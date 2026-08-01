"""Tests for the deterministic half of the pipeline.

The metric maths is checked against hand-computed values, and the fetch path
is checked for the property that matters most: one bad ticker must never take
down the run.
"""

from __future__ import annotations

from datetime import date, datetime
from types import SimpleNamespace

import pandas as pd
import pytest

from briefbot.config import Holding, Settings, Watchlist
from briefbot.errors import TickerNotFound
from briefbot.market_clock import EASTERN
from briefbot.market_data import (
    MarketSnapshot,
    TickerSnapshot,
    _dividend_yield_pct,
    _is_not_found,
    build_session,
    compute_metrics,
    fetch_ticker,
    fetch_watchlist,
    summarize_for_prompt,
)
from conftest import make_frame, make_snapshot


# ---------------------------------------------------------------------------
# Metric computation
# ---------------------------------------------------------------------------


def test_one_day_change():
    snap = TickerSnapshot(symbol="AAA")
    compute_metrics(snap, make_frame([100.0, 110.0]))
    assert snap.close == 110.0
    assert snap.prev_close == 100.0
    assert snap.change_abs == pytest.approx(10.0)
    assert snap.change_pct == pytest.approx(10.0)


def test_a_down_day_is_negative():
    snap = TickerSnapshot(symbol="AAA")
    compute_metrics(snap, make_frame([200.0, 185.0]))
    assert snap.change_pct == pytest.approx(-7.5)


def test_five_and_twentyone_day_lookbacks():
    # 30 bars, closing price equal to 100 + index, so the 5-day lookback is
    # exactly 5 points back.
    closes = [100.0 + i for i in range(30)]
    snap = TickerSnapshot(symbol="AAA")
    compute_metrics(snap, make_frame(closes))

    assert snap.close == 129.0
    assert snap.change_5d_pct == pytest.approx((129.0 / 124.0 - 1) * 100)
    assert snap.change_21d_pct == pytest.approx((129.0 / 108.0 - 1) * 100)


def test_lookbacks_are_none_when_history_is_too_short():
    snap = TickerSnapshot(symbol="AAA")
    compute_metrics(snap, make_frame([100.0, 101.0, 102.0]))
    assert snap.change_5d_pct is None
    assert snap.change_21d_pct is None


def test_ytd_uses_the_last_close_of_the_prior_year():
    # Frame straddling the new year: prior-year final close is 100.
    index = pd.to_datetime(
        ["2025-12-30", "2025-12-31", "2026-01-02", "2026-01-05"]
    ).tz_localize("America/New_York")
    frame = pd.DataFrame(
        {
            "Open": [98, 99, 101, 108],
            "High": [101, 101, 106, 112],
            "Low": [97, 98, 100, 107],
            "Close": [99.0, 100.0, 105.0, 110.0],
            "Volume": [1e6] * 4,
        },
        index=index,
    )
    snap = TickerSnapshot(symbol="AAA")
    compute_metrics(snap, frame)
    assert snap.change_ytd_pct == pytest.approx(10.0)


def test_ytd_is_none_without_prior_year_data():
    snap = TickerSnapshot(symbol="AAA")
    compute_metrics(snap, make_frame([100.0, 105.0], end=date(2026, 7, 31)))
    assert snap.change_ytd_pct is None


def test_volume_ratio_excludes_the_reported_day():
    # Twenty-one bars: twenty at 1M, then a 3M spike. The average must be the
    # 1M baseline, not contaminated by the spike itself.
    volumes = [1_000_000.0] * 20 + [3_000_000.0]
    snap = TickerSnapshot(symbol="AAA")
    compute_metrics(snap, make_frame([100.0] * 21, volumes=volumes))

    assert snap.avg_volume_20d == pytest.approx(1_000_000.0)
    assert snap.volume_ratio == pytest.approx(3.0)


def test_volume_ratio_needs_a_minimum_of_history():
    snap = TickerSnapshot(symbol="AAA")
    compute_metrics(snap, make_frame([100.0] * 3))
    assert snap.avg_volume_20d is None
    assert snap.volume_ratio is None


def test_52_week_range_and_distance_from_high():
    closes = [100.0] * 10
    highs = [120.0] + [105.0] * 9
    lows = [95.0] * 9 + [80.0]
    snap = TickerSnapshot(symbol="AAA")
    compute_metrics(snap, make_frame(closes, highs=highs, lows=lows))

    assert snap.high_52w == 120.0
    assert snap.low_52w == 80.0
    assert snap.pct_from_52w_high == pytest.approx((100.0 / 120.0 - 1) * 100)


def test_intraday_range_is_measured_against_the_prior_close():
    snap = TickerSnapshot(symbol="AAA")
    compute_metrics(
        snap,
        make_frame([100.0, 102.0], highs=[101.0, 105.0], lows=[99.0, 100.0]),
    )
    assert snap.intraday_range_pct == pytest.approx(5.0)


def test_nan_values_are_treated_as_missing():
    frame = make_frame([100.0, 105.0])
    frame.iloc[-1, frame.columns.get_loc("Volume")] = float("nan")
    snap = TickerSnapshot(symbol="AAA")
    compute_metrics(snap, frame)
    assert snap.volume is None
    assert snap.close == 105.0


def test_empty_closes_raise_not_found():
    frame = make_frame([100.0])
    frame["Close"] = [float("nan")]
    snap = TickerSnapshot(symbol="ZZZ")
    with pytest.raises(TickerNotFound):
        compute_metrics(snap, frame)


def test_session_date_comes_from_the_last_bar():
    snap = TickerSnapshot(symbol="AAA")
    compute_metrics(snap, make_frame([100.0, 101.0], end=date(2026, 3, 12)))
    assert snap.session_date == date(2026, 3, 12)


def test_notable_move_thresholds():
    quiet = TickerSnapshot(symbol="A", change_pct=0.4, volume_ratio=1.0)
    big_move = TickerSnapshot(symbol="B", change_pct=-2.5, volume_ratio=1.0)
    big_volume = TickerSnapshot(symbol="C", change_pct=0.3, volume_ratio=2.0)

    assert not quiet.is_notable_move
    assert big_move.is_notable_move
    assert big_volume.is_notable_move


# ---------------------------------------------------------------------------
# Fetch behaviour
# ---------------------------------------------------------------------------


class FakeTicker:
    def __init__(self, frame=None, exc=None, info=None):
        self._frame = frame
        self._exc = exc
        self._info = info or {}
        self.history_calls = 0

    def history(self, **kwargs):
        self.history_calls += 1
        if self._exc is not None:
            raise self._exc
        return self._frame

    def get_info(self):
        return self._info

    @property
    def fast_info(self):
        return {}


@pytest.fixture
def patch_ticker(monkeypatch):
    """Install a factory that returns scripted FakeTickers by symbol."""

    def install(mapping):
        def factory(symbol, session):
            return mapping[symbol]

        monkeypatch.setattr("briefbot.market_data._make_ticker", factory)
        return mapping

    return install


def test_fetch_ticker_success(patch_ticker):
    patch_ticker({"AAA": FakeTicker(frame=make_frame([100.0, 110.0]))})
    snap = fetch_ticker(Holding(symbol="AAA"), include_fundamentals=False)

    assert snap.ok
    assert snap.change_pct == pytest.approx(10.0)
    assert snap.error is None


def test_unknown_ticker_is_recorded_not_raised(patch_ticker):
    empty = pd.DataFrame({"Close": [], "Volume": [], "High": [], "Low": [], "Open": []})
    patch_ticker({"NOPE": FakeTicker(frame=empty)})

    snap = fetch_ticker(Holding(symbol="NOPE"), include_fundamentals=False)

    assert not snap.ok
    assert "not found" in (snap.error or "")


def test_a_delisted_symbol_is_not_retried(patch_ticker):
    fake = FakeTicker(exc=Exception("AAA: No data found, symbol may be delisted"))
    patch_ticker({"AAA": fake})

    snap = fetch_ticker(Holding(symbol="AAA"), attempts=3, sleep=lambda _: None, include_fundamentals=False)

    assert not snap.ok
    assert fake.history_calls == 1, "a delisting is permanent — retrying it is wasted time"


def test_a_transient_failure_is_retried(patch_ticker):
    fake = FakeTicker(exc=Exception("429 Too Many Requests"))
    patch_ticker({"AAA": fake})

    snap = fetch_ticker(Holding(symbol="AAA"), attempts=3, sleep=lambda _: None, include_fundamentals=False)

    assert not snap.ok
    assert fake.history_calls == 3


def test_retry_succeeds_on_a_later_attempt(monkeypatch):
    frame = make_frame([100.0, 110.0])
    state = {"n": 0}

    class Flaky(FakeTicker):
        def history(self, **kwargs):
            state["n"] += 1
            if state["n"] < 3:
                raise Exception("503 Service Unavailable")
            return frame

    monkeypatch.setattr("briefbot.market_data._make_ticker", lambda s, sess: Flaky())
    snap = fetch_ticker(Holding(symbol="AAA"), attempts=3, sleep=lambda _: None, include_fundamentals=False)

    assert snap.ok
    assert state["n"] == 3


def test_broken_fundamentals_do_not_fail_the_ticker(monkeypatch):
    class BadInfo(FakeTicker):
        def get_info(self):
            raise RuntimeError("Yahoo said no")

        @property
        def fast_info(self):
            raise RuntimeError("also no")

    monkeypatch.setattr(
        "briefbot.market_data._make_ticker",
        lambda s, sess: BadInfo(frame=make_frame([100.0, 110.0])),
    )
    snap = fetch_ticker(Holding(symbol="AAA"), include_fundamentals=True)

    assert snap.ok
    assert snap.change_pct == pytest.approx(10.0)
    assert snap.sector is None


def test_dividend_yield_prefers_rate_over_price():
    # Real AAPL fields, 2026-07-31. Reading dividendYield's scale wrong here
    # would report a 0.35% yield as 35%.
    info = {
        "dividendRate": 1.08,
        "currentPrice": 308.91,
        "dividendYield": 0.35,
        "trailingAnnualDividendYield": 0.00077977387,
    }
    assert _dividend_yield_pct(info) == pytest.approx(0.3496, abs=1e-3)


def test_dividend_yield_falls_back_to_the_trailing_fraction():
    # Real XLE fields: an ETF, so no dividendRate is published.
    info = {"trailingAnnualDividendYield": 0.036635008, "dividendYield": 2.85}
    assert _dividend_yield_pct(info) == pytest.approx(3.6635, abs=1e-3)


def test_dividend_yield_last_resort_reads_the_current_percent_format():
    assert _dividend_yield_pct({"dividendYield": 2.4}) == pytest.approx(2.4)


def test_dividend_yield_is_none_when_nothing_is_published():
    assert _dividend_yield_pct({}) is None


def test_dividend_yield_survives_a_zero_price():
    assert _dividend_yield_pct({"dividendRate": 1.0, "currentPrice": 0}) is None


def test_dividend_yield_reaches_the_snapshot(monkeypatch):
    monkeypatch.setattr(
        "briefbot.market_data._make_ticker",
        lambda s, sess: FakeTicker(
            frame=make_frame([100.0, 110.0]),
            info={"dividendRate": 6.0, "currentPrice": 351.79},
        ),
    )
    snap = fetch_ticker(Holding(symbol="JPM"))
    assert snap.dividend_yield_pct == pytest.approx(1.706, abs=1e-3)


def test_one_bad_ticker_does_not_stop_the_watchlist(patch_ticker, settings):
    patch_ticker(
        {
            "AAA": FakeTicker(frame=make_frame([100.0, 110.0])),
            "BBB": FakeTicker(exc=Exception("No data found, symbol may be delisted")),
        }
    )
    wl = Watchlist(name="t", holdings=(Holding(symbol="AAA"), Holding(symbol="BBB")))

    result = fetch_watchlist(wl, settings, now_et=datetime(2026, 7, 31, 18, 0, tzinfo=EASTERN), include_fundamentals=False)

    assert len(result.ok_snapshots) == 1
    assert len(result.failed_snapshots) == 1
    assert any("BBB" in w for w in result.warnings)


@pytest.mark.parametrize(
    "text,expected",
    [
        ("No data found for this date range", True),
        ("AAA: possibly delisted; symbol may be delisted", True),
        ("404 Client Error", True),
        ("429 Too Many Requests", False),
        ("Connection reset by peer", False),
    ],
)
def test_not_found_detection(text, expected):
    assert _is_not_found(Exception(text)) is expected


# ---------------------------------------------------------------------------
# Snapshot-level behaviour
# ---------------------------------------------------------------------------


def test_movers_are_ranked_by_absolute_move():
    snap = make_snapshot(
        [
            TickerSnapshot(symbol="A", change_pct=1.0, session_date=date(2026, 7, 31)),
            TickerSnapshot(symbol="B", change_pct=-9.0, session_date=date(2026, 7, 31)),
            TickerSnapshot(symbol="C", change_pct=4.0, session_date=date(2026, 7, 31)),
        ]
    )
    assert [s.symbol for s in snap.movers(limit=2)] == ["B", "C"]


def test_stale_data_is_detected(monkeypatch):
    # Latest bar is Wednesday, but it is Friday evening — two sessions behind.
    friday_evening = datetime(2026, 7, 31, 18, 0, tzinfo=EASTERN)
    snap = make_snapshot(
        [TickerSnapshot(symbol="A", change_pct=1.0, session_date=date(2026, 7, 29))],
        now_et=friday_evening,
    )
    assert snap.is_stale


def test_fresh_data_is_not_stale():
    snap = make_snapshot()
    assert not snap.is_stale


def test_open_market_produces_a_partial_session_warning(patch_ticker, settings):
    patch_ticker({"AAA": FakeTicker(frame=make_frame([100.0, 110.0]))})
    wl = Watchlist(name="t", holdings=(Holding(symbol="AAA"),))

    result = fetch_watchlist(
        wl, settings, now_et=datetime(2026, 7, 31, 11, 0, tzinfo=EASTERN), include_fundamentals=False
    )

    assert any("market is open" in w for w in result.warnings)


def test_total_data_failure_is_warned_about(patch_ticker, settings):
    patch_ticker({"AAA": FakeTicker(exc=Exception("No data found"))})
    wl = Watchlist(name="t", holdings=(Holding(symbol="AAA"),))

    result = fetch_watchlist(wl, settings, include_fundamentals=False)

    assert result.ok_snapshots == []
    assert any("no market data" in w for w in result.warnings)


def test_by_symbol_is_case_insensitive():
    snap = make_snapshot()
    assert snap.by_symbol("aaa") is not None
    assert snap.by_symbol("nope") is None


def test_summarize_includes_numbers_and_caveats():
    snap = make_snapshot()
    snap.warnings.append("a test caveat")
    text = summarize_for_prompt(snap)

    assert "AAA" in text
    assert "+11.11%" in text
    assert "2.50x 20d avg" in text
    assert "a test caveat" in text


def test_summarize_flags_missing_tickers():
    snap = make_snapshot(
        [TickerSnapshot(symbol="ZZZ", ok=False, error="not found — nope")]
    )
    assert "NO DATA" in summarize_for_prompt(snap)


# ---------------------------------------------------------------------------
# Session construction
# ---------------------------------------------------------------------------


def test_no_session_is_built_on_a_plain_network():
    assert build_session(Settings()) is None


def test_a_session_is_built_when_a_proxy_is_configured():
    session = build_session(Settings(proxy="http://127.0.0.1:8080"))
    assert session is not None
