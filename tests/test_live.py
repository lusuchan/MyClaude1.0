"""Live smoke tests. Skipped by default; run with ``pytest -m live``.

These hit real Yahoo Finance and the real Claude API, so they cost time and
tokens. They exist because the mocked tests cannot catch the failure that
actually bites in practice: an upstream shape change. yfinance is an
unofficial wrapper and Yahoo alters its payloads without notice.

Run these when something looks wrong, after a dependency bump, or before
trusting a brief you have not read closely.
"""

from __future__ import annotations

import os
from datetime import date, timedelta

import pytest

from briefbot.config import Holding, Settings, Watchlist, load_settings, load_watchlist
from briefbot.llm import ClaudeClient
from briefbot.market_data import build_session, fetch_ticker, fetch_watchlist
from briefbot.pipeline import run_brief

pytestmark = pytest.mark.live


@pytest.fixture(scope="module")
def live_settings() -> Settings:
    return load_settings()


@pytest.fixture(scope="module")
def live_session(live_settings):
    return build_session(live_settings)


needs_key = pytest.mark.skipif(
    not load_settings().has_api_key, reason="no ANTHROPIC_API_KEY configured"
)


# ---------------------------------------------------------------------------
# yfinance
# ---------------------------------------------------------------------------


def test_a_real_ticker_returns_plausible_data(live_session):
    snap = fetch_ticker(Holding(symbol="SPY", label="S&P 500 ETF"), session=live_session)

    assert snap.ok, snap.error
    assert snap.close and snap.close > 0
    assert snap.volume and snap.volume > 0
    assert snap.bars_used > 200, "a 1y window should hold roughly 250 trading days"
    assert snap.change_pct is not None and abs(snap.change_pct) < 25, "SPY moving 25% in a day would be historic"


def test_the_latest_bar_is_recent(live_session):
    snap = fetch_ticker(Holding(symbol="SPY"), session=live_session, include_fundamentals=False)

    assert snap.session_date is not None
    age = (date.today() - snap.session_date).days
    assert age <= 6, f"latest bar is {age} days old — Yahoo may be stalled"


def test_52_week_range_brackets_the_close(live_session):
    snap = fetch_ticker(Holding(symbol="AAPL"), session=live_session, include_fundamentals=False)

    assert snap.low_52w <= snap.close <= snap.high_52w
    assert snap.pct_from_52w_high <= 0


def test_fundamentals_come_through_for_a_large_cap(live_session):
    snap = fetch_ticker(Holding(symbol="MSFT"), session=live_session)

    assert snap.market_cap and snap.market_cap > 1e11
    assert snap.sector


def test_dividend_yield_is_in_a_sane_range(live_session):
    # The scale bug this guards against reported a 0.35% yield as 35%.
    snap = fetch_ticker(Holding(symbol="JPM"), session=live_session)

    assert snap.dividend_yield_pct is not None
    assert 0.1 < snap.dividend_yield_pct < 15, f"implausible yield: {snap.dividend_yield_pct}"


def test_a_bogus_ticker_fails_softly(live_session):
    snap = fetch_ticker(
        Holding(symbol="ZZQQXX9"), session=live_session, attempts=1, include_fundamentals=False
    )

    assert not snap.ok
    assert snap.error


def test_a_mixed_watchlist_survives_one_bad_symbol(live_settings, live_session):
    wl = Watchlist(
        name="live test",
        holdings=(Holding(symbol="SPY"), Holding(symbol="ZZQQXX9"), Holding(symbol="AAPL")),
    )
    result = fetch_watchlist(wl, live_settings, session=live_session, attempts=1, include_fundamentals=False)

    assert len(result.ok_snapshots) == 2
    assert len(result.failed_snapshots) == 1


# ---------------------------------------------------------------------------
# Claude
# ---------------------------------------------------------------------------


@needs_key
def test_the_api_answers(live_settings):
    response = ClaudeClient(live_settings).complete(
        prompt="Reply with exactly: OK", max_tokens=16, label="live/ping"
    )
    assert "OK" in response.text


@needs_key
def test_web_search_returns_cited_results(live_settings):
    response = ClaudeClient(live_settings).complete(
        prompt="What is the current US federal funds target rate? One sentence, cite your source.",
        max_tokens=1200,
        web_search=True,
        max_searches=2,
        label="live/search",
    )

    assert response.search_count >= 1
    assert response.cited_sources, "web search ran but nothing was cited"


# ---------------------------------------------------------------------------
# Whole pipeline
# ---------------------------------------------------------------------------


@needs_key
def test_the_whole_pipeline_produces_a_real_brief(tmp_path, live_settings):
    from dataclasses import replace

    settings = replace(live_settings, output_dir=tmp_path)
    wl = Watchlist(name="live smoke", holdings=(Holding(symbol="SPY"), Holding(symbol="AAPL")))

    result = run_brief(watchlist=wl, settings=settings)

    assert result.path and result.path.exists()
    assert result.synthesized, f"synthesis did not run: {result.degradations}"

    text = result.text
    for section in ("## The read", "## What moved", "## The backdrop", "## Watching", "## The numbers"):
        assert section in text, f"missing {section}"

    assert "SPY" in text and "AAPL" in text
    assert result.research.citations, "a brief with no sources is not a researched brief"
    assert len(text) > 1500, "suspiciously short for a full brief"


def test_data_only_pipeline_needs_no_key(tmp_path, live_settings):
    from dataclasses import replace

    settings = replace(live_settings, output_dir=tmp_path)
    wl = Watchlist(name="live smoke", holdings=(Holding(symbol="SPY"),))

    result = run_brief(watchlist=wl, settings=settings, skip_research=True)

    assert result.path.exists()
    assert "## The numbers" in result.text
    assert "SPY" in result.text
