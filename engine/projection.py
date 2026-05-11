"""Core projection engine - expands financial objects into monthly cash flow."""

from datetime import datetime
from collections import defaultdict
from dataclasses import dataclass, field

from engine.recurrence import expand_recurring_dates


@dataclass
class CashFlowEvent:
    date: str
    source_id: str
    source_type: str
    type: str
    amount: int
    label: str
    category: str


@dataclass
class MonthlyBucket:
    month: str
    income: int = 0
    expenses: int = 0
    net_cash_flow: int = 0
    cumulative_net_worth: int = 0
    actual_net_worth: int | None = None
    events: list[CashFlowEvent] = field(default_factory=list)


def project(
    transactions: list,
    blanket_expenses: list,
    rsu_grants: list,
    espp_plans: list,
    accounts: list,
    loans: list,
    stock_prices: dict,
    from_date: str,
    to_date: str,
    disabled_ids: set | None = None,
) -> tuple[list[MonthlyBucket], list[CashFlowEvent]]:
    """
    Project net worth and cash flow from financial objects.

    Args:
        transactions: List of {id, type, amount, date, category, account_id} dicts
        blanket_expenses: List of {id, label, amount, frequency, start_date, end_date, category} dicts
        rsu_grants: List of {id, label, total_shares, ticker, vest_schedule, withholding_rate, account_id} dicts
        espp_plans: List of {id, label, purchase_periods, contribution_mode, ...} dicts
        accounts: List of {id, current_balance} dicts
        loans: List of {id, current_balance, interest_rate, monthly_payment, start_date} dicts
        stock_prices: Dict {ticker: price_in_minor_units}
        from_date: Start date (YYYY-MM-DD)
        to_date: End date (YYYY-MM-DD)
        disabled_ids: Set of IDs to exclude (scenario mode)

    Returns:
        (monthly_buckets, all_cash_flow_events)
    """
    if disabled_ids is None:
        disabled_ids = set()

    all_events = []

    # Expand one-time transactions (those with a specific date, no frequency)
    for txn in transactions:
        if txn["id"] in disabled_ids:
            continue
        if not txn.get("date"):  # skip recurring — handled in the loop below
            continue
        all_events.append(
            CashFlowEvent(
                date=txn["date"],
                source_id=txn["id"],
                source_type="transaction",
                type=txn["type"],
                amount=txn["amount"],
                label=txn.get("note", ""),
                category=txn.get("category", ""),
            )
        )

    # Expand recurring transactions
    for txn in transactions:
        if txn["id"] in disabled_ids or txn.get("frequency") is None:
            continue
        dates = expand_recurring_dates(
            txn["start_date"], txn.get("end_date"), txn["frequency"], from_date, to_date
        )
        for date_str in dates:
            all_events.append(
                CashFlowEvent(
                    date=date_str,
                    source_id=txn["id"],
                    source_type="recurring",
                    type=txn["type"],
                    amount=txn["amount"],
                    label=txn.get("note", ""),
                    category=txn.get("category", ""),
                )
            )

    # Expand blanket expenses
    for expense in blanket_expenses:
        if expense["id"] in disabled_ids:
            continue
        dates = expand_recurring_dates(
            expense["start_date"],
            expense.get("end_date"),
            expense["frequency"],
            from_date,
            to_date,
        )
        for date_str in dates:
            all_events.append(
                CashFlowEvent(
                    date=date_str,
                    source_id=expense["id"],
                    source_type="blanket",
                    type="expense",
                    amount=expense["amount"],
                    label=expense.get("label", ""),
                    category=expense.get("category", ""),
                )
            )

    # Expand RSU grants
    for grant in rsu_grants:
        if grant["id"] in disabled_ids:
            continue
        ticker = grant.get("ticker", "")
        stock_price = stock_prices.get(ticker, 0)

        for vest_event in grant.get("vest_schedule", []):
            vest_date = vest_event.get("date", "")
            if not (from_date <= vest_date <= to_date):
                continue

            shares_millis = vest_event.get("shares", 0)
            gross_value = (shares_millis * stock_price) // 1000
            withholding = (gross_value * grant.get("withholding_rate", 0)) // 10000
            net_value = gross_value - withholding

            if net_value > 0:
                all_events.append(
                    CashFlowEvent(
                        date=vest_date,
                        source_id=grant["id"],
                        source_type="rsu",
                        type="income",
                        amount=net_value,
                        label=f"{grant.get('label', '')} vest",
                        category="equity",
                    )
                )

    # Expand ESPP purchases
    for plan in espp_plans:
        if plan["id"] in disabled_ids:
            continue

        for period in plan.get("purchase_periods", []):
            end_date = period.get("end_date", "")
            if not (from_date <= end_date <= to_date):
                continue

            estimated = period.get("estimated_purchase_amount", 0)
            if estimated > 0:
                all_events.append(
                    CashFlowEvent(
                        date=end_date,
                        source_id=plan["id"],
                        source_type="espp",
                        type="income",
                        amount=estimated,
                        label=f"{plan.get('label', '')} purchase",
                        category="equity",
                    )
                )

    # Expand loan payments
    for loan in loans:
        if loan["id"] in disabled_ids:
            continue

        dates = expand_recurring_dates(
            loan["start_date"], loan.get("payoff_date"), "monthly", from_date, to_date
        )
        for date_str in dates:
            all_events.append(
                CashFlowEvent(
                    date=date_str,
                    source_id=loan["id"],
                    source_type="loan_payment",
                    type="expense",
                    amount=loan.get("monthly_payment", 0),
                    label=f"{loan.get('name', '')} payment",
                    category="debt",
                )
            )

    # Sort events by date
    all_events.sort(key=lambda e: e.date)

    # Bucket by month
    buckets = {}
    for event in all_events:
        month = event.date[:7]  # YYYY-MM
        if month not in buckets:
            buckets[month] = MonthlyBucket(month=month)

        bucket = buckets[month]
        bucket.events.append(event)

        if event.type == "income":
            bucket.income += event.amount
        else:
            bucket.expenses += event.amount

        bucket.net_cash_flow = bucket.income - bucket.expenses

    # Sort buckets and carry forward net worth
    sorted_months = sorted(buckets.keys())

    # Starting net worth
    starting_net_worth = sum(a.get("current_balance", 0) for a in accounts)
    starting_net_worth -= sum(l.get("current_balance", 0) for l in loans)

    cumulative_nw = starting_net_worth
    monthly_buckets = []

    for month in sorted_months:
        bucket = buckets[month]
        cumulative_nw += bucket.net_cash_flow
        bucket.cumulative_net_worth = cumulative_nw
        monthly_buckets.append(bucket)

    return monthly_buckets, all_events


def project_v2(
    rules: list,
    changes: list,
    loans: list,
    starting_net_worth: int,
    stock_prices: dict,
    from_date: str,
    to_date: str,
) -> tuple[list[MonthlyBucket], list[CashFlowEvent]]:
    """Project net worth using the simplified v2 schema (Rules + ChangeEvents).

    Args:
        rules: List of Rule dicts:
          {id, rule_type, amount, frequency, start_date, end_date, category, schedule, config}
        changes: List of ChangeEvent dicts:
          {id, date, description, amount, category, change_type}
        loans: List of Loan dicts (for auto loan payments):
          {id, name, current_balance, monthly_payment, start_date, payoff_date}
        starting_net_worth: Pre-computed net worth from latest snapshots (cents)
        stock_prices: {ticker: price_in_minor_units}
        from_date: Start date YYYY-MM-DD
        to_date: End date YYYY-MM-DD
    """
    all_events: list[CashFlowEvent] = []

    for rule in rules:
        if not rule.get("is_active", True):
            continue
        rt = rule.get("rule_type", "income")

        if rt in ("income", "expense"):
            freq = rule.get("frequency")
            if not freq:
                continue
            dates = expand_recurring_dates(
                rule["start_date"], rule.get("end_date"), freq, from_date, to_date
            )
            for d in dates:
                all_events.append(CashFlowEvent(
                    date=d,
                    source_id=rule["id"],
                    source_type="rule",
                    type=rt,
                    amount=rule.get("amount", 0),
                    label=rule.get("name", ""),
                    category=rule.get("category", ""),
                ))

        elif rt == "rsu":
            cfg = rule.get("config") or {}
            ticker = cfg.get("ticker", "")
            stock_price = stock_prices.get(ticker, 0)
            withholding_rate = cfg.get("withholding_rate", 0)
            for vest in (rule.get("schedule") or []):
                vest_date = vest.get("date", "")
                if not (from_date <= vest_date <= to_date):
                    continue
                shares_millis = vest.get("shares", 0)
                gross = (shares_millis * stock_price) // 1000
                net = gross - (gross * withholding_rate) // 10000
                if net > 0:
                    all_events.append(CashFlowEvent(
                        date=vest_date,
                        source_id=rule["id"],
                        source_type="rsu",
                        type="income",
                        amount=net,
                        label=rule.get("name", "") + " vest",
                        category="equity",
                    ))

        elif rt == "espp":
            for period in (rule.get("schedule") or []):
                end = period.get("end_date", "")
                if not (from_date <= end <= to_date):
                    continue
                est = period.get("estimated_purchase_amount", 0)
                if est and est > 0:
                    all_events.append(CashFlowEvent(
                        date=end,
                        source_id=rule["id"],
                        source_type="espp",
                        type="income",
                        amount=est,
                        label=rule.get("name", "") + " purchase",
                        category="equity",
                    ))

    # Manual change events
    for change in changes:
        amt = change.get("amount", 0)
        if amt == 0:
            continue
        all_events.append(CashFlowEvent(
            date=change["date"],
            source_id=change["id"],
            source_type="change",
            type="income" if amt > 0 else "expense",
            amount=abs(amt),
            label=change.get("description", ""),
            category=change.get("category", ""),
        ))

    # Auto loan payments
    for loan in loans:
        dates = expand_recurring_dates(
            loan["start_date"], loan.get("payoff_date"), "monthly", from_date, to_date
        )
        for d in dates:
            all_events.append(CashFlowEvent(
                date=d,
                source_id=loan["id"],
                source_type="loan_payment",
                type="expense",
                amount=loan.get("monthly_payment", 0),
                label=loan.get("name", "") + " payment",
                category="debt",
            ))

    all_events.sort(key=lambda e: e.date)

    buckets: dict[str, MonthlyBucket] = {}
    for event in all_events:
        month = event.date[:7]
        if month not in buckets:
            buckets[month] = MonthlyBucket(month=month)
        b = buckets[month]
        b.events.append(event)
        if event.type == "income":
            b.income += event.amount
        else:
            b.expenses += event.amount
        b.net_cash_flow = b.income - b.expenses

    cumulative_nw = starting_net_worth
    monthly_buckets: list[MonthlyBucket] = []
    for month in sorted(buckets.keys()):
        b = buckets[month]
        cumulative_nw += b.net_cash_flow
        b.cumulative_net_worth = cumulative_nw
        monthly_buckets.append(b)

    return monthly_buckets, all_events
