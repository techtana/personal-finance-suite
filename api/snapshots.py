"""REST API for entity snapshots (actual recorded values at specific dates)."""

from flask import Blueprint, request, jsonify
from models import db, Snapshot
from schemas import SnapshotSchema

bp = Blueprint("api_snapshots", __name__)


@bp.route("/snapshots", methods=["GET"])
def list_snapshots():
    entity_type = request.args.get("entity_type")
    entity_id = request.args.get("entity_id")
    q = Snapshot.query
    if entity_type:
        q = q.filter_by(entity_type=entity_type)
    if entity_id:
        q = q.filter_by(entity_id=entity_id)
    snaps = q.order_by(Snapshot.date.desc()).all()
    return jsonify([SnapshotSchema.model_validate(s).model_dump() for s in snaps])


@bp.route("/snapshots", methods=["POST"])
def create_snapshot():
    data = request.get_json() or {}
    snap = Snapshot(
        entity_type=data.get("entity_type", "cash"),
        entity_id=data.get("entity_id", ""),
        date=data.get("date", ""),
        value=int(data.get("value", 0)),
        note=data.get("note") or None,
    )
    db.session.add(snap)
    db.session.commit()
    return jsonify(SnapshotSchema.model_validate(snap).model_dump()), 201


@bp.route("/snapshots/<snap_id>", methods=["PATCH"])
def update_snapshot(snap_id):
    snap = Snapshot.query.get(snap_id)
    if not snap:
        return jsonify({"error": "not found"}), 404
    data = request.get_json() or {}
    for key in ("date", "value", "note"):
        if key in data:
            setattr(snap, key, data[key])
    db.session.commit()
    return jsonify(SnapshotSchema.model_validate(snap).model_dump())


@bp.route("/snapshots/<snap_id>", methods=["DELETE"])
def delete_snapshot(snap_id):
    snap = Snapshot.query.get(snap_id)
    if not snap:
        return jsonify({"error": "not found"}), 404
    db.session.delete(snap)
    db.session.commit()
    return "", 204
