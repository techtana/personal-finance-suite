"""Seed a large database and time every read the pages make.

    python -m scripts.load_bench [--years 10] [--per-month 150] [--db instance/load-demo.db]

Uses a throwaway SQLite file (or the new file given with --db; never the real
database), so the pages can also be opened against it. Prints the response time
and size of each GET, slowest first, so a page that would hang on a big history
shows up before a user meets it.
"""

import argparse
import os
import random
import sys
import tempfile
import time
from datetime import date, timedelta


def seed(years: int, per_month: int):
    from models import Account, ChangeEvent, Loan, PricePoint, Rule, Snapshot, db

    rnd = random.Random(7)
    today = date.today()
    start = date(today.year - years, today.month, 1)
    accts = [Account(name=n, type=t, institution="Example Bank", current_balance=b, last_updated_date=start.isoformat())
             for n, t, b in [("Checking", "checking", 500000), ("Savings", "savings", 2000000),
                             ("Visa", "credit_card", 0), ("Amex", "credit_card", 0),
                             ("Brokerage", "brokerage", 5000000), ("401k", "retirement_401k", 9000000)]]
    db.session.add_all(accts)
    db.session.add(Loan(name="Mortgage", type="mortgage", institution="Example Bank", current_balance=40000000, original_balance=50000000,
                        interest_rate=500, monthly_payment=250000, start_date=start.isoformat(),
                        payoff_date=date(today.year + 20, 1, 1).isoformat()))
    db.session.flush()
    cats = ["groceries", "dining", "transport", "utilities", "shopping", "travel", "health", "entertainment"]
    rows, snaps, d = [], [], start
    while d <= today:
        for _ in range(per_month):
            day = d + timedelta(days=rnd.randrange(28))
            a = rnd.choice(accts[:4])
            rows.append(ChangeEvent(date=day.isoformat(), description=f"Merchant {rnd.randrange(400)}",
                                    amount=-rnd.randrange(200, 30000), account_id=a.id, category=rnd.choice(cats),
                                    change_type="import"))
        rows.append(ChangeEvent(date=d.isoformat(), description="Payroll", amount=900000, account_id=accts[0].id,
                                category="income", change_type="import"))
        for a in accts:
            snaps.append(Snapshot(entity_type="cash", entity_id=a.id, date=(d + timedelta(days=27)).isoformat(),
                                  value=a.current_balance + rnd.randrange(0, 100000)))
        d = (d.replace(day=28) + timedelta(days=4)).replace(day=1)
    for i in range(12):
        rows.append(ChangeEvent(date=(today + timedelta(days=30 * i)).isoformat(), description="Planned purchase",
                                amount=-50000, change_type="manual"))
    db.session.add_all(rows)
    db.session.add_all(snaps)
    p = start
    while p <= today:
        db.session.add(PricePoint(ticker="GOOG", date=p.isoformat(), price=10000 + rnd.randrange(5000)))
        p += timedelta(days=1)
    for i in range(25):
        db.session.add(Rule(name=f"Bill {i}", rule_type="expense", amount=-rnd.randrange(1000, 50000),
                            frequency="monthly", start_date=start.isoformat(), account_id=accts[0].id))
    db.session.add(Rule(name="Salary", rule_type="income", amount=900000, frequency="biweekly",
                        start_date=start.isoformat(), account_id=accts[0].id))
    db.session.commit()
    return len(rows), len(snaps), accts[0].id


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", type=int, default=10)
    ap.add_argument("--per-month", type=int, default=150)
    ap.add_argument("--db", help="write the seeded database here (must not exist yet)")
    args = ap.parse_args()
    if args.db and os.path.exists(args.db):
        sys.exit(f"{args.db} already exists; pick a new file")
    path = os.path.abspath(args.db) if args.db else os.path.join(tempfile.mkdtemp(), "bench.db")
    os.environ["FINANCE_DB_PATH"] = path
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from app import create_app
    from config import Config

    class Cfg(Config):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{path}"
        TESTING = True
        LLM_PROVIDER = "off"
        BACKUP_SCHEDULER = False

    app = create_app(Cfg)
    with app.app_context():
        n_txn, n_snap, chk = seed(args.years, args.per_month)
    print(f"seeded {n_txn} entries, {n_snap} balance records")
    today = date.today()
    in12 = (today + timedelta(days=365)).isoformat()
    in30y = (today + timedelta(days=365 * 30)).isoformat()
    urls = ["/api/balances", "/api/insights", "/api/projection?from=%s&to=%s" % (today, in12),
            "/api/projection?from=%s&to=%s" % (today, in30y), "/api/net-worth/history?months=12",
            "/api/net-worth/history?months=120", "/api/plan-vs-actual?months=4", "/api/changes", "/api/rules",
            "/api/prices", "/api/then-vs-now", "/api/taxes/summary", "/api/activity?limit=200",
            f"/api/balances/{chk}/ledger?limit=100", f"/api/snapshots?entity_type=cash&entity_id={chk}",
            "/api/accounts", "/api/categories"]
    client = app.test_client()
    out = []
    for u in urls:
        t = time.perf_counter()
        r = client.get(u)
        out.append((time.perf_counter() - t, len(r.data), r.status_code, u))
    for secs, size, status, u in sorted(out, reverse=True):
        print(f"{secs * 1000:8.0f} ms {size / 1024:9.0f} KB  {status}  {u}")


if __name__ == "__main__":
    main()
