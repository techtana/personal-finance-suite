"""A small, fictional data set for tests and local previews.

The app no longer offers "Load sample data" (it replaced real data), so this lives with the
tests. Call load_sample_data() inside an app context; it replaces everything in the database.
"""

from datetime import date

from api.settings import LEGACY_TABLES, TABLES
from engine.vest_builder import build_vest_schedule
from models import Account, Asset, Category, ChangeEvent, Loan, PricePoint, Rule, Snapshot, db


def _months_ago(today: date, n: int, day: int = 1) -> str:
    y, m = today.year, today.month - n
    while m <= 0:
        y, m = y - 1, m + 12
    while m > 12:
        y, m = y + 1, m - 12
    return date(y, m, day).isoformat()


def load_sample_data():
    """Replace everything with a small, fictional data set that exercises every page."""
    for _, model in TABLES + LEGACY_TABLES:
        db.session.query(model).delete()

    today = date.today()
    iso = today.isoformat()
    for slug, label, kind, color in [
        ("salary", "Salary", "income", "#10b981"), ("bonus", "Bonus", "income", "#06b6d4"),
        ("equity", "Equity", "income", "#8b5cf6"), ("rent", "Rent", "expense", "#ef4444"),
        ("utilities", "Utilities", "expense", "#f59e0b"), ("groceries", "Groceries", "expense", "#f97316"),
        ("travel", "Travel", "expense", "#0ea5e9"), ("misc", "Misc", "expense", "#6b7280"),
        ("debt", "Debt", "expense", "#dc2626"),
    ]:
        db.session.add(Category(slug=slug, label=label, type=kind, color=color))

    checking = Account(name="Everyday Checking", type="checking", institution="Example Bank",
                       current_balance=1240000, last_updated_date=iso)
    savings = Account(name="High Yield Savings", type="savings", institution="Example Savings Bank",
                      current_balance=3150000, last_updated_date=_months_ago(today, 2, 15))
    k401 = Account(name="401(k)", type="retirement_401k", institution="Employer Plan",
                   current_balance=45000000, last_updated_date=iso)
    car_loan = Loan(name="Car Loan", type="auto", institution="Example Credit Union", original_balance=2800000,
                    current_balance=1460000, interest_rate=549, monthly_payment=53500,
                    start_date=_months_ago(today, 28), payoff_date=_months_ago(today, -8), last_updated_date=iso)
    fund = Asset(name="Total Market Index Fund", category="etf", ticker="VTI", quantity=410.0,
                 current_value=11890000, cost_basis=9200000, acquired_date=_months_ago(today, 30),
                 last_updated_date=iso, scheduled_events=[])
    car = Asset(name="Family Car", category="vehicle", current_value=1900000, cost_basis=3100000,
                acquired_date=_months_ago(today, 28), last_updated_date=_months_ago(today, 5, 10),
                scheduled_events=[])
    db.session.add_all([checking, savings, k401, car_loan, fund, car])
    db.session.flush()

    for n in range(13, 0, -1):
        when = _months_ago(today, n, 28)
        db.session.add(Snapshot(entity_type="cash", entity_id=checking.id, date=when, value=1240000 - n * 21000))
        db.session.add(Snapshot(entity_type="cash", entity_id=k401.id, date=when, value=45000000 - n * 610000))
        db.session.add(Snapshot(entity_type="asset", entity_id=fund.id, date=when, value=11890000 - n * 205000))
        db.session.add(Snapshot(entity_type="asset", entity_id=car.id, date=_months_ago(today, n, 10),
                                value=1900000 + max(0, n - 5) * 15000))
        db.session.add(Snapshot(entity_type="liability", entity_id=car_loan.id, date=when,
                                value=1460000 + n * 47000))
        if n >= 3:
            db.session.add(Snapshot(entity_type="cash", entity_id=savings.id, date=when,
                                    value=3150000 - (n - 2) * 50000))
    for obj, etype, field in ((checking, "cash", "current_balance"), (k401, "cash", "current_balance"),
                              (fund, "asset", "current_value"), (car_loan, "liability", "current_balance")):
        db.session.add(Snapshot(entity_type=etype, entity_id=obj.id, date=iso, value=getattr(obj, field)))

    start = _months_ago(today, 12)
    grant = _months_ago(today, 14, 15)
    db.session.add_all([
        Rule(name="Salary", rule_type="income", amount=1050000, frequency="monthly", start_date=start,
             category="salary", account_id=checking.id),
        Rule(name="Rent", rule_type="expense", amount=260000, frequency="monthly", start_date=start,
             category="rent", account_id=checking.id),
        Rule(name="Groceries", rule_type="expense", amount=90000, frequency="monthly", start_date=start,
             category="groceries", account_id=checking.id),
        Rule(name="Utilities", rule_type="expense", amount=24000, frequency="monthly", start_date=start,
             category="utilities", account_id=checking.id),
        Rule(name="Everything else", rule_type="expense", amount=180000, frequency="monthly", start_date=start,
             category="misc", account_id=checking.id),
        Rule(name="401(k) contribution", rule_type="expense", amount=150000, frequency="monthly", start_date=start,
             category="misc", account_id=k401.id, tax_treatment="pretax_401k"),
        Rule(name="Annual RSU grant", rule_type="rsu", start_date=grant, account_id=checking.id,
             schedule=build_vest_schedule(grant, 160000, 12, 2500, "quarterly", 625),
             config={"ticker": "EXMP", "total_shares": 160000, "grant_date": grant, "price_at_grant": 8200,
                     "withholding_rate": 2200, "cliff_months": 12, "cliff_percent": 2500,
                     "subsequent_frequency": "quarterly", "subsequent_percent": 625}),
        ChangeEvent(date=_months_ago(today, -2, 12), description="Family trip", amount=-420000, category="travel",
                    account_id=checking.id),
        ChangeEvent(date=_months_ago(today, -4, 1), description="Annual bonus", amount=900000, category="bonus",
                    account_id=checking.id),
        ChangeEvent(date=_months_ago(today, 1, 9), description="Car repair", amount=-86000, category="misc",
                    account_id=checking.id),
        PricePoint(ticker="EXMP", date=grant, price=8200),
        PricePoint(ticker="EXMP", date=_months_ago(today, 1, 3), price=10450),
    ])
    db.session.commit()
