"""REST API for settings and data management."""

from flask import Blueprint, request, jsonify
from models import (
    db,
    Settings,
    Category,
    Account,
    Loan,
    Asset,
    Rule,
    ChangeEvent,
    Snapshot,
    PricePoint,
    ImportMerchantRule,
    ImportProfile,
    OneTimeTxn,
    RecurringTxn,
    BlanketExpense,
    RSUGrant,
    ESPPPlan,
    AccountSnapshot,
)
from schemas import SettingsSchema, CategorySchema
from backup import BackupError, backup_if_configured

bp = Blueprint("api_settings", __name__)


@bp.route("/settings", methods=["GET"])
def get_settings():
    settings = Settings.query.first()
    if not settings:
        settings = Settings()
        db.session.add(settings)
        db.session.commit()

    return jsonify(SettingsSchema.model_validate(settings).model_dump())


@bp.route("/settings", methods=["PATCH"])
def update_settings():
    settings = Settings.query.first()
    if not settings:
        settings = Settings()
        db.session.add(settings)

    data = request.get_json()
    for key, value in data.items():
        if hasattr(settings, key) and key != "id":
            setattr(settings, key, value)

    db.session.commit()
    return jsonify(SettingsSchema.model_validate(settings).model_dump())


@bp.route("/categories", methods=["GET"])
def list_categories():
    categories = Category.query.all()
    return jsonify([CategorySchema.model_validate(c).model_dump() for c in categories])


@bp.route("/categories", methods=["POST"])
def create_category():
    try:
        data = request.get_json()
        schema = CategorySchema(**data)
    except Exception as e:
        return jsonify({"error": str(e)}), 422

    category = Category(**schema.model_dump())
    db.session.add(category)
    db.session.commit()

    return jsonify(CategorySchema.model_validate(category).model_dump()), 201


@bp.route("/categories/<slug>", methods=["PATCH"])
def update_category(slug):
    category = Category.query.get(slug)
    if not category:
        return jsonify({"error": "not found"}), 404

    data = request.get_json()
    for key, value in data.items():
        if hasattr(category, key) and key != "slug":
            setattr(category, key, value)

    db.session.commit()
    return jsonify(CategorySchema.model_validate(category).model_dump())


@bp.route("/categories/<slug>", methods=["DELETE"])
def delete_category(slug):
    category = Category.query.get(slug)
    if not category:
        return jsonify({"error": "not found"}), 404

    if (
        Rule.query.filter_by(category=slug).first()
        or ChangeEvent.query.filter_by(category=slug).first()
        or OneTimeTxn.query.filter_by(category=slug).first()
        or RecurringTxn.query.filter_by(category=slug).first()
        or BlanketExpense.query.filter_by(category=slug).first()
    ):
        return jsonify({"error": "category in use"}), 409

    db.session.delete(category)
    db.session.commit()
    return "", 204


# ── Backup, restore, sample data ──────────────────────────────────────────────
#
# A backup holds every table the app writes to. Version 2 files carry the current
# tables; version 1 files (and old-format rows still sitting in a database) are
# converted into rules, logged changes and recorded balances.

EXPORT_VERSION = 2
TABLES = [
    ("categories", Category), ("accounts", Account), ("loans", Loan), ("assets", Asset), ("rules", Rule),
    ("change_events", ChangeEvent), ("snapshots", Snapshot), ("price_points", PricePoint),
    ("import_merchant_rules", ImportMerchantRule), ("import_profiles", ImportProfile),
]
LEGACY_TABLES = [
    ("one_time_transactions", OneTimeTxn), ("recurring_transactions", RecurringTxn),
    ("blanket_expenses", BlanketExpense), ("rsu_grants", RSUGrant), ("espp_plans", ESPPPlan),
    ("account_snapshots", AccountSnapshot),
]
SETTINGS_KEYS = ("currency", "locale", "fiscal_year_start_month", "default_withholding_rate",
                 "divergence_thresholds", "tax_profile")


def _row(obj) -> dict:
    return {c.name: getattr(obj, c.name) for c in obj.__table__.columns}


def _insert(model, row: dict):
    cols = {c.name for c in model.__table__.columns}
    db.session.add(model(**{k: v for k, v in row.items() if k in cols}))


def legacy_counts() -> dict:
    return {name: model.query.count() for name, model in LEGACY_TABLES}


def convert_legacy(data: dict) -> dict:
    """Old-format rows (as dicts) -> {rules, change_events, snapshots} rows in the current format."""
    rules, changes, snapshots = [], [], []
    for t in data.get("recurring_transactions", []):
        rules.append({"id": t.get("id"), "name": t.get("note") or (t.get("category") or t["type"]).title(),
                      "rule_type": t["type"], "account_id": t.get("account_id"), "amount": t["amount"],
                      "frequency": t["frequency"], "start_date": t["start_date"], "end_date": t.get("end_date"),
                      "category": t.get("category"), "note": t.get("note")})
    for e in data.get("blanket_expenses", []):
        rules.append({"id": e.get("id"), "name": e["label"], "rule_type": "expense", "amount": e["amount"],
                      "frequency": e["frequency"], "start_date": e["start_date"], "end_date": e.get("end_date"),
                      "category": e.get("category"), "note": e.get("note")})
    for g in data.get("rsu_grants", []):
        rules.append({"id": g.get("id"), "name": g["label"], "rule_type": "rsu", "account_id": g.get("account_id"),
                      "start_date": g["grant_date"], "schedule": g.get("vest_schedule") or [],
                      "config": {"ticker": g.get("ticker"), "total_shares": g.get("total_shares"),
                                 "grant_date": g["grant_date"], "price_at_grant": g.get("price_at_grant"),
                                 "withholding_rate": g.get("withholding_rate")},
                      "note": g.get("note")})
    for p in data.get("espp_plans", []):
        rules.append({"id": p.get("id"), "name": p["label"], "rule_type": "espp", "account_id": p.get("account_id"),
                      "start_date": p["offering_start_date"], "end_date": p.get("offering_end_date"),
                      "schedule": p.get("purchase_periods") or [],
                      "config": {"offering_start_date": p["offering_start_date"],
                                 "offering_end_date": p.get("offering_end_date"),
                                 "contribution_mode": p.get("contribution_mode"),
                                 "contribution_value": p.get("contribution_value"),
                                 "base_salary": p.get("base_salary"), "discount_rate": p.get("discount_rate"),
                                 "has_lookback": p.get("has_lookback")},
                      "note": p.get("note")})
    for t in data.get("one_time_transactions", []):
        amount = t["amount"] if t["type"] == "income" else -t["amount"]
        changes.append({"id": t.get("id"), "date": t["date"],
                        "description": t.get("note") or (t.get("category") or t["type"]).title(), "amount": amount,
                        "account_id": t.get("account_id"), "category": t.get("category"), "change_type": "manual",
                        "note": t.get("note")})
    for s in data.get("account_snapshots", []):
        snapshots.append({"id": s.get("id"), "entity_type": "cash", "entity_id": s["account_id"], "date": s["date"],
                          "value": s["actual_balance"], "note": s.get("note")})
    for row in rules + changes + snapshots:
        if not row.get("id"):
            row.pop("id", None)
    return {"rules": rules, "change_events": changes, "snapshots": snapshots}


@bp.route("/export", methods=["GET"])
def export_data():
    settings = Settings.query.first()
    data = {
        "meta": {"version": EXPORT_VERSION},
        "settings": {k: getattr(settings, k) for k in SETTINGS_KEYS} if settings else {},
    }
    for name, model in TABLES:
        data[name] = [_row(o) for o in model.query.all()]
    legacy = {name: [_row(o) for o in model.query.all()] for name, model in LEGACY_TABLES}
    if any(legacy.values()):
        data["legacy"] = legacy
    return jsonify(data), 200, {"Content-Disposition": "attachment; filename=finance_export.json"}


@bp.route("/import", methods=["POST"])
def import_data():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "invalid JSON: expected an exported backup file"}), 400

    version = (data.get("meta") or {}).get("version", 1)
    is_v2 = version >= 2 or "rules" in data

    try:
        backup_if_configured("before-import")
    except BackupError as e:
        return jsonify({"error": f"Nothing was imported because the cloud backup failed: {e}"}), 502

    try:
        for _, model in TABLES + LEGACY_TABLES:
            db.session.query(model).delete()
        converted = {"rules": [], "change_events": [], "snapshots": []}
        if is_v2:
            for name, model in TABLES:
                for row in data.get(name, []):
                    _insert(model, row)
            for name, model in LEGACY_TABLES:
                for row in (data.get("legacy") or {}).get(name, []):
                    _insert(model, row)
        else:
            for name, model in (("categories", Category), ("accounts", Account), ("loans", Loan)):
                for row in data.get(name, []):
                    _insert(model, row)
            converted = convert_legacy(data)
            for name, model in (("rules", Rule), ("change_events", ChangeEvent), ("snapshots", Snapshot)):
                for row in converted[name]:
                    _insert(model, row)
        if isinstance(data.get("settings"), dict):
            settings = Settings.query.first() or Settings()
            db.session.add(settings)
            for key in SETTINGS_KEYS:
                if key in data["settings"]:
                    setattr(settings, key, data["settings"][key])
        db.session.commit()
        return jsonify({"message": "import successful", "version": 2 if is_v2 else 1,
                        "converted": {k: len(v) for k, v in converted.items()}}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"import failed: {str(e)}"}), 422


@bp.route("/legacy", methods=["GET"])
def legacy_status():
    """How many old-format entries are still in the database (the old screens are gone)."""
    counts = legacy_counts()
    return jsonify({"counts": counts, "total": sum(counts.values())})


@bp.route("/legacy/convert", methods=["POST"])
def legacy_convert():
    """Turn old-format entries into rules, logged changes and recorded balances, then clear the old tables."""
    data = {name: [_row(o) for o in model.query.all()] for name, model in LEGACY_TABLES}
    converted = convert_legacy(data)
    try:
        for name, model in (("rules", Rule), ("change_events", ChangeEvent), ("snapshots", Snapshot)):
            for row in converted[name]:
                if row.get("id") and model.query.get(row["id"]):
                    row.pop("id")
                _insert(model, row)
        for _, model in LEGACY_TABLES:
            db.session.query(model).delete()
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"conversion failed: {str(e)}"}), 422
    return jsonify({"converted": {k: len(v) for k, v in converted.items()}})
