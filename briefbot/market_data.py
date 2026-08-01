"""Step 1 — pull price, volume and basic fundamentals from yfinance.

Everything numeric in the brief is computed here, in plain Python, from raw
OHLCV bars. The LLM steps downstream are handed finished numbers and are never
asked to do arithmetic.

Design notes worth keeping in mind:

* yfinance is an unofficial Yahoo wrapper. It fails in scrappy ways — rate
  limits, empty frames, occasional garbage. Every call goes through a retry,
  and a ticker that still fails is recorded as an error rather than allowed to
  take down the run.
* Fundamentals are strictly best-effort. ``Ticker.info`` is the slowest and
  flakiest surface yfinance exposes; if it fails the brief simply goes out
  without a P/E.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Iterable, Sequence

from .config import Holding, Settings, Watchlist
from .errors import MarketDataError, TickerNotFound
from .market_clock import EASTERN, MarketStatus, market_status
from .retry import retry_call

log = logging.getLogger(__name__)

# A year of daily bars covers the 52-week range and every lookback below with
# room to spare for holidays.
HISTORY_PERIOD = "1y"

# Signals that Yahoo knows nothing about this symbol, as opposed to a transient
# failure. Matched case-insensitively against the exception text.
_NOT_FOUND_MARKERS = (
    "no data found",
    "symbol may be delisted",
    "no price data found",
    "not found",
    "404",
)


def _is_not_found(exc: BaseException) -> bool:
    text = str(exc).lower()
    return any(marker in text for marker in _NOT_FOUND_MARKERS)


def _clean(value: Any) -> float | None:
    """Coerce a yfinance cell to a real float, or None."""

    if value is None:
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(out) or math.isinf(out):
        return None
    return out


def _pct_change(current: float | None, past: float | None) -> float | None:
    if current is None or past in (None, 0):
        return None
    return (current / past - 1.0) * 100.0


@dataclass
class TickerSnapshot:
    """One ticker's numbers for the brief. All percentages are in percent."""

    symbol: str
    label: str = ""
    why: str = ""

    ok: bool = True
    error: str | None = None

    # Latest completed bar
    session_date: date | None = None
    close: float | None = None
    prev_close: float | None = None
    day_open: float | None = None
    day_high: float | None = None
    day_low: float | None = None
    volume: float | None = None

    # Derived
    change_abs: float | None = None
    change_pct: float | None = None
    change_5d_pct: float | None = None
    change_21d_pct: float | None = None
    change_ytd_pct: float | None = None
    avg_volume_20d: float | None = None
    volume_ratio: float | None = None
    high_52w: float | None = None
    low_52w: float | None = None
    pct_from_52w_high: float | None = None
    intraday_range_pct: float | None = None

    # Best-effort fundamentals
    name: str | None = None
    currency: str | None = None
    sector: str | None = None
    industry: str | None = None
    market_cap: float | None = None
    trailing_pe: float | None = None
    forward_pe: float | None = None
    dividend_yield_pct: float | None = None
    quote_type: str | None = None

    bars_used: int = 0

    @property
    def display_name(self) -> str:
        return self.label or self.name or self.symbol

    @property
    def is_notable_move(self) -> bool:
        """A day worth explaining in prose rather than just tabulating."""

        if self.change_pct is None:
            return False
        if abs(self.change_pct) >= 2.0:
            return True
        return bool(self.volume_ratio and self.volume_ratio >= 1.75)


@dataclass
class MarketSnapshot:
    """The whole watchlist's numbers plus the context they were taken in."""

    generated_at: datetime
    status: MarketStatus
    snapshots: list[TickerSnapshot] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok_snapshots(self) -> list[TickerSnapshot]:
        return [s for s in self.snapshots if s.ok]

    @property
    def failed_snapshots(self) -> list[TickerSnapshot]:
        return [s for s in self.snapshots if not s.ok]

    @property
    def latest_session(self) -> date | None:
        dates = [s.session_date for s in self.ok_snapshots if s.session_date]
        return max(dates) if dates else None

    @property
    def is_stale(self) -> bool:
        """True when the newest bar predates the session we expected to see.

        This is the catch-all that covers unscheduled closures and Yahoo simply
        not having posted the day yet.
        """

        latest = self.latest_session
        if latest is None:
            return False
        return latest < self.status.expected_latest_session

    def movers(self, limit: int = 3) -> list[TickerSnapshot]:
        ranked = [s for s in self.ok_snapshots if s.change_pct is not None]
        ranked.sort(key=lambda s: abs(s.change_pct or 0.0), reverse=True)
        return ranked[:limit]

    def by_symbol(self, symbol: str) -> TickerSnapshot | None:
        for s in self.snapshots:
            if s.symbol == symbol.upper():
                return s
        return None


# --------------------------------------------------------------------------
# yfinance plumbing
# --------------------------------------------------------------------------


def build_session(settings: Settings):
    """Build an HTTP session for yfinance, or None to use its default.

    Only needed when the environment forces a proxy or a non-Chrome TLS
    fingerprint. On an ordinary network this returns None and yfinance behaves
    exactly as it does out of the box.
    """

    if not settings.proxy and not settings.yf_impersonate:
        return None

    try:
        from curl_cffi import requests as curl_requests
    except ImportError:  # pragma: no cover - curl_cffi ships with yfinance
        log.warning("curl_cffi unavailable; falling back to the default yfinance session")
        return None

    kwargs: dict[str, Any] = {"impersonate": settings.yf_impersonate or "safari"}
    if settings.proxy:
        kwargs["proxies"] = {"https": settings.proxy, "http": settings.proxy}
    log.debug("building yfinance session (impersonate=%s, proxy=%s)", kwargs["impersonate"], bool(settings.proxy))
    return curl_requests.Session(**kwargs)


def _make_ticker(symbol: str, session: Any):
    import yfinance as yf

    return yf.Ticker(symbol, session=session) if session is not None else yf.Ticker(symbol)


def _fetch_history(ticker: Any, symbol: str):
    frame = ticker.history(period=HISTORY_PERIOD, auto_adjust=False)
    if frame is None or frame.empty:
        raise TickerNotFound(symbol, "yfinance returned an empty frame")
    return frame


def _fetch_fundamentals(ticker: Any) -> dict[str, Any]:
    """Best-effort. Never raises — a missing P/E is not worth a failed run."""

    out: dict[str, Any] = {}

    try:
        fast = ticker.fast_info
        for key in ("currency", "market_cap", "quote_type", "last_price"):
            try:
                value = fast[key] if key in fast else getattr(fast, key, None)
            except Exception:  # noqa: BLE001 - fast_info raises many shapes
                value = None
            if value is not None:
                out[key] = value
    except Exception as exc:  # noqa: BLE001
        log.debug("fast_info unavailable: %s", exc)

    try:
        info = ticker.get_info() or {}
    except Exception as exc:  # noqa: BLE001
        log.debug("get_info unavailable: %s", exc)
        info = {}

    for key in (
        "longName",
        "shortName",
        "sector",
        "industry",
        "marketCap",
        "trailingPE",
        "forwardPE",
        "dividendYield",
        "quoteType",
        "currency",
    ):
        if info.get(key) is not None:
            out[key] = info[key]

    return out


# --------------------------------------------------------------------------
# Metric computation
# --------------------------------------------------------------------------


def compute_metrics(snapshot: TickerSnapshot, frame: Any) -> TickerSnapshot:
    """Fill ``snapshot`` from a daily OHLCV DataFrame.

    Split out from fetching so the maths is testable against a hand-built
    frame with no network anywhere near it.
    """

    closes = [_clean(v) for v in frame["Close"].tolist()]
    volumes = [_clean(v) for v in frame["Volume"].tolist()] if "Volume" in frame else []
    highs = [_clean(v) for v in frame["High"].tolist()] if "High" in frame else []
    lows = [_clean(v) for v in frame["Low"].tolist()] if "Low" in frame else []
    opens = [_clean(v) for v in frame["Open"].tolist()] if "Open" in frame else []

    index = list(frame.index)
    snapshot.bars_used = len(index)

    if not closes or closes[-1] is None:
        raise TickerNotFound(snapshot.symbol, "no usable closing prices")

    last_index = index[-1]
    snapshot.session_date = last_index.date() if hasattr(last_index, "date") else None

    snapshot.close = closes[-1]
    snapshot.prev_close = closes[-2] if len(closes) >= 2 else None
    snapshot.day_open = opens[-1] if opens else None
    snapshot.day_high = highs[-1] if highs else None
    snapshot.day_low = lows[-1] if lows else None
    snapshot.volume = volumes[-1] if volumes else None

    if snapshot.close is not None and snapshot.prev_close:
        snapshot.change_abs = snapshot.close - snapshot.prev_close
        snapshot.change_pct = _pct_change(snapshot.close, snapshot.prev_close)

    # Lookbacks are in trading days: 5 ~ a week, 21 ~ a month.
    for attr, lookback in (("change_5d_pct", 5), ("change_21d_pct", 21)):
        if len(closes) > lookback:
            setattr(snapshot, attr, _pct_change(snapshot.close, closes[-1 - lookback]))

    # Year to date: the last close of the previous calendar year, if the
    # window reaches back that far.
    if snapshot.session_date is not None:
        year = snapshot.session_date.year
        prior_year_closes = [
            c
            for ts, c in zip(index, closes)
            if c is not None and hasattr(ts, "year") and ts.year < year
        ]
        if prior_year_closes:
            snapshot.change_ytd_pct = _pct_change(snapshot.close, prior_year_closes[-1])

    # 20-day average volume, excluding the day being reported so the ratio
    # compares today against its own baseline rather than against itself.
    prior_volumes = [v for v in volumes[:-1] if v is not None]
    if len(prior_volumes) >= 5:
        window = prior_volumes[-20:]
        snapshot.avg_volume_20d = sum(window) / len(window)
        if snapshot.avg_volume_20d and snapshot.volume is not None:
            snapshot.volume_ratio = snapshot.volume / snapshot.avg_volume_20d

    clean_highs = [h for h in highs if h is not None]
    clean_lows = [low for low in lows if low is not None]
    if clean_highs:
        snapshot.high_52w = max(clean_highs)
        if snapshot.close is not None and snapshot.high_52w:
            snapshot.pct_from_52w_high = (snapshot.close / snapshot.high_52w - 1.0) * 100.0
    if clean_lows:
        snapshot.low_52w = min(clean_lows)

    if snapshot.day_high is not None and snapshot.day_low is not None and snapshot.prev_close:
        snapshot.intraday_range_pct = (snapshot.day_high - snapshot.day_low) / snapshot.prev_close * 100.0

    return snapshot


def _apply_fundamentals(snapshot: TickerSnapshot, info: dict[str, Any]) -> None:
    snapshot.name = info.get("longName") or info.get("shortName") or snapshot.name
    snapshot.currency = info.get("currency") or snapshot.currency
    snapshot.sector = info.get("sector")
    snapshot.industry = info.get("industry")
    snapshot.quote_type = info.get("quoteType") or info.get("quote_type")
    snapshot.market_cap = _clean(info.get("marketCap") or info.get("market_cap"))
    snapshot.trailing_pe = _clean(info.get("trailingPE"))
    snapshot.forward_pe = _clean(info.get("forwardPE"))

    raw_yield = _clean(info.get("dividendYield"))
    if raw_yield is not None:
        # yfinance has shipped this both as a fraction (0.0052) and as a
        # percentage (0.52) across versions. Anything under 1 is a fraction;
        # no listed equity yields 100%+.
        snapshot.dividend_yield_pct = raw_yield * 100.0 if raw_yield < 1 else raw_yield


# --------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------


def fetch_ticker(
    holding: Holding,
    *,
    session: Any = None,
    attempts: int = 3,
    sleep: Any = None,
    include_fundamentals: bool = True,
) -> TickerSnapshot:
    """Fetch and compute one ticker. Failures are returned, not raised."""

    snapshot = TickerSnapshot(symbol=holding.symbol, label=holding.label, why=holding.why)

    retry_kwargs: dict[str, Any] = {
        "attempts": attempts,
        "should_retry": lambda exc: not _is_not_found(exc),
        "label": f"yfinance history {holding.symbol}",
    }
    if sleep is not None:
        retry_kwargs["sleep"] = sleep

    try:
        ticker = _make_ticker(holding.symbol, session)
        frame = retry_call(lambda: _fetch_history(ticker, holding.symbol), **retry_kwargs)
        compute_metrics(snapshot, frame)
    except TickerNotFound as exc:
        snapshot.ok = False
        snapshot.error = f"not found — {exc.detail or 'no price history'}"
        log.warning("%s: %s", holding.symbol, snapshot.error)
        return snapshot
    except Exception as exc:  # noqa: BLE001 - one bad ticker must not end the run
        if _is_not_found(exc):
            snapshot.ok = False
            snapshot.error = "not found — Yahoo has no data for this symbol"
        else:
            snapshot.ok = False
            snapshot.error = f"fetch failed — {type(exc).__name__}: {exc}"
        log.warning("%s: %s", holding.symbol, snapshot.error)
        return snapshot

    if include_fundamentals:
        try:
            _apply_fundamentals(snapshot, _fetch_fundamentals(ticker))
        except Exception as exc:  # noqa: BLE001
            log.debug("%s: fundamentals skipped (%s)", holding.symbol, exc)

    return snapshot


def fetch_watchlist(
    watchlist: Watchlist,
    settings: Settings,
    *,
    now_et: datetime | None = None,
    session: Any = None,
    attempts: int = 3,
    include_fundamentals: bool = True,
) -> MarketSnapshot:
    """Fetch every ticker in the watchlist and assemble the snapshot."""

    if session is None:
        session = build_session(settings)

    status = market_status(now_et)
    result = MarketSnapshot(generated_at=datetime.now(EASTERN), status=status)

    for holding in watchlist.holdings:
        log.info("fetching %s", holding.symbol)
        result.snapshots.append(
            fetch_ticker(
                holding,
                session=session,
                attempts=attempts,
                include_fundamentals=include_fundamentals,
            )
        )

    result.warnings.extend(_collect_warnings(result))
    return result


def _collect_warnings(snapshot: MarketSnapshot) -> list[str]:
    warnings: list[str] = []

    failed = snapshot.failed_snapshots
    if failed:
        names = ", ".join(f"{s.symbol} ({s.error})" for s in failed)
        warnings.append(f"{len(failed)} of {len(snapshot.snapshots)} tickers failed: {names}")

    if not snapshot.ok_snapshots:
        warnings.append("no market data was retrieved for any ticker")
        return warnings

    if snapshot.is_stale:
        latest = snapshot.latest_session
        expected = snapshot.status.expected_latest_session
        warnings.append(
            f"latest bar is {latest}, but the most recent expected session was {expected} — "
            "data may be delayed, or the market was unexpectedly closed"
        )

    if snapshot.status.is_open:
        warnings.append(
            "the market is open right now, so the latest bar is a partial session and "
            "its close and volume will keep moving"
        )

    sessions = {s.session_date for s in snapshot.ok_snapshots if s.session_date}
    if len(sessions) > 1:
        warnings.append(
            "tickers do not share a single latest session date "
            f"({', '.join(str(d) for d in sorted(sessions))}) — likely a mixed-exchange watchlist"
        )

    return warnings


def summarize_for_prompt(snapshot: MarketSnapshot, holdings: Sequence[Holding] | None = None) -> str:
    """A compact plain-text rendering of the numbers, for LLM consumption.

    Kept separate from the markdown renderer: this one optimises for the model
    reading it accurately, not for a human reading it prettily.
    """

    lines: list[str] = []
    lines.append(f"As of: {snapshot.status.describe()}")
    if snapshot.latest_session:
        lines.append(f"Latest completed session in the data: {snapshot.latest_session}")
    lines.append("")

    for s in snapshot.ok_snapshots:
        parts = [f"{s.symbol} ({s.display_name})"]
        if s.close is not None:
            parts.append(f"close {s.close:,.2f}")
        if s.change_pct is not None:
            parts.append(f"1d {s.change_pct:+.2f}%")
        if s.change_5d_pct is not None:
            parts.append(f"5d {s.change_5d_pct:+.2f}%")
        if s.change_21d_pct is not None:
            parts.append(f"21d {s.change_21d_pct:+.2f}%")
        if s.change_ytd_pct is not None:
            parts.append(f"YTD {s.change_ytd_pct:+.2f}%")
        if s.volume_ratio is not None:
            parts.append(f"volume {s.volume_ratio:.2f}x 20d avg")
        if s.pct_from_52w_high is not None:
            parts.append(f"{s.pct_from_52w_high:+.1f}% vs 52w high")
        if s.sector:
            parts.append(f"sector {s.sector}")
        if s.market_cap:
            parts.append(f"mkt cap {s.market_cap / 1e9:,.1f}B")
        if s.trailing_pe:
            parts.append(f"trailing P/E {s.trailing_pe:.1f}")
        if s.why:
            parts.append(f"on the list for: {s.why}")
        lines.append("- " + "; ".join(parts))

    for s in snapshot.failed_snapshots:
        lines.append(f"- {s.symbol}: NO DATA ({s.error})")

    if snapshot.warnings:
        lines.append("")
        lines.append("Data caveats:")
        lines.extend(f"- {w}" for w in snapshot.warnings)

    return "\n".join(lines)


def iter_symbols(holdings: Iterable[Holding]) -> list[str]:
    return [h.symbol for h in holdings]
