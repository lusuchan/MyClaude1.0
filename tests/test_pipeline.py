"""End-to-end orchestration tests with every external call mocked.

The property under test throughout: whatever fails, a brief still comes out,
and it says honestly what it is missing.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from briefbot.config import Holding, Settings, Watchlist
from briefbot.llm import ClaudeClient
from briefbot.market_clock import EASTERN
from briefbot.pipeline import run_brief
from conftest import FakeAnthropic, make_frame, make_message, text_block

FRIDAY_EVENING = datetime(2026, 7, 31, 18, 0, tzinfo=EASTERN)


class FakeTicker:
    def __init__(self, frame=None, exc=None):
        self._frame = frame
        self._exc = exc

    def history(self, **kwargs):
        if self._exc:
            raise self._exc
        return self._frame

    def get_info(self):
        return {}

    @property
    def fast_info(self):
        return {}


@pytest.fixture
def market(monkeypatch):
    """Patch yfinance out. Returns a setter for per-symbol behaviour."""

    mapping: dict[str, FakeTicker] = {}

    def factory(symbol, session):
        return mapping.get(symbol, FakeTicker(frame=make_frame([100.0 + i for i in range(30)])))

    monkeypatch.setattr("briefbot.market_data._make_ticker", factory)
    return mapping


def client_for(responses):
    return ClaudeClient(Settings(api_key="k"), client=FakeAnthropic(responses), sleep=lambda _: None)


def three_good_responses():
    return [
        make_message([text_block("mover research")]),
        make_message([text_block("macro research")]),
        make_message([text_block("## The read\n\nA synthesised day.")]),
    ]


def run(watchlist, settings, **kwargs):
    kwargs.setdefault("now_et", FRIDAY_EVENING)
    kwargs.setdefault("include_fundamentals", False)
    return run_brief(watchlist=watchlist, settings=settings, **kwargs)


# ---------------------------------------------------------------------------
# The happy path
# ---------------------------------------------------------------------------


def test_full_run_writes_a_synthesised_brief(market, watchlist, settings):
    result = run(watchlist, settings, client=client_for(three_good_responses()))

    assert result.synthesized
    assert not result.degraded
    assert "A synthesised day." in result.text
    assert result.path.exists()
    assert result.path.read_text() == result.text


def test_latest_is_written_alongside_the_dated_brief(market, watchlist, settings):
    result = run(watchlist, settings, client=client_for(three_good_responses()))
    assert (settings.output_dir / "latest.md").read_text() == result.text


def test_write_can_be_suppressed(market, watchlist, settings):
    result = run(watchlist, settings, client=client_for(three_good_responses()), write=False)

    assert result.path is None
    assert not settings.output_dir.exists()


def test_summary_reports_what_happened(market, watchlist, settings):
    result = run(watchlist, settings, client=client_for(three_good_responses()))
    assert "2/2 tickers" in result.summary()
    assert "synthesised" in result.summary()


# ---------------------------------------------------------------------------
# Degradation
# ---------------------------------------------------------------------------


def test_a_missing_ticker_degrades_but_still_ships(market, watchlist, settings):
    market["BBB"] = FakeTicker(exc=Exception("No data found, symbol may be delisted"))

    result = run(watchlist, settings, client=client_for(three_good_responses()))

    assert result.degraded
    assert "1 of 2 tickers had no data" in " ".join(result.degradations)
    assert "`BBB`" in result.text
    assert result.path.exists()


def test_failed_research_still_produces_a_synthesised_brief(market, watchlist, settings):
    client = client_for(
        [
            Exception("search is down"),
            Exception("search is still down"),
            make_message([text_block("## The read\n\nWrote it anyway.")]),
        ]
    )
    result = run(watchlist, settings, client=client)

    assert result.synthesized
    assert result.degraded
    assert "Wrote it anyway." in result.text


def test_failed_synthesis_falls_back_to_deterministic_prose(market, watchlist, settings):
    client = client_for(
        [
            make_message([text_block("mover research")]),
            make_message([text_block("macro research")]),
            Exception("model is down"),
        ]
    )
    result = run(watchlist, settings, client=client)

    assert not result.synthesized
    assert result.degraded
    assert "Automated synthesis was unavailable" in result.text
    assert "mover research" in result.text, "surviving research must not be thrown away"
    assert result.path.exists()


def test_no_api_key_produces_a_data_only_brief(market, watchlist, tmp_path):
    settings = Settings(api_key=None, output_dir=tmp_path / "briefs")

    result = run(watchlist, settings)

    assert not result.synthesized
    assert any("ANTHROPIC_API_KEY" in d for d in result.degradations)
    assert "## The numbers" in result.text
    assert result.path.exists()


def test_skip_research_makes_no_api_calls(market, watchlist, settings):
    fake = FakeAnthropic([])  # any call would raise
    result = run(watchlist, settings, client=ClaudeClient(Settings(api_key="k"), client=fake), skip_research=True)

    assert fake.calls == []
    assert not result.synthesized
    assert "data-only brief" in " ".join(result.degradations)


def test_a_total_data_failure_still_writes_something(market, watchlist, settings):
    for symbol in ("AAA", "BBB"):
        market[symbol] = FakeTicker(exc=Exception("No data found"))

    result = run(watchlist, settings, client=client_for(three_good_responses()))

    assert result.degraded
    assert any("no market data" in d for d in result.degradations)
    assert result.path.exists()
    assert "No market data was retrieved" in result.text


def test_ticker_research_is_skipped_when_no_data_exists(market, watchlist, settings):
    for symbol in ("AAA", "BBB"):
        market[symbol] = FakeTicker(exc=Exception("No data found"))

    fake = FakeAnthropic([make_message([text_block("macro")]), make_message([text_block("prose")])])
    run(watchlist, settings, client=ClaudeClient(Settings(api_key="k"), client=fake))

    # Two calls, not three: the movers research had nothing to research.
    assert len(fake.calls) == 2


# ---------------------------------------------------------------------------
# Ordering
# ---------------------------------------------------------------------------


def test_research_runs_before_synthesis_and_feeds_it(market, watchlist, settings):
    fake = FakeAnthropic(three_good_responses())
    run(watchlist, settings, client=ClaudeClient(Settings(api_key="k"), client=fake))

    assert len(fake.calls) == 3
    synthesis_prompt = fake.calls[2]["messages"][0]["content"]
    assert "mover research" in synthesis_prompt
    assert "macro research" in synthesis_prompt
    assert "tools" not in fake.calls[2]


def test_numbers_in_the_table_come_from_data_not_from_the_model(market, watchlist, settings):
    # The model emits a wrong figure; the table must still be right.
    client = client_for(
        [
            make_message([text_block("AAA rose 999%")]),
            make_message([text_block("macro")]),
            make_message([text_block("## The read\n\nAAA rose 999%.")]),
        ]
    )
    result = run(watchlist, settings, client=client)

    table = result.text.split("## The numbers")[1]
    assert "999" not in table
    # make_frame closes at 100..129, so the real 1-day move is 129/128 - 1.
    assert "+0.78%" in table
    assert result.snapshot.by_symbol("AAA").change_pct == pytest.approx(0.78125, abs=1e-4)
