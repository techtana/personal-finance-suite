"""REST API for the Then vs. Now page: the look-back payload and share prices."""

from datetime import date
from flask import Blueprint, request, jsonify
from models import db, Account, Loan, Asset, Rule, Snapshot, PricePoint
from api import _data
from engine import ledger
from engine.lookback import build_lookback

bp = Blueprint("api_lookback", __name__)


def _price_json(p: PricePoint) -> dict:
    return {"id": p.id, "ticker": p.ticker, "date": p.date, "price": p.price}


def _valid_date(value) -> bool:
    try:
        date.fromisoformat(value)
        return True
    except (TypeError, ValueError):
        return False


@bp.route("/then-vs-now", methods=["GET"])
def then_vs_now():
    today = request.args.get("today")
    if not _valid_date(today):
        today = date.today().isoformat()

    txns = _data.balance_txns(today)
    payload = build_lookback(
        rules=[
            {"id": r.id, "name": r.name, "rule_type": r.rule_type, "start_date": r.start_date,
             "schedule": r.schedule, "config": r.config}
            for r in Rule.query.filter_by(is_active=True).all()
        ],
        assets=[
            {"id": a.id, "name": a.name, "category": a.category, "ticker": a.ticker, "quantity": a.quantity,
             "current_value": a.current_value, "cost_basis": a.cost_basis, "acquired_date": a.acquired_date,
             "decided_date": a.decided_date, "last_updated_date": a.last_updated_date, "note": a.note}
            for a in Asset.query.all()
        ],
        accounts=[
            {"id": a.id, "current_balance": a.current_balance, "last_updated_date": a.last_updated_date,
             "txns": txns.get(a.id, []), "owed": ledger.is_owed(a.type)}
            for a in Account.query.filter_by(is_active=True).all()
        ],
        loans=[
            {"id": l.id, "current_balance": l.current_balance, "original_balance": l.original_balance,
             "start_date": l.start_date, "last_updated_date": l.last_updated_date}
            for l in Loan.query.all()
        ],
        snapshots=[
            {"entity_type": s.entity_type, "entity_id": s.entity_id, "date": s.date, "value": s.value}
            for s in Snapshot.query.all()
        ],
        prices=[_price_json(p) for p in PricePoint.query.all()],
        today=today,
    )
    return jsonify(payload)


@bp.route("/prices", methods=["GET"])
def list_prices():
    q = PricePoint.query
    ticker = request.args.get("ticker")
    if ticker:
        q = q.filter_by(ticker=ticker.upper())
    points = q.order_by(PricePoint.ticker, PricePoint.date.desc()).all()
    return jsonify([_price_json(p) for p in points])


@bp.route("/prices", methods=["POST"])
def save_prices():
    """Create or replace prices. Body: one {ticker, date, price} or {"prices": [...]}. Price in cents."""
    data = request.get_json() or {}
    rows = data.get("prices") if isinstance(data.get("prices"), list) else [data]

    cleaned = []
    for row in rows:
        ticker = str(row.get("ticker") or "").strip().upper()
        try:
            price = int(row.get("price"))
        except (TypeError, ValueError):
            price = 0
        if not ticker or not _valid_date(row.get("date")) or price <= 0:
            return jsonify({"error": "each price needs a ticker, a date (YYYY-MM-DD) and a price above zero"}), 422
        cleaned.append((ticker, row["date"], price))

    saved = []
    for ticker, day, price in cleaned:
        point = PricePoint.query.filter_by(ticker=ticker, date=day).first()
        if point:
            point.price = price
        else:
            point = PricePoint(ticker=ticker, date=day, price=price)
            db.session.add(point)
        saved.append(point)
    db.session.commit()
    return jsonify([_price_json(p) for p in saved]), 201


@bp.route("/prices/<price_id>", methods=["DELETE"])
def delete_price(price_id):
    point = db.session.get(PricePoint, price_id)
    if not point:
        return jsonify({"error": "not found"}), 404
    db.session.delete(point)
    db.session.commit()
    return "", 204
