"""REST API for projections (v1 legacy + v2 new schema)."""

import json
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify
from models import db, OneTimeTxn, RecurringTxn, BlanketExpense, RSUGrant, ESPPPlan
from models import Account, Loan, Asset, Rule, ChangeEvent, Snapshot
from engine.projection import project, project_v2

bp = Blueprint("api_projection", __name__)


def serialize_bucket(bucket):
    return {
        "month": bucket.month,
        "income": bucket.income,
        "expenses": bucket.expenses,
        "net_cash_flow": bucket.net_cash_flow,
        "cumulative_net_worth": bucket.cumulative_net_worth,
        "actual_net_worth": bucket.actual_net_worth,
        "events": [
            {
                "date": ev.date,
                "source_id": ev.source_id,
                "source_type": ev.source_type,
                "type": ev.type,
                "amount": ev.amount,
                "label": ev.label,
                "category": ev.category,
            }
            for ev in bucket.events
        ],
    }


def latest_snapshot_value(entity_type: str, entity_id: str) -> int | None:
    snap = (
        Snapshot.query
        .filter_by(entity_type=entity_type, entity_id=entity_id)
        .order_by(Snapshot.date.desc())
        .first()
    )
    return snap.value if snap else None


@bp.route("/projection", methods=["GET"])
def get_projection():
    """v2 projection using Rules + ChangeEvents + Snapshots."""
    from_date = request.args.get("from") or datetime.utcnow().date().isoformat()
    to_date = request.args.get("to") or (datetime.utcnow().date() + timedelta(days=365)).isoformat()

    stock_prices_str = request.args.get("prices", "{}")
    try:
        stock_prices = json.loads(stock_prices_str)
    except Exception:
        stock_prices = {}

    # Compute starting net worth from snapshots, falling back to entity fields
    starting_nw = 0

    for account in Account.query.filter_by(is_active=True).all():
        val = latest_snapshot_value("cash", account.id)
        starting_nw += val if val is not None else account.current_balance

    for asset in Asset.query.all():
        val = latest_snapshot_value("asset", asset.id)
        starting_nw += val if val is not None else asset.current_value

    for loan in Loan.query.all():
        val = latest_snapshot_value("liability", loan.id)
        starting_nw -= val if val is not None else loan.current_balance

    # Fetch rules
    rules = [
        {
            "id": r.id,
            "name": r.name,
            "rule_type": r.rule_type,
            "account_id": r.account_id,
            "amount": r.amount,
            "frequency": r.frequency,
            "start_date": r.start_date,
            "end_date": r.end_date,
            "category": r.category,
            "schedule": r.schedule,
            "config": r.config,
            "is_active": r.is_active,
        }
        for r in Rule.query.filter_by(is_active=True).all()
    ]

    # Fetch manual change events
    changes = [
        {
            "id": c.id,
            "date": c.date,
            "description": c.description,
            "amount": c.amount,
            "category": c.category,
            "change_type": c.change_type,
        }
        for c in ChangeEvent.query.all()
    ]

    # Loans for auto payment expansion
    loans = [
        {
            "id": l.id,
            "name": l.name,
            "current_balance": l.current_balance,
            "monthly_payment": l.monthly_payment,
            "start_date": l.start_date,
            "payoff_date": l.payoff_date,
        }
        for l in Loan.query.all()
    ]

    try:
        buckets, events = project_v2(
            rules=rules,
            changes=changes,
            loans=loans,
            starting_net_worth=starting_nw,
            stock_prices=stock_prices,
            from_date=from_date,
            to_date=to_date,
        )
        return jsonify({
            "buckets": [serialize_bucket(b) for b in buckets],
            "events": [
                {
                    "date": e.date,
                    "source_id": e.source_id,
                    "source_type": e.source_type,
                    "type": e.type,
                    "amount": e.amount,
                    "label": e.label,
                    "category": e.category,
                }
                for e in events
            ],
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@bp.route("/projection/legacy", methods=["GET"])
def get_projection_legacy():
    """Legacy v1 projection (kept for reference)."""
    from_date = request.args.get("from") or datetime.utcnow().date().isoformat()
    to_date = request.args.get("to") or (datetime.utcnow().date() + timedelta(days=365)).isoformat()

    stock_prices_str = request.args.get("prices", "{}")
    try:
        stock_prices = json.loads(stock_prices_str)
    except Exception:
        stock_prices = {}

    transactions = [
        {"id": t.id, "type": t.type, "amount": t.amount, "date": t.date,
         "category": t.category, "account_id": t.account_id, "note": t.note,
         "frequency": None, "start_date": None, "end_date": None}
        for t in OneTimeTxn.query.all()
    ]
    for t in RecurringTxn.query.all():
        transactions.append({
            "id": t.id, "type": t.type, "amount": t.amount, "date": None,
            "category": t.category, "account_id": t.account_id, "note": t.note,
            "frequency": t.frequency, "start_date": t.start_date, "end_date": t.end_date,
        })

    blanket_expenses = [
        {"id": e.id, "label": e.label, "amount": e.amount, "frequency": e.frequency,
         "start_date": e.start_date, "end_date": e.end_date, "category": e.category}
        for e in BlanketExpense.query.all()
    ]
    rsu_grants = [
        {"id": g.id, "label": g.label, "total_shares": g.total_shares, "ticker": g.ticker,
         "vest_schedule": g.vest_schedule, "withholding_rate": g.withholding_rate}
        for g in RSUGrant.query.all()
    ]
    espp_plans = [
        {"id": p.id, "label": p.label, "purchase_periods": p.purchase_periods,
         "contribution_mode": p.contribution_mode, "contribution_value": p.contribution_value,
         "base_salary": p.base_salary, "discount_rate": p.discount_rate, "has_lookback": p.has_lookback}
        for p in ESPPPlan.query.all()
    ]
    accounts = [{"id": a.id, "current_balance": a.current_balance}
                for a in Account.query.filter_by(is_active=True).all()]
    loans = [
        {"id": l.id, "current_balance": l.current_balance, "interest_rate": l.interest_rate,
         "monthly_payment": l.monthly_payment, "start_date": l.start_date,
         "payoff_date": l.payoff_date, "name": l.name}
        for l in Loan.query.all()
    ]

    try:
        buckets, events = project(
            transactions, blanket_expenses, rsu_grants, espp_plans,
            accounts, loans, stock_prices, from_date, to_date,
        )
        return jsonify({
            "buckets": [serialize_bucket(b) for b in buckets],
            "events": [{"date": e.date, "source_id": e.source_id, "source_type": e.source_type,
                        "type": e.type, "amount": e.amount, "label": e.label, "category": e.category}
                       for e in events],
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 400
