"""Recurring transaction date expansion."""

from datetime import datetime, timedelta
from dateutil.rrule import rrule, DAILY, WEEKLY, MONTHLY, YEARLY
from dateutil.relativedelta import relativedelta


def expand_recurring_dates(
    start_date: str, end_date: str | None, frequency: str, horizon_start: str, horizon_end: str
) -> list[str]:
    """
    Expand a recurring date pattern into all occurrences within a horizon.

    Args:
        start_date: ISO string (YYYY-MM-DD)
        end_date: ISO string or None for indefinite
        frequency: 'daily', 'weekly', 'biweekly', 'monthly', 'quarterly', 'annually'
        horizon_start: ISO string for projection start
        horizon_end: ISO string for projection end

    Returns:
        List of ISO date strings within [horizon_start, horizon_end]
    """
    try:
        dtstart = datetime.strptime(start_date, "%Y-%m-%d").date()
        until = None
        if end_date:
            until = datetime.strptime(end_date, "%Y-%m-%d").date()

        h_start = datetime.strptime(horizon_start, "%Y-%m-%d").date()
        h_end = datetime.strptime(horizon_end, "%Y-%m-%d").date()
    except ValueError:
        return []

    # Map frequency to rrule interval
    freq_map = {
        "daily": (DAILY, 1),
        "weekly": (WEEKLY, 1),
        "biweekly": (DAILY, 14),  # 14 days = 2 weeks
        "monthly": (MONTHLY, 1),
        "quarterly": (MONTHLY, 3),
        "annually": (YEARLY, 1),
    }

    if frequency not in freq_map:
        return []

    freq, interval = freq_map[frequency]

    # Generate rule: if start_date is before horizon_start, use horizon_start
    rule_start = max(dtstart, h_start)

    # Generate all occurrences
    rule = rrule(
        freq,
        dtstart=rule_start,
        until=min(until or h_end, h_end),
        interval=interval,
        count=None
    )

    dates = []
    for dt in rule:
        date_str = dt.date().isoformat()
        if h_start <= dt.date() <= h_end:
            dates.append(date_str)

    return dates


def get_month_range(date_str: str) -> tuple[str, str]:
    """Get first and last day of month for a given date."""
    dt = datetime.strptime(date_str, "%Y-%m-%d").date()
    first = dt.replace(day=1)
    last = first + relativedelta(months=1) - timedelta(days=1)
    return first.isoformat(), last.isoformat()
