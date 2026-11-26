"""Recurring transaction date expansion."""

from datetime import datetime, timedelta
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

    # Day-based steps keep the start date's weekday; month-based steps keep its day
    # number, clamped to the last day of shorter months (Jan 31 -> Feb 28, Feb 29 ->
    # Feb 28 in common years). See docs/SRD.md section 9.4.
    day_steps = {"daily": 1, "weekly": 7, "biweekly": 14}
    month_steps = {"monthly": 1, "quarterly": 3, "annually": 12}
    if frequency not in day_steps and frequency not in month_steps:
        return []

    last = min(until, h_end) if until else h_end
    if last < h_start or last < dtstart:
        return []

    dates = []
    if frequency in day_steps:
        step = day_steps[frequency]
        # Occurrences stay on the rule's own anchor: jump to the first one on or after the window start.
        k = max(0, -(-(h_start - dtstart).days // step))
        d = dtstart + timedelta(days=k * step)
        while d <= last:
            dates.append(d.isoformat())
            d += timedelta(days=step)
        return dates

    step = month_steps[frequency]
    # Always offset from the original start (not the previous occurrence) so a clamped
    # month doesn't drag later ones off the 31st.
    months_to_window = (h_start.year - dtstart.year) * 12 + (h_start.month - dtstart.month)
    k = max(0, months_to_window // step - 1)
    while True:
        d = dtstart + relativedelta(months=k * step)
        if d > last:
            break
        if d >= h_start:
            dates.append(d.isoformat())
        k += 1
    return dates


def get_month_range(date_str: str) -> tuple[str, str]:
    """Get first and last day of month for a given date."""
    dt = datetime.strptime(date_str, "%Y-%m-%d").date()
    first = dt.replace(day=1)
    last = first + relativedelta(months=1) - timedelta(days=1)
    return first.isoformat(), last.isoformat()
