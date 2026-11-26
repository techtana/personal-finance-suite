"""REST API for manual change events (one-time cash-flow entries).

Years of imported transactions land here, so the list is searched, filtered,
sorted and paged in the database: a page asks for one screenful at a time.
"""

from datetime import date

from flask import Blueprint, request, jsonify
from sqlalchemy import func, or_

from models import db, Account, ChangeEvent
from schemas import ChangeEventSchema

bp = Blueprint("api_changes", __name__)

MAX_LIMIT = 500
SORTS = {
    "date": ChangeEvent.date, "description": func.lower(ChangeEvent.description), "amount": ChangeEvent.amount,
    "source": ChangeEvent.change_type, "category": func.coalesce(ChangeEvent.category, ""),
    "account": func.coalesce(Account.name, ""),
}


def _cents(value):
    """Dollars typed in a filter box -> cents, or None when blank or not a number."""
    try:
        return round(abs(float(value)) * 100) if value not in (None, "") else None
    except ValueError:
        return None


def _filtered(args, skip=None):
    """The entries matching the query string. `skip` leaves one filter out (for its own dropdown)."""
    q = ChangeEvent.query.outerjoin(Account, ChangeEvent.account_id == Account.id)
    today = args.get("today") or date.today().isoformat()
    if args.get("account_id"):  # older name, kept for API callers
        q = q.filter(ChangeEvent.account_id == args["account_id"])
    exact = {"source": ChangeEvent.change_type, "change_type": ChangeEvent.change_type,
             "category": ChangeEvent.category, "account": ChangeEvent.account_id}
    for name, col in exact.items():
        if name != skip and args.get(name):
            q = q.filter(col == args[name])
    when = args.get("when")
    if skip != "when" and when == "planned":
        q = q.filter(ChangeEvent.date > today)
    elif skip != "when" and when == "past":
        q = q.filter(ChangeEvent.date <= today)
    text = (args.get("q") or "").strip()
    if text:
        like = f"%{text}%"
        q = q.filter(or_(ChangeEvent.description.ilike(like), ChangeEvent.note.ilike(like),
                         ChangeEvent.category.ilike(like)))
    if args.get("from"):
        q = q.filter(ChangeEvent.date >= args["from"])
    if args.get("to"):
        q = q.filter(ChangeEvent.date <= args["to"])
    lo, hi = _cents(args.get("min")), _cents(args.get("max"))
    if lo is not None:
        q = q.filter(func.abs(ChangeEvent.amount) >= lo)
    if hi is not None:
        q = q.filter(func.abs(ChangeEvent.amount) <= hi)
    return q


def _options(args):
    """Choices for each dropdown, from the entries the other filters leave."""
    def distinct(name, col):
        return [v for (v,) in _filtered(args, skip=name).with_entities(col).distinct().order_by(col).all() if v]

    accounts = dict(db.session.query(Account.id, Account.name).all())
    return {
        "when": [w for w in ("past", "planned") if _filtered(args, skip="when").filter(
            (ChangeEvent.date > (args.get("today") or date.today().isoformat())) == (w == "planned")).first()],
        "source": distinct("source", ChangeEvent.change_type),
        "category": distinct("category", ChangeEvent.category),
        "account": sorted(({"value": i, "label": accounts.get(i, "(deleted account)")}
                           for i in distinct("account", ChangeEvent.account_id)), key=lambda o: o["label"].lower()),
    }


@bp.route("/changes", methods=["GET"])
def list_changes():
    """One-off entries and imported transactions.

    Without ?limit: every matching entry, newest first (the original list form).
    With ?limit (at most 500) and ?offset: one page as
    {items, total, matched, offset, limit, sum, options}.
    Filters: ?q, ?source (or ?change_type), ?category, ?account, ?when=past|planned,
    ?from, ?to, ?min, ?max (dollars, compared on the absolute amount), ?today.
    Sort: ?sort=date|description|amount|source|category|account and ?dir=asc|desc.
    """
    args = request.args
    q = _filtered(args)
    col = SORTS.get(args.get("sort") or "date", ChangeEvent.date)
    desc = (args.get("dir") or ("desc" if (args.get("sort") or "date") == "date" else "asc")) == "desc"
    q = q.order_by(col.desc() if desc else col.asc(), ChangeEvent.date.desc(), ChangeEvent.id)
    if "limit" not in args:
        return jsonify([ChangeEventSchema.model_validate(c).model_dump() for c in q.all()])
    try:
        limit = min(MAX_LIMIT, max(1, int(args.get("limit"))))
        offset = max(0, int(args.get("offset", 0)))
    except ValueError:
        return jsonify({"error": "limit and offset must be whole numbers"}), 422
    matched, total_sum = q.with_entities(func.count(ChangeEvent.id), func.coalesce(func.sum(ChangeEvent.amount), 0)).order_by(None).one()
    return jsonify({
        "items": [ChangeEventSchema.model_validate(c).model_dump() for c in q.offset(offset).limit(limit).all()],
        "matched": matched, "total": ChangeEvent.query.count(), "sum": total_sum,
        "offset": offset, "limit": limit,
        "options": _options(args) if args.get("options", "1") != "0" else None,
    })


@bp.route("/changes", methods=["POST"])
def create_change():
    data = request.get_json() or {}
    change = ChangeEvent(
        date=data.get("date", ""),
        description=data.get("description", ""),
        amount=int(data.get("amount", 0)),
        account_id=data.get("account_id") or None,
        category=data.get("category") or None,
        change_type=data.get("change_type", "manual"),
        tax_treatment=data.get("tax_treatment") or None,
        snapshot_id=data.get("snapshot_id") or None,
        note=data.get("note") or None,
    )
    db.session.add(change)
    db.session.commit()
    return jsonify(ChangeEventSchema.model_validate(change).model_dump()), 201


@bp.route("/changes/<change_id>", methods=["PATCH"])
def update_change(change_id):
    change = ChangeEvent.query.get(change_id)
    if not change:
        return jsonify({"error": "not found"}), 404
    data = request.get_json() or {}
    for key, value in data.items():
        if hasattr(change, key) and key not in ("id", "created_at"):
            setattr(change, key, value)
    db.session.commit()
    return jsonify(ChangeEventSchema.model_validate(change).model_dump())


@bp.route("/changes/<change_id>", methods=["DELETE"])
def delete_change(change_id):
    change = ChangeEvent.query.get(change_id)
    if not change:
        return jsonify({"error": "not found"}), 404
    db.session.delete(change)
    db.session.commit()
    return "", 204
