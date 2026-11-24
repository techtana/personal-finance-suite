"""REST API for cloud restore points and clearing all data."""

from flask import Blueprint, jsonify, request

import audit
import backup
from backup import BackupError

bp = Blueprint("api_backups", __name__)


def _error(e, status=502):
    return jsonify({"error": str(e)}), status


@bp.route("/backups", methods=["GET"])
def list_backups():
    cfg = backup.get_config()
    result = {
        "config": cfg,
        "configured": backup.is_configured(cfg),
        "frequencies": list(backup.FREQUENCIES),
        "status": backup.status(),
        "can_delete": backup.can_delete(),
        "backups": [],
        "error": None,
    }
    if result["configured"]:
        try:
            store = backup.get_store(cfg)
            result["target"] = store.description
            result["backups"] = backup.list_backups(store)
        except BackupError as e:
            result["error"] = str(e)
    return jsonify(result)


@bp.route("/backups/config", methods=["PATCH"])
def update_config():
    try:
        return jsonify(backup.update_config(request.get_json() or {}))
    except BackupError as e:
        return _error(e, 422)


@bp.route("/backups", methods=["POST"])
def create_backup():
    try:
        return jsonify(backup.create_backup("manual")), 201
    except BackupError as e:
        return _error(e)


@bp.route("/backups/<name>/restore", methods=["POST"])
def restore_backup(name):
    try:
        safety = backup.restore_backup(name)
    except BackupError as e:
        return _error(e)
    audit.record_event("restore", name)
    return jsonify({"message": f"Restored {name}", "safety_backup": safety})


@bp.route("/backups/<name>", methods=["DELETE"])
def delete_backup(name):
    try:
        backup.delete_backup(name)
    except BackupError as e:
        return _error(e, 502 if backup.can_delete() else 403)
    return "", 204


@bp.route("/data/clear", methods=["POST"])
def clear_all_data():
    try:
        saved = backup.clear_all_data()
    except BackupError as e:
        return _error(f"Nothing was deleted because the cloud backup failed: {e}")
    audit.record_event("clear", saved["name"] if saved else None)
    return jsonify({"message": "All data cleared", "backup": saved})
