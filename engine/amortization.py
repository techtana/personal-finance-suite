"""Loan amortization calculations."""

from datetime import datetime
from dateutil.relativedelta import relativedelta


def calculate_monthly_payment(
    principal: int, annual_rate: int, months: int
) -> int:
    """
    Calculate monthly loan payment using standard amortization formula.

    Args:
        principal: Loan amount in minor units
        annual_rate: Annual interest rate (× 10000, e.g., 65000 = 6.5%)
        months: Number of months to amortize

    Returns:
        Monthly payment in minor units
    """
    if months <= 0 or annual_rate < 0:
        return 0

    monthly_rate_bps = annual_rate / 12  # basis points per month
    monthly_rate = monthly_rate_bps / 10000  # decimal

    if monthly_rate == 0:
        return principal // months

    # Standard formula: payment = principal * rate / (1 - (1 + rate)^-n)
    denominator = 1 - ((1 + monthly_rate) ** -months)
    if denominator <= 0:
        return 0

    payment = principal * monthly_rate / denominator
    return int(payment)


def calculate_payoff_date(
    start_date: str, principal: int, annual_rate: int, monthly_payment: int
) -> str:
    """
    Calculate loan payoff date given monthly payment.

    Args:
        start_date: Loan start date (YYYY-MM-DD)
        principal: Initial loan amount in minor units
        annual_rate: Annual interest rate (× 10000)
        monthly_payment: Monthly payment in minor units

    Returns:
        Payoff date as ISO string (YYYY-MM-DD)
    """
    try:
        current_date = datetime.strptime(start_date, "%Y-%m-%d")
    except ValueError:
        return start_date

    balance = principal
    monthly_rate = annual_rate / 120000  # annual_rate / 12 / 10000

    max_months = 600  # 50-year max to avoid infinite loops
    months_count = 0

    while balance > 0 and months_count < max_months:
        interest = int(balance * monthly_rate)
        principal_payment = monthly_payment - interest

        if principal_payment <= 0:
            break

        balance -= principal_payment
        current_date += relativedelta(months=1)
        months_count += 1

    return current_date.date().isoformat()


def amortize_loan(
    start_date: str,
    principal: int,
    annual_rate: int,
    monthly_payment: int,
    num_months: int,
) -> list[dict]:
    """
    Generate full amortization schedule.

    Args:
        start_date: Loan start date
        principal: Initial balance
        annual_rate: Annual rate (× 10000)
        monthly_payment: Monthly payment
        num_months: Number of months to amortize

    Returns:
        List of {date, beginning_balance, payment, principal, interest, ending_balance}
    """
    try:
        current_date = datetime.strptime(start_date, "%Y-%m-%d")
    except ValueError:
        return []

    schedule = []
    balance = principal
    monthly_rate = annual_rate / 120000

    for _ in range(num_months):
        beginning = balance
        interest = int(balance * monthly_rate)
        principal_payment = min(monthly_payment - interest, balance)
        ending = balance - principal_payment

        schedule.append(
            {
                "date": current_date.date().isoformat(),
                "beginning_balance": beginning,
                "payment": monthly_payment,
                "principal": principal_payment,
                "interest": interest,
                "ending_balance": max(0, ending),
            }
        )

        balance = max(0, ending)
        current_date += relativedelta(months=1)

        if balance == 0:
            break

    return schedule
