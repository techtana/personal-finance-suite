"""Recurring rule dates: a rule keeps its own day, short months clamp to their last day."""

import pytest

from engine.recurrence import expand_recurring_dates as expand


def test_rule_started_before_the_window_keeps_its_own_day():
    assert expand("2026-01-05", None, "monthly", "2026-02-01", "2026-03-15") == ["2026-02-05", "2026-03-05"]
    # A window that opens on "today" must not move the rule to today's day number.
    assert expand("2025-03-20", None, "monthly", "2026-11-25", "2027-01-31") == \
        ["2026-12-20", "2027-01-20"]


def test_weekly_and_biweekly_stay_on_the_start_dates_cycle():
    assert expand("2026-01-02", None, "biweekly", "2026-02-01", "2026-03-01") == ["2026-02-13", "2026-02-27"]
    assert expand("2026-01-02", None, "weekly", "2026-01-10", "2026-01-24") == ["2026-01-16", "2026-01-23"]
    assert expand("2026-01-30", None, "daily", "2026-02-01", "2026-02-03") == \
        ["2026-02-01", "2026-02-02", "2026-02-03"]


def test_month_end_rules_clamp_to_short_months_without_drifting():
    assert expand("2026-01-31", None, "monthly", "2026-01-01", "2026-06-30") == \
        ["2026-01-31", "2026-02-28", "2026-03-31", "2026-04-30", "2026-05-31", "2026-06-30"]
    assert expand("2025-11-30", None, "quarterly", "2026-01-01", "2026-12-31") == \
        ["2026-02-28", "2026-05-30", "2026-08-30", "2026-11-30"]
    assert expand("2024-02-29", None, "annually", "2025-01-01", "2028-12-31") == \
        ["2025-02-28", "2026-02-28", "2027-02-28", "2028-02-29"]


def test_start_end_and_window_limits():
    # Starts inside the window: first date is the start itself.
    assert expand("2026-03-10", None, "monthly", "2026-01-01", "2026-05-31") == \
        ["2026-03-10", "2026-04-10", "2026-05-10"]
    # The rule's end date and the window end are both inclusive.
    assert expand("2026-01-15", "2026-03-15", "monthly", "2026-01-01", "2026-12-31") == \
        ["2026-01-15", "2026-02-15", "2026-03-15"]
    assert expand("2026-01-15", "2025-12-31", "monthly", "2026-01-01", "2026-12-31") == []  # ended before it began
    assert expand("2026-01-15", "2026-05-01", "monthly", "2026-06-01", "2026-12-31") == []  # ended before the window
    assert expand("2027-01-15", None, "monthly", "2026-01-01", "2026-12-31") == []          # starts after it


@pytest.mark.parametrize("args", [
    ("2026-01-01", None, "fortnightly", "2026-01-01", "2026-12-31"),
    ("not-a-date", None, "monthly", "2026-01-01", "2026-12-31"),
])
def test_unknown_frequency_or_bad_date_gives_nothing(args):
    assert expand(*args) == []
