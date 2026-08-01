"""Tests for the two LLM steps.

These check plumbing and degradation, not prose quality — a scripted client
cannot tell you whether the writing is good. Prose quality is what the live
smoke test and reading the actual brief are for.
"""

from __future__ import annotations

from datetime import date

import pytest

from briefbot.config import Settings
from briefbot.errors import SynthesisError
from briefbot.llm import ClaudeClient, LLMResponse
from briefbot.market_data import TickerSnapshot
from briefbot.research import ResearchBundle, _focus_line, research_macro, research_movers, run_research
from briefbot.synthesis import build_prompt, fallback_prose, synthesize
from conftest import FakeAnthropic, make_message, make_snapshot, search_result_block, text_block


def client_for(responses) -> ClaudeClient:
    return ClaudeClient(Settings(api_key="k", model="m"), client=FakeAnthropic(responses), sleep=lambda _: None)


# ---------------------------------------------------------------------------
# Focus selection
# ---------------------------------------------------------------------------


def test_focus_names_the_notable_movers():
    snap = make_snapshot(
        [
            TickerSnapshot(symbol="BIG", change_pct=-7.4, session_date=date(2026, 7, 31)),
            TickerSnapshot(symbol="MEH", change_pct=0.1, session_date=date(2026, 7, 31)),
        ]
    )
    focus = _focus_line(snap)

    assert "BIG" in focus and "-7.4%" in focus
    assert "MEH" not in focus, "a 0.1% drift does not deserve a web search"


def test_focus_falls_back_to_top_movers_on_a_quiet_day():
    snap = make_snapshot(
        [
            TickerSnapshot(symbol="A", change_pct=0.4, session_date=date(2026, 7, 31)),
            TickerSnapshot(symbol="B", change_pct=0.9, session_date=date(2026, 7, 31)),
        ]
    )
    assert "B" in _focus_line(snap)


def test_focus_handles_a_watchlist_with_no_data():
    snap = make_snapshot([TickerSnapshot(symbol="X", ok=False, error="nope")])
    assert _focus_line(snap) == "the whole list"


# ---------------------------------------------------------------------------
# Research calls
# ---------------------------------------------------------------------------


def test_movers_research_returns_text_and_uses_search(snapshot):
    fake = FakeAnthropic([make_message([text_block("AAA fell on guidance.")])])
    client = ClaudeClient(Settings(api_key="k"), client=fake)

    response = research_movers(client, snapshot)

    assert "guidance" in response.text
    assert "tools" in fake.calls[0], "the research step is pointless without web search"


def test_movers_prompt_carries_the_real_numbers(snapshot):
    fake = FakeAnthropic([make_message([text_block("x")])])
    research_movers(ClaudeClient(Settings(api_key="k"), client=fake), snapshot)

    prompt = fake.calls[0]["messages"][0]["content"]
    assert "+11.11%" in prompt
    assert "<market_data>" in prompt


def test_macro_prompt_lists_the_watchlist_with_sectors(watchlist, snapshot):
    fake = FakeAnthropic([make_message([text_block("x")])])
    research_macro(ClaudeClient(Settings(api_key="k"), client=fake), watchlist, snapshot)

    prompt = fake.calls[0]["messages"][0]["content"]
    assert "AAA" in prompt and "Alpha Corp" in prompt
    assert "Technology" in prompt


def test_research_system_prompt_forbids_inventing_causes(snapshot):
    fake = FakeAnthropic([make_message([text_block("x")])])
    research_movers(ClaudeClient(Settings(api_key="k"), client=fake), snapshot)

    assert "Never invent a cause" in fake.calls[0]["system"]


# ---------------------------------------------------------------------------
# Bundle degradation
# ---------------------------------------------------------------------------


def test_both_research_calls_succeed(watchlist, snapshot):
    client = client_for(
        [make_message([text_block("movers")]), make_message([text_block("macro")])]
    )
    bundle = run_research(client, watchlist, snapshot)

    assert bundle.ok and not bundle.errors
    assert bundle.movers.text == "movers"
    assert bundle.macro.text == "macro"


def test_a_failed_movers_call_still_leaves_macro(watchlist, snapshot):
    client = client_for([Exception("boom"), make_message([text_block("macro")])])
    bundle = run_research(client, watchlist, snapshot)

    assert bundle.ok and bundle.partial
    assert bundle.movers is None
    assert bundle.macro.text == "macro"
    assert any("ticker news research failed" in e for e in bundle.errors)


def test_a_failed_macro_call_still_leaves_movers(watchlist, snapshot):
    client = client_for([make_message([text_block("movers")]), Exception("boom")])
    bundle = run_research(client, watchlist, snapshot)

    assert bundle.ok and bundle.partial
    assert bundle.macro is None


def test_both_failing_leaves_an_unusable_but_intact_bundle(watchlist, snapshot):
    client = client_for([Exception("a"), Exception("b")])
    bundle = run_research(client, watchlist, snapshot)

    assert not bundle.ok
    assert len(bundle.errors) == 2


def test_ticker_research_is_skipped_when_there_is_no_data(watchlist):
    snap = make_snapshot([TickerSnapshot(symbol="X", ok=False, error="nope")])
    client = client_for([make_message([text_block("macro")])])

    bundle = run_research(client, watchlist, snap)

    assert bundle.movers is None
    assert bundle.macro is not None
    assert any("no market data" in e for e in bundle.errors)


def test_bundle_prefers_cited_sources_over_raw_results():
    bundle = ResearchBundle(
        movers=LLMResponse(
            text="x",
            citations=_cites([("https://a", True), ("https://junk", False)]),
        )
    )
    assert [c.url for c in bundle.citations] == ["https://a"]
    assert len(bundle.all_results) == 2


def test_bundle_falls_back_to_results_when_nothing_was_cited():
    bundle = ResearchBundle(movers=LLMResponse(text="x", citations=_cites([("https://only", False)])))
    assert [c.url for c in bundle.citations] == ["https://only"]


def test_bundle_deduplicates_across_both_calls():
    shared = [("https://same", True)]
    bundle = ResearchBundle(
        movers=LLMResponse(text="a", citations=_cites(shared)),
        macro=LLMResponse(text="b", citations=_cites(shared)),
    )
    assert len(bundle.citations) == 1


def test_prompt_context_exposes_research_gaps():
    bundle = ResearchBundle(movers=LLMResponse(text="m"), errors=["macro failed"])
    context = bundle.as_prompt_context()

    assert "<ticker_research>" in context
    assert "<research_gaps>" in context
    assert "macro failed" in context


def _cites(pairs):
    from briefbot.llm import Citation

    return [Citation(url=url, title="", cited=cited) for url, cited in pairs]


# ---------------------------------------------------------------------------
# Synthesis
# ---------------------------------------------------------------------------


def test_synthesis_returns_prose(snapshot):
    client = client_for([make_message([text_block("## The read\n\nQuiet day.")])])
    assert "Quiet day" in synthesize(client, snapshot, ResearchBundle())


def test_synthesis_does_not_get_web_search(snapshot):
    fake = FakeAnthropic([make_message([text_block("prose")])])
    synthesize(ClaudeClient(Settings(api_key="k"), client=fake), snapshot, ResearchBundle())

    assert "tools" not in fake.calls[0], "synthesis reads research, it does not do its own"


def test_empty_synthesis_output_raises(snapshot):
    client = client_for([make_message([text_block("   ")])])
    with pytest.raises(SynthesisError):
        synthesize(client, snapshot, ResearchBundle())


def test_synthesis_prompt_includes_research_and_data(snapshot):
    bundle = ResearchBundle(movers=LLMResponse(text="mover notes"), macro=LLMResponse(text="macro notes"))
    prompt = build_prompt(snapshot, bundle)

    assert "mover notes" in prompt and "macro notes" in prompt
    assert "+11.11%" in prompt
    assert "## The read" in prompt


def test_synthesis_prompt_warns_the_model_when_research_is_missing(snapshot):
    prompt = build_prompt(snapshot, ResearchBundle(errors=["macro failed"]))
    assert "do not speculate to fill the holes" in prompt


def test_no_caveat_note_when_research_is_complete(snapshot):
    bundle = ResearchBundle(movers=LLMResponse(text="m"), macro=LLMResponse(text="x"))
    assert "do not speculate to fill the holes" not in build_prompt(snapshot, bundle)


# ---------------------------------------------------------------------------
# Fallback prose
# ---------------------------------------------------------------------------


def test_fallback_prose_has_all_four_sections(snapshot):
    text = fallback_prose(snapshot, ResearchBundle(), "test reason")

    for header in ("## The read", "## What moved", "## The backdrop", "## Watching"):
        assert header in text


def test_fallback_prose_names_the_reason_and_the_biggest_mover(snapshot):
    text = fallback_prose(snapshot, ResearchBundle(), "no API key")

    assert "no API key" in text
    assert "AAA" in text and "+11.11%" in text


def test_fallback_prose_survives_a_total_data_failure():
    snap = make_snapshot([TickerSnapshot(symbol="X", ok=False, error="nope")])
    text = fallback_prose(snap, ResearchBundle(), "reason")

    assert "No usable price data" in text


def test_fallback_prose_includes_whatever_research_survived(snapshot):
    bundle = ResearchBundle(macro=LLMResponse(text="the macro notes survived"))
    assert "the macro notes survived" in fallback_prose(snapshot, bundle, "synthesis failed")
