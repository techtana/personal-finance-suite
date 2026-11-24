"""Serve the app on a throwaway database filled with the Then vs. Now sample data.

    python -m tests.lookback_demo demo.db [--port 5601]

Then open http://127.0.0.1:5601/then-vs-now?today=2026-11-22

The sample is loaded only when the database file does not exist yet, so this can
never add sample rows to a database that already holds real data.
"""

import os
import sys


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        sys.exit(__doc__)
    db_path = os.path.abspath(args[0])
    port = int(sys.argv[sys.argv.index("--port") + 1]) if "--port" in sys.argv else 5601
    fresh = not os.path.exists(db_path)
    os.environ["FINANCE_DB_PATH"] = db_path      # read by config.py at import time

    from app import create_app
    from tests import lookback_sample as sample

    app = create_app()
    if fresh:
        client = app.test_client()

        def post(url, body):
            res = client.post(url, json=body)
            assert res.status_code == 201, (url, res.status_code, res.get_data(as_text=True))
            return res.get_json()

        def snap(entity_type, entity_id, day, dollars):
            post("/api/snapshots", {"entity_type": entity_type, "entity_id": entity_id, "date": day, "value": dollars * 100})

        accounts = {a["name"]: post("/api/accounts", a)["id"] for a in sample.accounts()}
        loans = {l["name"]: post("/api/loans", l)["id"] for l in sample.loans()}
        assets = {a["name"]: post("/api/assets", a)["id"] for a in sample.assets()}
        for rule in sample.rules():
            body = dict(rule)
            if rule["rule_type"] == "rsu":       # the rules API rebuilds RSU schedules from these
                body["config"] = dict(rule["config"], cliff_months=12, cliff_percent=2500,
                                      subsequent_frequency="quarterly", subsequent_percent=625)
            post("/api/rules", body)
        post("/api/prices", {"prices": sample.prices()})

        for day, checking, brokerage, k401 in sample.ACCOUNT_HISTORY:
            snap("cash", accounts["Checking"], day, checking)
            snap("cash", accounts["Brokerage"], day, brokerage)
            snap("cash", accounts["401k"], day, k401)
        for name, history in sample.ASSET_HISTORY.items():
            for day, dollars in history:
                snap("asset", assets[name], day, dollars)
        for name, history in sample.LOAN_HISTORY.items():
            for day, dollars in history:
                snap("liability", loans[name], day, dollars)
        print(f"Loaded sample data into {db_path}")

    print(f"Open http://127.0.0.1:{port}/then-vs-now?today={sample.TODAY}")
    app.run(port=port, debug=False)


if __name__ == "__main__":
    main()
