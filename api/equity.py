"""REST API for equity compensation and alternative assets."""

from flask import Blueprint, request, jsonify
from models import db, Asset
from schemas import AssetSchema

bp = Blueprint("api_equity", __name__)


# ── Unified Assets ────────────────────────────────────────────────────────────

@bp.route("/assets", methods=["GET"])
def list_assets():
    category = request.args.get("category")
    q = Asset.query
    if category:
        q = q.filter_by(category=category)
    return jsonify([AssetSchema.model_validate(a).model_dump() for a in q.all()])


@bp.route("/assets", methods=["POST"])
def create_asset():
    import uuid
    data = request.get_json() or {}
    today = __import__("datetime").date.today().isoformat()
    asset = Asset(
        name=data.get("name", ""),
        category=data.get("category", "other"),
        ticker=data.get("ticker") or None,
        quantity=data.get("quantity"),
        current_value=int(data.get("current_value", 0)),
        cost_basis=int(data["cost_basis"]) if data.get("cost_basis") is not None else None,
        acquired_date=data.get("acquired_date") or None,
        decided_date=data.get("decided_date") or None,
        address=data.get("address") or None,
        linked_loan_id=data.get("linked_loan_id") or None,
        last_updated_date=data.get("last_updated_date") or today,
        scheduled_events=data.get("scheduled_events", []),
        note=data.get("note") or None,
    )
    db.session.add(asset)
    db.session.commit()
    return jsonify(AssetSchema.model_validate(asset).model_dump()), 201


@bp.route("/assets/<asset_id>", methods=["PATCH"])
def update_asset(asset_id):
    asset = Asset.query.get(asset_id)
    if not asset:
        return jsonify({"error": "not found"}), 404

    data = request.get_json() or {}
    for key, value in data.items():
        if hasattr(asset, key) and key not in ["id", "created_at"]:
            setattr(asset, key, value)

    db.session.commit()
    return jsonify(AssetSchema.model_validate(asset).model_dump())


@bp.route("/assets/<asset_id>", methods=["DELETE"])
def delete_asset(asset_id):
    asset = Asset.query.get(asset_id)
    if not asset:
        return jsonify({"error": "not found"}), 404

    db.session.delete(asset)
    db.session.commit()
    return "", 204


@bp.route("/assets/<asset_id>/events", methods=["POST"])
def add_asset_event(asset_id):
    """Append a scheduled event to an asset."""
    from nanoid import generate
    asset = Asset.query.get(asset_id)
    if not asset:
        return jsonify({"error": "not found"}), 404

    data = request.get_json() or {}
    event = {
        "id": generate(),
        "date": data.get("date", ""),
        "type": data.get("type", "acquire"),
        "value": int(data.get("value", 0)),
        "funding": data.get("funding", "cash"),
        "linked_loan_id": data.get("linked_loan_id"),
        "note": data.get("note", ""),
    }
    events = list(asset.scheduled_events or [])
    events.append(event)
    asset.scheduled_events = events
    db.session.commit()
    return jsonify(AssetSchema.model_validate(asset).model_dump())


@bp.route("/assets/<asset_id>/events/<event_id>", methods=["DELETE"])
def delete_asset_event(asset_id, event_id):
    """Remove a scheduled event from an asset."""
    asset = Asset.query.get(asset_id)
    if not asset:
        return jsonify({"error": "not found"}), 404

    asset.scheduled_events = [e for e in (asset.scheduled_events or []) if e.get("id") != event_id]
    db.session.commit()
    return jsonify(AssetSchema.model_validate(asset).model_dump())
