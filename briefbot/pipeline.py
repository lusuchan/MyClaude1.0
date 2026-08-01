"""The thin orchestrator: data -> research -> synthesis -> file.

Each step is allowed to fail without ending the run. What comes out the far
end always says honestly what it is missing.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .config import Settings, Watchlist, load_settings, load_watchlist
from .llm import ClaudeClient
from .market_data import MarketSnapshot, fetch_watchlist
from .render import render_brief, write_brief
from .research import ResearchBundle, run_research
from .synthesis import fallback_prose, synthesize

log = logging.getLogger(__name__)


@dataclass
class BriefResult:
    text: str
    snapshot: MarketSnapshot
    research: ResearchBundle
    path: Path | None = None
    degradations: list[str] = field(default_factory=list)
    synthesized: bool = True
    write_error: str | None = None

    @property
    def degraded(self) -> bool:
        return bool(self.degradations)

    @property
    def usable(self) -> bool:
        """Whether this run produced anything worth reading.

        A brief with no prices and no research is a failed run, not a quiet
        one — the distinction is what makes a cron alert meaningful.
        """

        return bool(self.snapshot.ok_snapshots) or self.research.ok

    def summary(self) -> str:
        got = len(self.snapshot.ok_snapshots)
        total = len(self.snapshot.snapshots)
        bits = [f"{got}/{total} tickers"]
        if self.research.search_count:
            bits.append(f"{self.research.search_count} web searches")
        if self.research.citations:
            bits.append(f"{len(self.research.citations)} sources")
        bits.append("synthesised" if self.synthesized else "fallback prose")
        return ", ".join(bits)


def run_brief(
    *,
    watchlist: Watchlist | None = None,
    settings: Settings | None = None,
    watchlist_path: str | Path | None = None,
    skip_research: bool = False,
    write: bool = True,
    now_et: datetime | None = None,
    client: ClaudeClient | None = None,
    include_fundamentals: bool = True,
) -> BriefResult:
    """Run the full pipeline and return the brief.

    ``skip_research=True`` produces a numbers-only brief with no API calls,
    which is both a fast dev loop and the honest degraded mode when there is
    no API key.
    """

    settings = settings or load_settings()
    watchlist = watchlist or load_watchlist(watchlist_path)
    degradations: list[str] = []

    log.info("fetching market data for %d tickers", len(watchlist))
    snapshot = fetch_watchlist(
        watchlist, settings, now_et=now_et, include_fundamentals=include_fundamentals
    )

    if not snapshot.ok_snapshots:
        degradations.append("no market data was retrieved for any ticker")
    elif snapshot.failed_snapshots:
        degradations.append(
            f"{len(snapshot.failed_snapshots)} of {len(snapshot.snapshots)} tickers had no data"
        )

    research = ResearchBundle()
    prose: str

    if skip_research:
        research.errors.append("research skipped by request")
        degradations.append("research skipped — this is a data-only brief")
        prose = fallback_prose(snapshot, research, "research skipped")
        synthesized = False
    elif client is None and not settings.has_api_key:
        msg = "no ANTHROPIC_API_KEY — falling back to a data-only brief"
        log.error(msg)
        research.errors.append(msg)
        degradations.append(msg)
        prose = fallback_prose(snapshot, research, "no API key configured")
        synthesized = False
    else:
        if client is None:
            client = ClaudeClient(settings)

        research = run_research(client, watchlist, snapshot)
        if research.errors:
            degradations.extend(research.errors)

        try:
            prose = synthesize(client, snapshot, research)
            synthesized = True
        except Exception as exc:  # noqa: BLE001 - a failed write-up still ships a brief
            log.error("synthesis failed: %s", exc)
            degradations.append(f"synthesis failed ({type(exc).__name__}: {exc})")
            prose = fallback_prose(snapshot, research, f"{type(exc).__name__}")
            synthesized = False

    text = render_brief(snapshot, research, prose, watchlist_name=watchlist.name)

    result = BriefResult(
        text=text,
        snapshot=snapshot,
        research=research,
        degradations=degradations,
        synthesized=synthesized,
    )

    if write:
        try:
            result.path = write_brief(text, settings.output_dir, snapshot)
        except OSError as exc:
            # Losing a brief that took a dozen web searches to produce because
            # a directory is read-only would be the worst possible ending.
            # Record it; the CLI prints the text to stdout instead.
            log.error("could not write the brief to %s: %s", settings.output_dir, exc)
            result.write_error = f"could not write to {settings.output_dir}: {exc}"
            result.degradations.append(result.write_error)

    return result
