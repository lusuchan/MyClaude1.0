"""Step 2 — research the news and geopolitical backdrop with Claude web search.

Two calls, deliberately separate:

1. **Movers** — what actually happened to these specific tickers, anchored to
   the real price moves computed upstream.
2. **Macro** — the rates / policy / geopolitical backdrop the whole watchlist
   is sitting in.

Splitting them keeps each search budget focused, and means one failing still
leaves the brief with half its context.

The prompts work hard on one thing above all: never inventing a cause. A brief
that confidently attributes a 7% drop to the wrong story is worse than one that
says the catalyst is unclear.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from .config import Watchlist
from .errors import ResearchError
from .llm import Citation, ClaudeClient, LLMResponse
from .market_data import MarketSnapshot, summarize_for_prompt

log = logging.getLogger(__name__)


RESEARCH_SYSTEM = """You are a research assistant for a private daily market brief. \
You are not writing the brief — you are gathering the raw material another step will synthesise.

Hard rules, in order of importance:

1. Never invent a cause. If a price move has no clearly reported catalyst, say \
"no clear catalyst reported" and stop. A confident wrong explanation is the worst \
possible output here.
2. Separate what is reported from what is speculation. Attribute both: "Reuters \
reported X"; "several analysts speculate Y". If commentary is one analyst's opinion, \
say so.
3. Date everything. "Thursday's earnings" is useless in isolation — give the date.
4. Prefer primary and major outlets (company filings and press releases, Reuters, \
Bloomberg, AP, WSJ, FT, CNBC) over aggregators and blog spam.
5. Be concrete. Numbers, names, dates. No filler, no hedging boilerplate, no \
"investors should monitor developments closely".
6. Do not give investment advice or make price predictions. You describe what \
happened and what is scheduled to happen."""


MOVERS_PROMPT = """Here is today's price and volume data for the watchlist. \
The numbers are already computed and correct — do not recompute or restate them at \
length, and do not contradict them.

<market_data>
{market_data}
</market_data>

Search the web and report what is behind these moves. Focus your searches on the \
names that actually moved: {focus}.

For each ticker that moved meaningfully (roughly 2%+, or on unusual volume), give:

- **Ticker** — one line on the move, then the catalyst if there is a reported one: \
earnings, guidance, an analyst action, a product or regulatory event, a sector-wide \
move. Include the date and the source.
- If the move has no clearly reported catalyst, say exactly that. Do not reach.

Then, briefly:

- **Sector context** — was any move part of a broader sector or index move rather \
than name-specific?
- **Scheduled ahead** — earnings dates, product events, or company-specific catalysts \
in the next week or two for any name on this list. Only things actually scheduled.

Keep the whole thing under 600 words. Dense notes, not an essay."""


MACRO_PROMPT = """Today is {today}. A private daily brief covers this watchlist:

{watchlist}

Search the web for the macro and geopolitical backdrop these positions are sitting in \
right now. Cover, in this order:

1. **Macro** — the last few days of rates, inflation, growth and central bank news, \
and anything scheduled in the coming week (Fed meetings, CPI/PPI, jobs, major earnings).
2. **Geopolitics** — live developments plausibly affecting these sectors: conflict, \
trade policy and tariffs, sanctions, export controls, elections, energy supply. \
Energy and semiconductors are the two most exposed lines on this list.
3. **Transmission** — for each item that matters, one clause on the actual mechanism \
by which it reaches these tickers. If the mechanism is speculative or indirect, say \
so plainly. Skip anything you cannot connect to this watchlist; a short honest list \
beats a long padded one.

Under 500 words. If a story is loud in the news but has no real transmission channel \
to these names, leave it out or note in one line that it is noise for this watchlist."""


@dataclass
class ResearchBundle:
    """Everything the research step gathered, plus what it failed to gather."""

    movers: LLMResponse | None = None
    macro: LLMResponse | None = None
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return bool(self.movers or self.macro)

    @property
    def partial(self) -> bool:
        return bool(self.errors) and self.ok

    @property
    def citations(self) -> list[Citation]:
        out: list[Citation] = []
        seen: set[str] = set()
        for response in (self.movers, self.macro):
            for cite in response.citations if response else []:
                if cite.url not in seen:
                    seen.add(cite.url)
                    out.append(cite)
        return out

    @property
    def search_count(self) -> int:
        return sum(r.search_count for r in (self.movers, self.macro) if r)

    def as_prompt_context(self) -> str:
        blocks: list[str] = []
        if self.movers:
            blocks.append(f"<ticker_research>\n{self.movers.text}\n</ticker_research>")
        if self.macro:
            blocks.append(f"<macro_research>\n{self.macro.text}\n</macro_research>")
        if self.errors:
            joined = "; ".join(self.errors)
            blocks.append(f"<research_gaps>\nThese research steps failed: {joined}\n</research_gaps>")
        return "\n\n".join(blocks)


def _focus_line(snapshot: MarketSnapshot) -> str:
    """Name the tickers actually worth searching, so the budget isn't wasted."""

    notable = [s for s in snapshot.ok_snapshots if s.is_notable_move]
    if not notable:
        notable = snapshot.movers(limit=3)
    if not notable:
        return "the whole list"

    return ", ".join(
        f"{s.symbol} ({s.change_pct:+.1f}%)" if s.change_pct is not None else s.symbol
        for s in notable
    )


def research_movers(
    client: ClaudeClient,
    snapshot: MarketSnapshot,
    *,
    max_tokens: int = 2500,
) -> LLMResponse:
    """Search for what moved the names on the list."""

    prompt = MOVERS_PROMPT.format(
        market_data=summarize_for_prompt(snapshot),
        focus=_focus_line(snapshot),
    )
    response = client.complete(
        prompt=prompt,
        system=RESEARCH_SYSTEM,
        max_tokens=max_tokens,
        web_search=True,
        label="research/movers",
    )
    if not response:
        raise ResearchError("movers research returned no text")
    return response


def research_macro(
    client: ClaudeClient,
    watchlist: Watchlist,
    snapshot: MarketSnapshot,
    *,
    max_tokens: int = 2500,
) -> LLMResponse:
    """Search for the macro and geopolitical backdrop."""

    lines = []
    for holding in watchlist.holdings:
        s = snapshot.by_symbol(holding.symbol)
        sector = f" [{s.sector}]" if s and s.sector else ""
        lines.append(f"- {holding.describe()}{sector}")

    today = snapshot.latest_session or snapshot.status.now_et.date()

    response = client.complete(
        prompt=MACRO_PROMPT.format(today=today.isoformat(), watchlist="\n".join(lines)),
        system=RESEARCH_SYSTEM,
        max_tokens=max_tokens,
        web_search=True,
        label="research/macro",
    )
    if not response:
        raise ResearchError("macro research returned no text")
    return response


def run_research(
    client: ClaudeClient,
    watchlist: Watchlist,
    snapshot: MarketSnapshot,
) -> ResearchBundle:
    """Run both research calls, tolerating either one failing.

    A brief with prices and macro context but no mover detail is still useful,
    and so is the reverse. Only a total failure is worth flagging loudly.
    """

    bundle = ResearchBundle()

    if not snapshot.ok_snapshots:
        bundle.errors.append("skipped ticker research: no market data was retrieved")
    else:
        try:
            bundle.movers = research_movers(client, snapshot)
        except Exception as exc:  # noqa: BLE001 - degrade, do not abort
            log.error("movers research failed: %s", exc)
            bundle.errors.append(f"ticker news research failed ({type(exc).__name__}: {exc})")

    try:
        bundle.macro = research_macro(client, watchlist, snapshot)
    except Exception as exc:  # noqa: BLE001
        log.error("macro research failed: %s", exc)
        bundle.errors.append(f"macro/geopolitical research failed ({type(exc).__name__}: {exc})")

    return bundle
