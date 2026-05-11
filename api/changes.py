"""REST API for manual change events (one-time cash-flow entries)."""

from flask import Blueprint, request, jsonify
from models import db, ChangeEvent
from schemas import ChangeEventSchema

bp = Blueprint("api_changes", __name__)


@bp.route("/changes", methods=["GET"])
def list_changes():
    account_id = request.args.get("account_id")
    change_type = request.args.get("change_type")
    q = ChangeEvent.query
    if account_id:
        q = q.filter_by(account_id=account_id)
    if change_type:
        q = q.filter_by(change_type=change_type)
    changes = q.order_by(ChangeEvent.date.desc()).all()
    return jsonify([ChangeEventSchema.model_validate(c).model_dump() for c in changes])


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
