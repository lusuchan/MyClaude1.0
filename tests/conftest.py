"""Shared fixtures.

Nothing in the default test run touches the network. The live smoke tests in
``test_live.py`` are opt-in and marked ``live``.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from briefbot.config import Holding, Settings, Watchlist
from briefbot.market_clock import EASTERN, market_status
from briefbot.market_data import MarketSnapshot, TickerSnapshot


def make_frame(
    closes: list[float],
    *,
    end: date = date(2026, 7, 31),
    volumes: list[float] | None = None,
    highs: list[float] | None = None,
    lows: list[float] | None = None,
    opens: list[float] | None = None,
) -> pd.DataFrame:
    """Build a daily OHLCV frame shaped like the one yfinance returns.

    Business-day index so lookbacks land where a reader would expect.
    """

    n = len(closes)
    index = pd.bdate_range(end=pd.Timestamp(end), periods=n, tz="America/New_York")
    return pd.DataFrame(
        {
            "Open": opens or [c * 0.995 for c in closes],
            "High": highs or [c * 1.01 for c in closes],
            "Low": lows or [c * 0.99 for c in closes],
            "Close": closes,
            "Volume": volumes or [1_000_000.0] * n,
        },
        index=index,
    )


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(api_key="test-key", model="test-model", output_dir=tmp_path / "briefs")


@pytest.fixture
def watchlist() -> Watchlist:
    return Watchlist(
        name="test watchlist",
        holdings=(
            Holding(symbol="AAA", label="Alpha Corp", why="test name"),
            Holding(symbol="BBB", label="Beta Inc", why="second test name"),
        ),
    )


def make_snapshot(
    tickers: list[TickerSnapshot] | None = None,
    *,
    now_et: datetime | None = None,
) -> MarketSnapshot:
    now = now_et or datetime(2026, 7, 31, 18, 0, tzinfo=EASTERN)
    if tickers is None:
        tickers = [
            TickerSnapshot(
                symbol="AAA",
                label="Alpha Corp",
                session_date=date(2026, 7, 31),
                close=100.0,
                prev_close=90.0,
                change_abs=10.0,
                change_pct=11.11,
                change_5d_pct=12.0,
                change_21d_pct=-3.0,
                change_ytd_pct=20.0,
                volume=5_000_000.0,
                avg_volume_20d=2_000_000.0,
                volume_ratio=2.5,
                pct_from_52w_high=-4.0,
                sector="Technology",
            ),
            TickerSnapshot(
                symbol="BBB",
                label="Beta Inc",
                session_date=date(2026, 7, 31),
                close=50.0,
                prev_close=50.1,
                change_abs=-0.1,
                change_pct=-0.2,
                volume=900_000.0,
                volume_ratio=0.9,
            ),
        ]
    snapshot = MarketSnapshot(generated_at=now, status=market_status(now), snapshots=list(tickers))
    return snapshot


@pytest.fixture
def snapshot() -> MarketSnapshot:
    return make_snapshot()


# ---------------------------------------------------------------------------
# Fake Anthropic client
# ---------------------------------------------------------------------------


def text_block(text: str, citations: list[tuple[str, str]] | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        type="text",
        text=text,
        citations=[SimpleNamespace(url=url, title=title) for url, title in (citations or [])],
    )


def search_result_block(results: list[tuple[str, str]]) -> SimpleNamespace:
    return SimpleNamespace(
        type="web_search_tool_result",
        content=[SimpleNamespace(url=url, title=title) for url, title in results],
    )


def tool_use_block() -> SimpleNamespace:
    return SimpleNamespace(type="server_tool_use", name="web_search")


def make_message(content: list, *, stop_reason: str = "end_turn") -> SimpleNamespace:
    return SimpleNamespace(
        content=content,
        stop_reason=stop_reason,
        usage=SimpleNamespace(input_tokens=100, output_tokens=200),
    )


class FakeMessages:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if not self._responses:
            raise AssertionError("FakeMessages ran out of scripted responses")
        item = self._responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class FakeAnthropic:
    """Stands in for ``anthropic.Anthropic``. Scripted, never networked."""

    def __init__(self, responses):
        self.messages = FakeMessages(responses)

    @property
    def calls(self) -> list[dict]:
        return self.messages.calls


@pytest.fixture
def no_sleep():
    """A sleep that records instead of waiting, so retry tests stay instant."""

    slept: list[float] = []
    return slept.append, slept


def days_ago(n: int, end: date = date(2026, 7, 31)) -> date:
    return end - timedelta(days=n)
