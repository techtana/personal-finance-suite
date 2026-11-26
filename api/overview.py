"""Read models for the role-based pages: unified balances, net-worth history, insights."""

from datetime import date, timedelta

from flask import Blueprint, jsonify, request

from api import _data
from engine import insights as insights_engine
from engine.lookback import _entity_value, _month_ends
from engine import ledger, plan_actual
from models import Account, Asset, Category, ChangeEvent, ImportBatch, ImportRow, Loan, Snapshot, db
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
    entities = _data.load_entities(snaps, today=today)
    full = {}
    for etype, (model, _, schema) in MODELS.items():
        q = model.query.filter_by(is_active=True) if etype == "cash" else model.query
        for obj in q.all():
            full[(etype, obj.id)] = schema.model_validate(obj).model_dump()
    rows = []
    for e in entities:
        history = snaps.get((e["type"], e["id"]), [])
        n = insights_engine.days_since(e, today)
        row = {
            "entity_type": e["type"], "id": e["id"], "name": e["name"], "kind": e["kind"],
            "institution": e["institution"], "value": e["current"], "signed_value": _data.signed(e),
            "owed": bool(e.get("owed")), "bucket": _data.bucket(e),
            "last_updated": e["current_date"], "days_since": n,
            "stale": n is None or n >= limits["stale_days"],
            "snapshot_count": len(history), "spark": _spark(e, history, today),
            "note": e["note"], "entity": full.get((e["type"], e["id"])),
        }
        if e["type"] == "cash":
            row.update({"recorded": e["recorded"], "recorded_date": e["recorded_date"],
                        "since_count": e["since_count"], "since_flow": e["since_flow"], "txn_count": e["txn_count"],
                        "needs_start": e["txn_count"] > 0 and not e["has_snapshots"]})
        rows.append(row)
    return jsonify({"rows": rows, "totals": _data.totals(entities), "stale_days": limits["stale_days"],
                    "stale_count": sum(1 for r in rows if r["stale"]), "today": today})


def _spark(entity, history, today, points=12):
    """Recorded values, or for a cash account with transactions, its month-end balances."""
    if entity["type"] != "cash" or not entity.get("txns"):
        return [v for _, v in history[-points:]]
    start = (date.fromisoformat(today).replace(day=1) - timedelta(days=31 * (points - 1))).replace(day=1)
    out = []
    for iso in list(_month_ends(start.isoformat(), today)) + [today]:
        v = _entity_value(entity, history, iso)
        if v is not None:
            out.append(v)
    return out


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
    if snap and snap.value != value:
        _drop_adjustments(snap.id)  # the old difference no longer applies
        db.session.flush()
    check = _reconcile_check(obj, when, value) if etype == "cash" else None
    if snap:
        snap.value = value
        if "note" in data:
            snap.note = data.get("note") or None
    else:
        snap = Snapshot(entity_type=etype, entity_id=eid, date=when, value=value, note=data.get("note") or None)
        db.session.add(snap)
    if not obj.last_updated_date or when >= obj.last_updated_date:
        if etype == "cash" and obj.last_updated_date and obj.last_updated_date < when and not Snapshot.query.filter(
                Snapshot.entity_type == "cash", Snapshot.entity_id == eid,
                Snapshot.date >= obj.last_updated_date, Snapshot.date < when).first():
            # The value typed in with the account is its only earlier record: keep it, so the
            # transactions in between can still be checked against it.
            db.session.add(Snapshot(entity_type="cash", entity_id=eid, date=obj.last_updated_date,
                                    value=getattr(obj, field) or 0, note="Value entered with the account"))
        setattr(obj, field, value)
        obj.last_updated_date = when
    db.session.commit()
    return jsonify({"id": snap.id, "entity_type": etype, "entity_id": eid, "date": when, "value": value,
                    "check": check}), 201


_account_points = _data.account_points


def _reconcile_check(account, when, value):
    """How a newly recorded balance compares with the previous record plus the transactions since.

    None when there is no earlier record or no transaction in between: then there is nothing to compare.
    """
    owed = ledger.is_owed(account.type)
    txns = _data.balance_txns(when).get(account.id, [])
    got = ledger.expected_at(_account_points(account, before=when), txns, when, owed)
    if not got or not got[2]:
        return None
    expected, anchor_date, count = got
    return {"expected": expected, "actual": value, "gap": value - expected, "since_date": anchor_date,
            "count": count, "owed": owed}


def _drop_adjustments(snapshot_id):
    for c in ChangeEvent.query.filter_by(snapshot_id=snapshot_id, change_type="adjustment").all():
        db.session.delete(c)


@bp.route("/balances/<account_id>/ledger", methods=["GET"])
def account_ledger(account_id):
    """One cash account's recorded balances and transactions, newest first, with the running balance.

    ?limit (default 100, at most 500) and ?offset page through the entries.
    """
    account = db.session.get(Account, account_id)
    if not account:
        return jsonify({"error": "not found"}), 404
    owed = ledger.is_owed(account.type)
    try:
        limit = min(500, max(1, int(request.args.get("limit", 100))))
        offset = max(0, int(request.args.get("offset", 0)))
    except ValueError:
        return jsonify({"error": "limit and offset must be whole numbers"}), 422
    today = _data.today_iso(request.args.get("today"))
    snaps = [{"id": s.id, "date": s.date, "value": s.value, "note": s.note}
             for s in Snapshot.query.filter_by(entity_type="cash", entity_id=account.id).all()]
    if account.last_updated_date and not any(s["date"] >= account.last_updated_date for s in snaps):
        snaps.append({"id": None, "date": account.last_updated_date, "value": account.current_balance or 0,
                      "note": "Value entered with the account"})
    changes = [c for c in ChangeEvent.query.filter_by(account_id=account.id).all()
               if ledger.is_actual({"change_type": c.change_type}) and c.amount and (c.date or "") <= today]
    files = _import_files([c.id for c in changes if c.change_type == "imported"])
    entries = ledger.build_ledger(snaps, [
        {"id": c.id, "date": c.date, "description": c.description, "amount": c.amount, "category": c.category,
         "change_type": c.change_type, "snapshot_id": c.snapshot_id, "file": files.get(c.id),
         "transfer": c.category == ledger.TRANSFER_CATEGORY} for c in changes], owed)
    newest = max(snaps, key=lambda s: s["date"]) if snaps else {"value": 0, "date": None}
    now = ledger.current(newest["value"], newest["date"],
                         [(e["date"], e["amount"]) for e in entries if e["kind"] == "txn"], today, owed)
    entries.reverse()
    gaps = sum(1 for e in entries if e["kind"] == "recorded" and e.get("gap"))
    return jsonify({"account": {"id": account.id, "name": account.name, "type": account.type, "owed": owed},
                    "current": now["value"], "as_of": now["as_of"], "since_count": now["since_count"],
                    "total": len(entries), "open_gaps": gaps,
                    "entries": entries[offset:offset + limit], "offset": offset, "limit": limit})


def _import_files(change_ids):
    """{change_id: filename} for imported transactions."""
    if not change_ids:
        return {}
    q = (db.session.query(ImportRow.created_id, ImportBatch.filename)
         .join(ImportBatch, ImportRow.batch_id == ImportBatch.id)
         .filter(ImportRow.created_id.in_(change_ids)))
    return {cid: fn for cid, fn in q}


@bp.route("/balances/reconcile", methods=["POST"])
def reconcile():
    """Log what a recorded balance's transactions leave unexplained as one adjustment entry.

    {snapshot_id}. The adjustment is dated on the record's day, so it explains the
    gap in the ledger without moving the balance, which the record already sets.
    """
    data = request.get_json() or {}
    snap = db.session.get(Snapshot, data.get("snapshot_id") or "")
    if not snap or snap.entity_type != "cash":
        return jsonify({"error": "not found"}), 404
    account = db.session.get(Account, snap.entity_id)
    if not account:
        return jsonify({"error": "not found"}), 404
    owed = ledger.is_owed(account.type)
    txns = _data.balance_txns(snap.date).get(account.id, [])
    got = ledger.expected_at(_account_points(account, before=snap.date), txns, snap.date, owed)
    if not got:
        return jsonify({"error": "There is no earlier balance to compare this one with."}), 409
    expected, anchor_date, _ = got
    gap = snap.value - expected
    if gap == 0:
        return jsonify({"created": None, "gap": 0})
    change = ChangeEvent(date=snap.date, description="Unexplained difference", amount=ledger.sign(owed) * gap,
                         account_id=account.id, category=None, change_type="adjustment", snapshot_id=snap.id,
                         note=f"Recorded {snap.value / 100:,.2f} on {snap.date}; the record before it "
                              f"({anchor_date}) plus the transactions since add up to {expected / 100:,.2f}.")
    db.session.add(change)
    db.session.commit()
    return jsonify({"created": change.id, "gap": gap, "amount": change.amount}), 201


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
    entities = [e for e in _data.load_entities(snaps, today=today)
                if (not types or _data.bucket(e) in types) and (not ids or e["id"] in ids)]
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
            row[{"cash": "cash", "asset": "assets", "liability": "liabilities"}[_data.bucket(e)]] += v
        if known:
            row["net_worth"] = row["cash"] + row["assets"] - row["liabilities"]
            points.append(row)
    return jsonify({"series": points, "today": today})


@bp.route("/plan-vs-actual", methods=["GET"])
def plan_vs_actual():
    """What the plan expected each month by category, next to the imported transactions. ?months=4"""
    today = _data.today_iso(request.args.get("today"))
    try:
        count = min(24, max(1, int(request.args.get("months", 4))))
    except ValueError:
        count = 4
    return jsonify({**_plan_vs_actual(today, count), "today": today})


def _plan_vs_actual(today: str, count: int) -> dict:
    labels = {c.slug: c.label for c in Category.query.all()}
    return plan_actual.plan_vs_actual(_data.rule_dicts(), _data.change_dicts(), _data.loan_dicts(),
                                      _data.latest_prices(today), plan_actual.recent_months(today, count), labels)


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
        entities=_data.load_entities(snaps, today=today), snaps=snaps, rules=_data.rule_dicts(), changes=_data.change_dicts(),
        loans=_data.loan_dicts(), prices=prices, today=today, stale_days=limits["stale_days"],
        net_worth_bps=limits["net_worth_bps"],
        pending_imports=ImportBatch.query.filter_by(status="review").count(),
        tax_insights=tax_insights, tax_year=year, plan_actual=_plan_vs_actual(today, 2),
    )


@bp.route("/insights", methods=["GET"])
def insights():
    today = _data.today_iso(request.args.get("today"))
    items = collect_insights(today)
    return jsonify({"insights": items, "today": today,
                    "counts": {s: sum(1 for i in items if i["severity"] == s) for s in ("attention", "info", "good")}})
