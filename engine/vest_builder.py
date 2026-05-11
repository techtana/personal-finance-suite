"""RSU vest schedule builder."""

from datetime import datetime
from dateutil.relativedelta import relativedelta


def build_vest_schedule(
    grant_date: str,
    total_shares: int,
    cliff_months: int,
    cliff_percent: int,
    subsequent_frequency: str,
    subsequent_percent: int,
) -> list[dict]:
    """
    Build explicit vest schedule from cliff + subsequent parameters.

    Args:
        grant_date: ISO string (YYYY-MM-DD)
        total_shares: Total shares in grant (milliShares, × 1000)
        cliff_months: Months until cliff
        cliff_percent: Percent vested at cliff (× 100, e.g., 2500 = 25%)
        subsequent_frequency: 'monthly' or 'quarterly'
        subsequent_percent: Percent per subsequent vest (× 100)

    Returns:
        List of {date: str, shares: int} vest events
    """
    try:
        start_dt = datetime.strptime(grant_date, "%Y-%m-%d")
    except ValueError:
        return []

    # Validate percentages sum to 100%
    cliff_p = cliff_percent / 10000
    sub_p = subsequent_percent / 10000

    remaining_percent = 1.0 - cliff_p

    if subsequent_frequency not in ("monthly", "quarterly"):
        return []

    # Calculate number of subsequent vests needed
    if sub_p == 0:
        num_subsequent = 0
    else:
        num_subsequent = int(remaining_percent / sub_p)

    # Verify we don't have rounding issues
    total_vested = cliff_p + (sub_p * num_subsequent)
    if abs(total_vested - 1.0) > 0.001:
        return []

    schedule = []

    # Add cliff vest
    cliff_shares = int((total_shares * cliff_percent) / 10000)
    cliff_date = (start_dt + relativedelta(months=cliff_months)).date().isoformat()
    schedule.append({"date": cliff_date, "shares": cliff_shares})

    # Add subsequent vests
    subsequent_shares = int((total_shares * subsequent_percent) / 10000)
    months_between = 1 if subsequent_frequency == "monthly" else 3

    for i in range(num_subsequent):
        vest_date = (
            start_dt
            + relativedelta(months=cliff_months)
            + relativedelta(months=months_between * (i + 1))
        ).date().isoformat()
        schedule.append({"date": vest_date, "shares": subsequent_shares})

    return sorted(schedule, key=lambda x: x["date"])
