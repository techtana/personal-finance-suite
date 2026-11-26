"""REST API for the forecast: rules + logged changes + loan payments, from today's recorded balances."""

import json
from datetime import date, timedelta

from flask import Blueprint, jsonify, request

from api import _data
from engine.lookback import net_worth_series
from engine.projection import project_v2

bp = Blueprint("api_projection", __name__)


def serialize_event(ev):
    return {"date": ev.date, "source_id": ev.source_id, "source_type": ev.source_type, "type": ev.type,
            "amount": ev.amount, "label": ev.label, "category": ev.category}


def serialize_bucket(bucket):
    return {
        "month": bucket.month,
        "income": bucket.income,
        "expenses": bucket.expenses,
        "net_cash_flow": bucket.net_cash_flow,
        "cumulative_net_worth": bucket.cumulative_net_worth,
        "actual_net_worth": bucket.actual_net_worth,
        "events": [serialize_event(ev) for ev in bucket.events],
    }


@bp.route("/projection", methods=["GET"])
def get_projection():
    """Forecast from recorded balances.

    ?from, ?to     horizon (default today, one year)
    ?prices        JSON {ticker: cents}; defaults to the latest stored share prices
    ?disable       comma-separated rule / change / loan ids to leave out (what-if).
                   The answer then also carries `baseline`, the forecast with nothing left out.
    ?history       months of recorded net worth to return alongside (default 0)
    """
    today = date.today().isoformat()
    from_date = request.args.get("from") or today
    to_date = request.args.get("to") or (date.today() + timedelta(days=365)).isoformat()

    stock_prices = _data.latest_prices(from_date)
    if request.args.get("prices"):
        try:
            stock_prices.update(json.loads(request.args["prices"]))
        except Exception:
            pass
    disabled = {i for i in (request.args.get("disable") or "").split(",") if i}
    try:
        history_months = min(120, max(0, int(request.args.get("history", 0))))
    except ValueError:
        history_months = 0

    snaps = _data.snapshot_history()
    entities = _data.load_entities(snaps, today=today)
    starting_nw = _data.totals(entities)["net_worth"]
    rules, changes, loans = _data.rule_dicts(), _data.change_dicts(), _data.loan_dicts()

    def run(disabled_ids):
        return project_v2(rules=rules, changes=changes, loans=loans, starting_net_worth=starting_nw,
                          stock_prices=stock_prices, from_date=from_date, to_date=to_date,
                          disabled_ids=disabled_ids, fill_months=True)

    try:
        buckets, events = run(disabled)
        baseline = run(set())[0] if disabled else None
    except Exception as e:
        return jsonify({"error": str(e)}), 400

    actuals = []
    if history_months:
        start = (date.fromisoformat(today).replace(day=1) - timedelta(days=31 * history_months)).replace(day=1)
        actuals = [{"date": p["date"], "month": p["date"][:7], "net_worth": p["value"], "partial": p["partial"]}
                   for p in net_worth_series(entities, snaps, start.isoformat(), today)]
    by_month = {a["month"]: a["net_worth"] for a in actuals}
    for b in buckets:
        if b.month in by_month and b.month <= today[:7]:
            b.actual_net_worth = by_month[b.month]

    return jsonify({
        "buckets": [serialize_bucket(b) for b in buckets],
        "events": [serialize_event(e) for e in events],
        "starting_net_worth": starting_nw,
        "actuals": actuals,
        "disabled": sorted(disabled),
        "baseline": [{"month": b.month, "cumulative_net_worth": b.cumulative_net_worth,
                      "net_cash_flow": b.net_cash_flow} for b in baseline] if baseline is not None else None,
        "prices_used": stock_prices,
    })
