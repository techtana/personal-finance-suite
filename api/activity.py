"""Who is signed in, and the log of changes."""

from flask import Blueprint, jsonify, request

import audit
from models import AuditLog

bp = Blueprint("api_activity", __name__)

TABLE_LABELS = {
    "accounts": "Account", "loans": "Loan", "assets": "Asset", "real_estate": "Property",
    "other_assets": "Other asset", "snapshots": "Balance", "account_snapshots": "Balance",
    "rules": "Recurring entry", "change_events": "One-off entry", "price_points": "Price",
    "categories": "Category", "settings": "Settings", "import_batches": "Imported file",
    "import_merchant_rules": "Learned category", "import_profiles": "Import layout",
    "one_time_txns": "Transaction", "recurring_txns": "Recurring transaction",
    "blanket_expenses": "Expense", "rsu_grants": "RSU grant", "espp_plans": "ESPP plan",
    "restore": "Restore from a backup", "clear": "Clear all data",
}
ACTIONS = {"create": "added", "update": "changed", "delete": "deleted", "event": "ran"}


@bp.route("/whoami", methods=["GET"])
def whoami():
    return jsonify(audit.identity())


@bp.route("/activity", methods=["GET"])
def activity():
    limit = max(1, min(int(request.args.get("limit", 100)), 500))
    rows = AuditLog.query.order_by(AuditLog.id.desc()).limit(limit).all()
    return jsonify({
        "rev": audit.current_rev(),
        "entries": [{
            "id": r.id, "at": r.at, "who": r.who, "action": r.action, "action_label": ACTIONS.get(r.action, r.action),
            "kind": TABLE_LABELS.get(r.table_name, r.table_name.replace("_", " ").capitalize()),
            "label": r.label, "fields": r.fields or [],
        } for r in rows],
    })
