"""Step 3 — turn numbers plus research into the readable part of the brief.

The division of labour with :mod:`briefbot.render` is deliberate. This module
produces only the *prose*. The price table, the sources list and the caveats
are rendered mechanically from the data, so no LLM output sits between the
reader and a number.

If this step fails, :func:`fallback_prose` produces a plain, honest stand-in so
there is still something to read at 7am.
"""

from __future__ import annotations

import logging

from .errors import SynthesisError
from .llm import ClaudeClient
from .market_data import MarketSnapshot, summarize_for_prompt
from .research import ResearchBundle

log = logging.getLogger(__name__)


SYNTHESIS_SYSTEM = """You write a private daily market brief for one experienced reader. \
They know what a P/E is. They do not need definitions, disclaimers, or encouragement.

Voice: direct, specific, unhurried. Short paragraphs. Plain sentences. The tone of a \
sharp colleague telling you what happened over coffee, not a newsletter trying to keep \
you subscribed.

Rules:

- Every number you use must come from the market data given to you. Never estimate, \
round misleadingly, or introduce a figure that is not in the data or the research notes.
- Distinguish fact from interpretation, every time. "Apple fell 7.3% after guiding \
below consensus" is fact. "The market appears to be repricing the AI capex cycle" is \
interpretation — mark it as such with words like "reads as", "the likely story is", \
"unclear whether".
- When the research found no catalyst for a move, say so. "No clear catalyst" is a \
legitimate and useful sentence. Never fill the gap with a plausible-sounding guess.
- No investment advice, no buy/sell language, no price targets of your own. You explain \
and you flag; you do not recommend.
- No filler. Cut "it is worth noting", "as always", "in today's volatile market". If a \
section has nothing real in it, write one honest line instead of padding it.
- Do not use headers beyond the ones you are asked for, and do not restate the price \
table — it is printed directly above your text."""


SYNTHESIS_PROMPT = """Write today's brief from the material below.

<market_data>
{market_data}
</market_data>

{research}

Produce exactly these four sections, in this order, using level-2 markdown headers:

## The read

Three to five sentences. What kind of day was this for this watchlist, and what is the \
one thing that most matters? Lead with the substance, not with scene-setting. If the \
day was unremarkable, say that plainly rather than manufacturing a narrative.

## What moved

The names that actually moved, most significant first. One short paragraph each, and \
only for moves worth explaining — a ticker that drifted 0.3% does not need a paragraph. \
Give the move, the reported cause with its source, and whether it looks name-specific \
or sector-wide. Where the research found no catalyst, say so.

## The backdrop

The macro and geopolitical context that actually touches these names, and the mechanism \
by which it does. Skip anything with no transmission channel to this list. Two or three \
short paragraphs at most.

## Watching

A short bulleted list — three to six items — of what is scheduled or genuinely unresolved \
in the coming days: earnings dates, data releases, policy decisions, open questions from \
today's moves. Each item one line. Scheduled events should carry their date. This is a \
watch list, not a trade list.

{caveat_note}Write the four sections and nothing else — no title, no preamble, no sign-off."""


FALLBACK_NOTE = (
    "Some research did not complete for this run, noted in the gaps block above. "
    "Write around what you have and do not speculate to fill the holes — if a mover "
    "has no research behind it, say the move is unexplained in this run.\n\n"
)


def build_prompt(snapshot: MarketSnapshot, research: ResearchBundle) -> str:
    research_block = research.as_prompt_context() or (
        "<research_gaps>\nNo web research was available for this run.\n</research_gaps>"
    )
    caveat_note = FALLBACK_NOTE if (research.errors or not research.ok) else ""
    return SYNTHESIS_PROMPT.format(
        market_data=summarize_for_prompt(snapshot),
        research=research_block,
        caveat_note=caveat_note,
    )


def synthesize(
    client: ClaudeClient,
    snapshot: MarketSnapshot,
    research: ResearchBundle,
    *,
    max_tokens: int = 3000,
) -> str:
    """Write the prose body of the brief. Raises on failure so the caller can
    choose to fall back."""

    response = client.complete(
        prompt=build_prompt(snapshot, research),
        system=SYNTHESIS_SYSTEM,
        max_tokens=max_tokens,
        label="synthesis",
    )
    if not response:
        raise SynthesisError("synthesis returned no text")
    return response.text.strip()


def fallback_prose(snapshot: MarketSnapshot, research: ResearchBundle, reason: str) -> str:
    """A mechanically-written body for when synthesis is unavailable.

    Deliberately dull and entirely deterministic — it states what the data
    shows and nothing more.
    """

    lines: list[str] = ["## The read", ""]
    lines.append(
        f"_Automated synthesis was unavailable for this run ({reason}). "
        "What follows is generated directly from the data._"
    )
    lines.append("")

    movers = [s for s in snapshot.movers(limit=5) if s.change_pct is not None]
    if not movers:
        lines.append("No usable price data was retrieved for this run.")
    else:
        biggest = movers[0]
        lines.append(
            f"Largest move on the list: {biggest.symbol} at {biggest.change_pct:+.2f}%. "
            f"{len([s for s in snapshot.ok_snapshots if (s.change_pct or 0) > 0])} of "
            f"{len(snapshot.ok_snapshots)} tickers closed higher."
        )

    lines += ["", "## What moved", ""]
    if movers:
        for s in movers:
            bits = [f"**{s.symbol}** ({s.display_name}) {s.change_pct:+.2f}%"]
            if s.close is not None:
                bits.append(f"closing at {s.close:,.2f}")
            if s.volume_ratio is not None:
                bits.append(f"on {s.volume_ratio:.2f}x its 20-day average volume")
            lines.append("- " + ", ".join(bits))
    else:
        lines.append("No price data available.")

    lines += ["", "## The backdrop", ""]
    if research.movers or research.macro:
        lines.append("Partial research notes were retrieved:")
        lines.append("")
        for response in (research.movers, research.macro):
            if response:
                lines.append(response.text)
                lines.append("")
    else:
        lines.append("No research was retrieved for this run.")

    lines += ["", "## Watching", "", "- Re-run the brief once the failing step recovers."]
    for err in research.errors:
        lines.append(f"- Unresolved: {err}")

    return "\n".join(lines).strip()
