"""A thin wrapper over the Anthropic Messages API.

Wraps the two things every LLM step here needs and nothing else: retrying the
failures that are worth retrying, and flattening a response (which may be a
long chain of search-result and text blocks) into text plus a citation list.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from .config import Settings
from .retry import retry_call

log = logging.getLogger(__name__)

# Deliberately the basic variant, not the newer "web_search_20260209" with
# dynamic filtering. That one was tried and measured (2026-08-02) and is worse
# *here*: it routes results through code execution, and its text blocks carry no
# citations at all, so the brief's sources list degrades from "actually cited"
# to "everything consulted" -- 105 entries instead of 22. It also breaks the
# search count, because the extractor counts server_tool_use blocks and those
# then include code-execution calls. Do not upgrade this without first fixing
# citation extraction; see NOTES_FOR_PAYITO.md item 11.
WEB_SEARCH_TOOL_TYPE = "web_search_20250305"

# Generous, because a research call runs several web searches server-side
# before it returns, but bounded so a stalled request cannot hang the run.
REQUEST_TIMEOUT_SECONDS = 300.0

# Retried: the API is momentarily unhappy. Not retried: our request is wrong,
# or the key is bad — those fail the same way every time.
_RETRYABLE_STATUS = {408, 409, 429, 500, 502, 503, 504, 529}


@dataclass
class Citation:
    url: str
    title: str = ""
    # True when the model actually cited this in its prose. False means the
    # search merely returned it. Search results outnumber real citations by
    # roughly five to one and include plenty of junk, so the two are kept
    # apart and only the cited ones are shown to the reader.
    cited: bool = False

    def as_markdown(self) -> str:
        return f"[{self.title or self.url}]({self.url})"


@dataclass
class LLMResponse:
    text: str
    citations: list[Citation] = field(default_factory=list)
    search_count: int = 0
    stop_reason: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0

    def __bool__(self) -> bool:
        return bool(self.text.strip())

    @property
    def cited_sources(self) -> list[Citation]:
        return [c for c in self.citations if c.cited]


def _is_retryable(exc: BaseException) -> bool:
    status = getattr(exc, "status_code", None)
    if isinstance(status, int):
        return status in _RETRYABLE_STATUS

    name = type(exc).__name__
    if name in {"APIConnectionError", "APITimeoutError", "InternalServerError", "RateLimitError", "APIStatusError"}:
        return True
    # Anthropic's overloaded_error surfaces with varying types across SDK
    # versions; the string is the reliable tell.
    return "overloaded" in str(exc).lower()


def _extract(message: Any) -> LLMResponse:
    """Flatten a Messages response into text plus deduplicated citations."""

    chunks: list[str] = []
    by_url: dict[str, Citation] = {}
    searches = 0

    def record(url: str | None, title: str, cited: bool) -> None:
        if not url:
            return
        existing = by_url.get(url)
        if existing is None:
            by_url[url] = Citation(url=url, title=title, cited=cited)
            return
        # A URL first seen as a search result and later cited is promoted.
        existing.cited = existing.cited or cited
        if title and not existing.title:
            existing.title = title

    for block in getattr(message, "content", []) or []:
        btype = getattr(block, "type", None)

        if btype == "text":
            chunks.append(getattr(block, "text", "") or "")
            for cite in getattr(block, "citations", None) or []:
                record(getattr(cite, "url", None), getattr(cite, "title", "") or "", True)

        elif btype == "server_tool_use":
            searches += 1

        elif btype == "web_search_tool_result":
            # Kept, but marked uncited: useful for debugging what was consulted,
            # not for printing in the brief.
            for item in getattr(block, "content", None) or []:
                record(getattr(item, "url", None), getattr(item, "title", "") or "", False)

    citations = list(by_url.values())

    usage = getattr(message, "usage", None)

    return LLMResponse(
        text="".join(chunks).strip(),
        citations=citations,
        search_count=searches,
        stop_reason=getattr(message, "stop_reason", None),
        input_tokens=getattr(usage, "input_tokens", 0) or 0,
        output_tokens=getattr(usage, "output_tokens", 0) or 0,
    )


class ClaudeClient:
    """Small facade so the research and synthesis steps stay readable."""

    def __init__(self, settings: Settings, client: Any = None, sleep: Any = None):
        self.settings = settings
        self._sleep = sleep
        if client is not None:
            self._client = client
        else:
            if not settings.has_api_key:
                raise ValueError(
                    "no Anthropic API key — set ANTHROPIC_API_KEY in .env (see .env.example)"
                )
            import anthropic

            # max_retries=0 matters: the SDK retries twice by default, and
            # stacked with retry_call's three attempts a rate-limited call
            # would fire up to nine requests with no backoff coordination.
            # One retry policy, ours.
            self._client = anthropic.Anthropic(
                api_key=settings.api_key,
                max_retries=0,
                timeout=REQUEST_TIMEOUT_SECONDS,
            )

    def complete(
        self,
        *,
        prompt: str,
        system: str | None = None,
        max_tokens: int = 2000,
        web_search: bool = False,
        max_searches: int | None = None,
        attempts: int = 3,
        label: str = "claude call",
    ) -> LLMResponse:
        kwargs: dict[str, Any] = {
            "model": self.settings.model,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            kwargs["system"] = system
        if web_search:
            kwargs["tools"] = [
                {
                    "type": WEB_SEARCH_TOOL_TYPE,
                    "name": "web_search",
                    "max_uses": max_searches or self.settings.max_searches,
                }
            ]

        retry_kwargs: dict[str, Any] = {
            "attempts": attempts,
            "base_delay": 3.0,
            "max_delay": 45.0,
            "should_retry": _is_retryable,
            "label": label,
        }
        if self._sleep is not None:
            retry_kwargs["sleep"] = self._sleep

        message = retry_call(lambda: self._client.messages.create(**kwargs), **retry_kwargs)
        response = _extract(message)
        log.info(
            "%s: %d chars, %d searches, %d cited of %d results (in=%d out=%d)",
            label,
            len(response.text),
            response.search_count,
            len(response.cited_sources),
            len(response.citations),
            response.input_tokens,
            response.output_tokens,
        )
        return response
