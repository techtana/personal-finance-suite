"""Read models for the role-based pages: unified balances, net-worth history, insights."""

from datetime import date, timedelta

from flask import Blueprint, jsonify, request

from api import _data
from engine import insights as insights_engine
from engine.lookback import _entity_value, _month_ends
from models import Account, Asset, ImportBatch, Loan, Snapshot, db
from schemas import AccountSchema, AssetSchema, LoanSchema

bp = Blueprint("api_overview", __name__)

MODELS = {"cash": (Account, "current_balance", AccountSchema),
          "asset": (Asset, "current_value", AssetSchema),
          "liability": (Loan, "current_balance", LoanSchema)}


@bp.route("/balances", methods=["GET"])
def balances():
    """Every cash account, asset and liability in one list, with freshness."""
    today = _data.today_iso(request.args.get("today"))
    limits = _data.thresholds()
    snaps = _data.snapshot_history()
    entities = _data.load_entities(snaps)
    full = {}
    for etype, (model, _, schema) in MODELS.items():
        q = model.query.filter_by(is_active=True) if etype == "cash" else model.query
        for obj in q.all():
            full[(etype, obj.id)] = schema.model_validate(obj).model_dump()
    rows = []
    for e in entities:
        history = snaps.get((e["type"], e["id"]), [])
        n = insights_engine.days_since(e, today)
        rows.append({
            "entity_type": e["type"], "id": e["id"], "name": e["name"], "kind": e["kind"],
            "institution": e["institution"], "value": e["current"],
            "signed_value": -e["current"] if e["type"] == "liability" else e["current"],
            "last_updated": e["current_date"], "days_since": n,
            "stale": n is None or n >= limits["stale_days"],
            "snapshot_count": len(history), "spark": [v for _, v in history[-12:]],
            "note": e["note"], "entity": full.get((e["type"], e["id"])),
        })
    return jsonify({"rows": rows, "totals": _data.totals(entities), "stale_days": limits["stale_days"],
                    "stale_count": sum(1 for r in rows if r["stale"]), "today": today})


@bp.route("/balances/record", methods=["POST"])
def record_balance():
    """Record a value for one entity on a date: one snapshot, and the entity's own field if it is the newest."""
    data = request.get_json() or {}
    etype, eid = data.get("entity_type"), data.get("entity_id")
    if etype not in MODELS:
        return jsonify({"error": "entity_type must be cash, asset or liability"}), 422
    model, field, _ = MODELS[etype]
    obj = model.query.get(eid) if eid else None
    if not obj:
        return jsonify({"error": "not found"}), 404
    try:
        value = int(data.get("value"))
    except (TypeError, ValueError):
        return jsonify({"error": "value must be a whole number of cents"}), 422
    if value < 0:
        return jsonify({"error": "value can't be negative; liabilities are entered as positive amounts"}), 422
    when = data.get("date") or date.today().isoformat()
    try:
        date.fromisoformat(when)
    except ValueError:
        return jsonify({"error": "date must be YYYY-MM-DD"}), 422

    snap = Snapshot.query.filter_by(entity_type=etype, entity_id=eid, date=when).first()
    if snap:
        snap.value = value
        if "note" in data:
            snap.note = data.get("note") or None
    else:
        snap = Snapshot(entity_type=etype, entity_id=eid, date=when, value=value, note=data.get("note") or None)
        db.session.add(snap)
    if not obj.last_updated_date or when >= obj.last_updated_date:
        setattr(obj, field, value)
        obj.last_updated_date = when
    db.session.commit()
    return jsonify({"id": snap.id, "entity_type": etype, "entity_id": eid, "date": when, "value": value}), 201


@bp.route("/net-worth/history", methods=["GET"])
def net_worth_history():
    """Month-end recorded values split by cash, assets and liabilities.

    ?months=24 how far back; ?types=cash,asset to include only some entity types;
    ?ids=a,b to include only some entities.
    """
    today = _data.today_iso(request.args.get("today"))
    try:
        months = min(120, max(1, int(request.args.get("months", 24))))
    except ValueError:
        months = 24
    types = {t for t in (request.args.get("types") or "").split(",") if t}
    ids = {i for i in (request.args.get("ids") or "").split(",") if i}
    snaps = _data.snapshot_history()
    entities = [e for e in _data.load_entities(snaps)
                if (not types or e["type"] in types) and (not ids or e["id"] in ids)]
    start = (date.fromisoformat(today).replace(day=1) - timedelta(days=31 * (months - 1))).replace(day=1)
    points = []
    for iso in list(_month_ends(start.isoformat(), today)) + [today]:
        row = {"date": iso, "month": iso[:7], "cash": 0, "assets": 0, "liabilities": 0, "partial": False}
        known = 0
        for e in entities:
            v = _entity_value(e, snaps.get((e["type"], e["id"]), []), iso)
            if v is None:
                row["partial"] = True
                continue
            known += 1
            row[{"cash": "cash", "asset": "assets", "liability": "liabilities"}[e["type"]]] += v
        if known:
            row["net_worth"] = row["cash"] + row["assets"] - row["liabilities"]
            points.append(row)
    return jsonify({"series": points, "today": today})


def collect_insights(today: str) -> list[dict]:
    from api.taxes import compute_tax_summary

    limits = _data.thresholds()
    snaps = _data.snapshot_history()
    prices = _data.latest_prices(today)
    year = int(today[:4])
    try:
        tax = compute_tax_summary(year, prices)
        tax_insights = tax.get("insights", []) if (_data.rule_dicts() or _data.change_dicts()) else []
    except Exception:
        tax_insights = []
    return insights_engine.build_insights(
        entities=_data.load_entities(snaps), snaps=snaps, rules=_data.rule_dicts(), changes=_data.change_dicts(),
        loans=_data.loan_dicts(), prices=prices, today=today, stale_days=limits["stale_days"],
        net_worth_bps=limits["net_worth_bps"],
        pending_imports=ImportBatch.query.filter_by(status="review").count(),
        tax_insights=tax_insights, tax_year=year,
    )


@bp.route("/insights", methods=["GET"])
def insights():
    today = _data.today_iso(request.args.get("today"))
    items = collect_insights(today)
    return jsonify({"insights": items, "today": today,
                    "counts": {s: sum(1 for i in items if i["severity"] == s) for s in ("attention", "info", "good")}})
