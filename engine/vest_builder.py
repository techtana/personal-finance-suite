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
        List of {date: str, shares: int} vest events whose shares sum to total_shares,
        or [] when the inputs can't make a schedule (bad date, frequency or percents).
    """
    try:
        start_dt = datetime.strptime(grant_date, "%Y-%m-%d")
    except ValueError:
        return []

    if subsequent_frequency not in ("monthly", "quarterly"):
        return []
    if not 0 <= cliff_percent <= 10000 or subsequent_percent < 0:
        return []

    # Whole basis points avoid float drift. Percents that don't divide the remainder
    # evenly (the Plan form's default 2.0833 % arrives as 208 bps) still vest the whole
    # grant: the number of later vests is rounded to the nearest whole count and the
    # last vest takes whatever is left, so the shares always add up to total_shares.
    remaining_bps = 10000 - cliff_percent
    if remaining_bps == 0:
        num_subsequent = 0
    elif subsequent_percent == 0:
        return []  # nothing would ever vest after the cliff
    else:
        num_subsequent = max(1, (2 * remaining_bps + subsequent_percent) // (2 * subsequent_percent))

    cliff_dt = start_dt + relativedelta(months=cliff_months)
    schedule = []
    if cliff_percent:
        schedule.append({"date": cliff_dt.date().isoformat(), "shares": total_shares * cliff_percent // 10000})

    subsequent_shares = total_shares * subsequent_percent // 10000
    months_between = 1 if subsequent_frequency == "monthly" else 3
    for i in range(num_subsequent):
        vest_date = (cliff_dt + relativedelta(months=months_between * (i + 1))).date().isoformat()
        schedule.append({"date": vest_date, "shares": subsequent_shares})

    # The last vest absorbs the rounding so nothing is lost or over-vested.
    if schedule:
        schedule[-1]["shares"] = total_shares - sum(v["shares"] for v in schedule[:-1])
    return schedule
