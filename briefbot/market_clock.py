"""US equity market calendar and session state.

The brief needs to say something honest at the top — "the market is closed for
Thanksgiving", "this is pre-market, yesterday's close is the latest print" —
rather than silently presenting stale numbers as if they were live.

NYSE holidays are rule-based, so they are computed rather than hardcoded to a
year. That keeps this correct without anyone having to remember to update a
table every January.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

EASTERN = ZoneInfo("America/New_York")

REGULAR_OPEN = time(9, 30)
REGULAR_CLOSE = time(16, 0)
EARLY_CLOSE = time(13, 0)
PREMARKET_OPEN = time(4, 0)
AFTER_HOURS_CLOSE = time(20, 0)


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    """The nth ``weekday`` (Mon=0) of a month. ``n=-1`` means the last one."""

    if n > 0:
        d = date(year, month, 1)
        offset = (weekday - d.weekday()) % 7
        return d + timedelta(days=offset + 7 * (n - 1))

    nxt = date(year + (month == 12), (month % 12) + 1, 1)
    d = nxt - timedelta(days=1)
    return d - timedelta(days=(d.weekday() - weekday) % 7)


def easter_sunday(year: int) -> date:
    """Gregorian Easter — needed only to locate Good Friday."""

    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    lam = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * lam) // 451
    month, day = divmod(h + lam - 7 * m + 114, 31)
    return date(year, month, day + 1)


def _observed(d: date) -> date:
    """Weekend holidays shift to the nearest weekday, NYSE-style."""

    if d.weekday() == 5:  # Saturday -> Friday
        return d - timedelta(days=1)
    if d.weekday() == 6:  # Sunday -> Monday
        return d + timedelta(days=1)
    return d


def market_holidays(year: int) -> dict[date, str]:
    """Full-day NYSE closures for ``year``.

    Excludes one-off closures (presidential funerals, hurricanes) — those are
    caught downstream by the stale-data check instead.
    """

    holidays = {
        _nth_weekday(year, 1, 0, 3): "Martin Luther King Jr. Day",
        _nth_weekday(year, 2, 0, 3): "Presidents' Day",
        easter_sunday(year) - timedelta(days=2): "Good Friday",
        _nth_weekday(year, 5, 0, -1): "Memorial Day",
        _observed(date(year, 6, 19)): "Juneteenth",
        _observed(date(year, 7, 4)): "Independence Day",
        _nth_weekday(year, 9, 0, 1): "Labor Day",
        _nth_weekday(year, 11, 3, 4): "Thanksgiving",
        _observed(date(year, 12, 25)): "Christmas Day",
    }

    # New Year's Day on a Saturday is the one case the NYSE does not shift:
    # it will not close the preceding Friday because that day is in the prior
    # year. Sunday still moves to Monday.
    new_year = date(year, 1, 1)
    if new_year.weekday() != 5:
        holidays[_observed(new_year)] = "New Year's Day"

    return holidays


def early_closes(year: int) -> dict[date, str]:
    """Scheduled 1:00pm ET closes."""

    out: dict[date, str] = {}

    july_3 = date(year, 7, 3)
    if july_3.weekday() < 5 and july_3 not in market_holidays(year):
        out[july_3] = "day before Independence Day"

    out[_nth_weekday(year, 11, 3, 4) + timedelta(days=1)] = "day after Thanksgiving"

    dec_24 = date(year, 12, 24)
    if dec_24.weekday() < 5:
        out[dec_24] = "Christmas Eve"

    return out


def is_trading_day(d: date) -> bool:
    return d.weekday() < 5 and d not in market_holidays(d.year)


def holiday_name(d: date) -> str | None:
    return market_holidays(d.year).get(d)


def previous_trading_day(d: date) -> date:
    d -= timedelta(days=1)
    while not is_trading_day(d):
        d -= timedelta(days=1)
    return d


def most_recent_trading_day(now_et: datetime) -> date:
    """The trading day whose regular session has already opened.

    Before 9:30am the answer is the previous session, which is what "latest
    close" means when the brief runs at 6am.
    """

    today = now_et.date()
    if is_trading_day(today) and now_et.time() >= REGULAR_OPEN:
        return today
    return previous_trading_day(today)


@dataclass(frozen=True)
class MarketStatus:
    """Where we are in the trading day, in plain language."""

    now_et: datetime
    state: str  # open | premarket | after_hours | closed | weekend | holiday
    note: str
    expected_latest_session: date

    @property
    def is_open(self) -> bool:
        return self.state == "open"

    def describe(self) -> str:
        stamp = self.now_et.strftime("%Y-%m-%d %H:%M ET")
        return f"{stamp} — {self.note}"


def market_status(now_et: datetime | None = None) -> MarketStatus:
    """Classify the current moment against the US equity session."""

    if now_et is None:
        now_et = datetime.now(EASTERN)
    elif now_et.tzinfo is None:
        now_et = now_et.replace(tzinfo=EASTERN)
    else:
        now_et = now_et.astimezone(EASTERN)

    today = now_et.date()
    clock = now_et.time()
    expected = most_recent_trading_day(now_et)

    if today.weekday() >= 5:
        return MarketStatus(now_et, "weekend", "market closed for the weekend", expected)

    name = holiday_name(today)
    if name:
        return MarketStatus(now_et, "holiday", f"market closed for {name}", expected)

    close_at = REGULAR_CLOSE
    early = early_closes(today.year).get(today)
    if early:
        close_at = EARLY_CLOSE

    if clock < PREMARKET_OPEN:
        return MarketStatus(now_et, "closed", "market closed overnight", expected)
    if clock < REGULAR_OPEN:
        return MarketStatus(now_et, "premarket", "pre-market — last regular close is the latest print", expected)
    if clock < close_at:
        note = "market open"
        if early:
            note = f"market open, early 1:00pm close ({early})"
        return MarketStatus(now_et, "open", note, expected)
    if clock < AFTER_HOURS_CLOSE:
        note = "after hours — today's regular session has closed"
        if early:
            note = f"after hours — early 1:00pm close today ({early})"
        return MarketStatus(now_et, "after_hours", note, expected)

    return MarketStatus(now_et, "closed", "market closed for the day", expected)
