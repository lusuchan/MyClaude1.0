"""The market calendar is computed from rules, so it needs checking against
dates a human has verified."""

from __future__ import annotations

from datetime import date, datetime

import pytest

from briefbot.market_clock import (
    EASTERN,
    early_closes,
    easter_sunday,
    holiday_name,
    is_trading_day,
    market_holidays,
    market_status,
    most_recent_trading_day,
    previous_trading_day,
)


@pytest.mark.parametrize(
    "year,expected",
    [
        (2024, date(2024, 3, 31)),
        (2025, date(2025, 4, 20)),
        (2026, date(2026, 4, 5)),
        (2027, date(2027, 3, 28)),
        (2030, date(2030, 4, 21)),
    ],
)
def test_easter_sunday(year, expected):
    assert easter_sunday(year) == expected


@pytest.mark.parametrize(
    "d,name",
    [
        (date(2026, 1, 1), "New Year's Day"),
        (date(2026, 1, 19), "Martin Luther King Jr. Day"),
        (date(2026, 2, 16), "Presidents' Day"),
        (date(2026, 4, 3), "Good Friday"),
        (date(2026, 5, 25), "Memorial Day"),
        (date(2026, 6, 19), "Juneteenth"),
        (date(2026, 7, 3), "Independence Day"),  # Jul 4 is a Saturday, observed Friday
        (date(2026, 9, 7), "Labor Day"),
        (date(2026, 11, 26), "Thanksgiving"),
        (date(2026, 12, 25), "Christmas Day"),
    ],
)
def test_known_2026_holidays(d, name):
    assert holiday_name(d) == name


@pytest.mark.parametrize(
    "d,name",
    [
        (date(2025, 1, 1), "New Year's Day"),
        (date(2025, 4, 18), "Good Friday"),
        (date(2025, 6, 19), "Juneteenth"),
        (date(2025, 7, 4), "Independence Day"),
        (date(2025, 11, 27), "Thanksgiving"),
        (date(2025, 12, 25), "Christmas Day"),
    ],
)
def test_known_2025_holidays(d, name):
    assert holiday_name(d) == name


def test_new_years_on_saturday_is_not_observed():
    # 2028-01-01 falls on a Saturday. The NYSE does not close the preceding
    # Friday for it, because that Friday belongs to the prior year.
    assert date(2028, 1, 1).weekday() == 5
    assert date(2027, 12, 31) not in market_holidays(2028)
    assert date(2027, 12, 31) not in market_holidays(2027)
    assert is_trading_day(date(2027, 12, 31))


def test_new_years_on_sunday_shifts_to_monday():
    assert date(2023, 1, 1).weekday() == 6
    assert holiday_name(date(2023, 1, 2)) == "New Year's Day"
    assert not is_trading_day(date(2023, 1, 2))


def test_juneteenth_on_a_sunday_shifts_forward():
    assert date(2027, 6, 19).weekday() == 5
    assert holiday_name(date(2027, 6, 18)) == "Juneteenth"


def test_trading_day_predicates():
    assert is_trading_day(date(2026, 7, 31))  # a Friday
    assert not is_trading_day(date(2026, 8, 1))  # Saturday
    assert not is_trading_day(date(2026, 12, 25))  # Christmas


def test_previous_trading_day_skips_the_weekend():
    assert previous_trading_day(date(2026, 8, 3)) == date(2026, 7, 31)


def test_previous_trading_day_skips_a_holiday():
    # Nov 27 2026 is the Friday after Thanksgiving (open, early close);
    # Nov 26 is the holiday itself.
    assert previous_trading_day(date(2026, 11, 27)) == date(2026, 11, 25)


def test_early_closes_include_the_day_after_thanksgiving():
    assert date(2026, 11, 27) in early_closes(2026)


@pytest.mark.parametrize(
    "when,state",
    [
        (datetime(2026, 7, 31, 3, 0), "closed"),
        (datetime(2026, 7, 31, 7, 0), "premarket"),
        (datetime(2026, 7, 31, 9, 29), "premarket"),
        (datetime(2026, 7, 31, 9, 30), "open"),
        (datetime(2026, 7, 31, 15, 59), "open"),
        (datetime(2026, 7, 31, 16, 0), "after_hours"),
        (datetime(2026, 7, 31, 19, 59), "after_hours"),
        (datetime(2026, 7, 31, 21, 0), "closed"),
        (datetime(2026, 8, 1, 12, 0), "weekend"),
        (datetime(2026, 8, 2, 12, 0), "weekend"),
        (datetime(2026, 12, 25, 12, 0), "holiday"),
    ],
)
def test_session_states(when, state):
    assert market_status(when.replace(tzinfo=EASTERN)).state == state


def test_early_close_day_flips_to_after_hours_at_one():
    friday_after_thanksgiving = datetime(2026, 11, 27, 13, 30, tzinfo=EASTERN)
    status = market_status(friday_after_thanksgiving)
    assert status.state == "after_hours"
    assert "early" in status.note


def test_holiday_note_names_the_holiday():
    status = market_status(datetime(2026, 12, 25, 10, 0, tzinfo=EASTERN))
    assert "Christmas" in status.note
    assert not status.is_open


def test_expected_session_before_the_open_is_the_prior_day():
    # 6am Monday: the latest close available is Friday's.
    monday_dawn = datetime(2026, 8, 3, 6, 0, tzinfo=EASTERN)
    assert most_recent_trading_day(monday_dawn) == date(2026, 7, 31)
    assert market_status(monday_dawn).expected_latest_session == date(2026, 7, 31)


def test_expected_session_after_the_open_is_today():
    monday_noon = datetime(2026, 8, 3, 12, 0, tzinfo=EASTERN)
    assert most_recent_trading_day(monday_noon) == date(2026, 8, 3)


def test_naive_datetimes_are_treated_as_eastern():
    naive = market_status(datetime(2026, 7, 31, 12, 0))
    assert naive.state == "open"


def test_utc_input_is_converted():
    from datetime import timezone

    # 20:00 UTC on a July weekday is 16:00 ET — just after the close.
    status = market_status(datetime(2026, 7, 31, 20, 30, tzinfo=timezone.utc))
    assert status.state == "after_hours"
