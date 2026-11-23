"""REST API for the tax estimate (visualize, then analyze)."""

import json
from datetime import datetime
from flask import Blueprint, request, jsonify

from models import db, Settings, Rule, ChangeEvent, Asset, Loan
from engine.tax import estimate_taxes, normalize_profile
from engine.tax_tables import (
    INCOME_TREATMENTS, EXPENSE_TREATMENTS, FILING_STATUSES, TAX_YEARS,
)

bp = Blueprint("api_taxes", __name__)

PROFILE_KEYS = ("filing_status", "state_rate", "age", "hsa_coverage",
                "loss_carryover", "other_gain_short", "other_gain_long")


def _settings():
    settings = Settings.query.first()
    if not settings:
        settings = Settings()
        db.session.add(settings)
        db.session.commit()
    return settings


@bp.route("/taxes/treatments", methods=["GET"])
def list_treatments():
    """Tax treatments the input forms can offer."""
    return jsonify({
        "income": INCOME_TREATMENTS,
        "expense": EXPENSE_TREATMENTS,
        "filing_statuses": [{"key": k, "label": v} for k, v in FILING_STATUSES.items()],
        "years": sorted(TAX_YEARS),
    })


@bp.route("/taxes/profile", methods=["GET"])
def get_profile():
    raw = _settings().tax_profile or {}
    profile, assumptions = normalize_profile(raw)
    return jsonify({"profile": profile, "saved": raw, "assumptions": assumptions})


@bp.route("/taxes/profile", methods=["PATCH"])
def update_profile():
    settings = _settings()
    data = request.get_json() or {}
    profile = dict(settings.tax_profile or {})
    for key in PROFILE_KEYS:
        if key not in data:
            continue
        value = data[key]
        if value is None or value == "":
            profile.pop(key, None)  # back to "not set"
        elif key in ("filing_status", "hsa_coverage"):
            profile[key] = str(value)
        else:
            try:
                profile[key] = int(value)
            except (TypeError, ValueError):
                return jsonify({"error": f"{key} must be a number"}), 422
    settings.tax_profile = profile
    db.session.commit()
    normalized, assumptions = normalize_profile(profile)
    return jsonify({"profile": normalized, "saved": profile, "assumptions": assumptions})


@bp.route("/taxes/summary", methods=["GET"])
def tax_summary():
    """Estimated taxes for one calendar year, from every input in the app."""
    try:
        year = int(request.args.get("year") or datetime.utcnow().year)
    except ValueError:
        return jsonify({"error": "year must be a number"}), 422
    try:
        stock_prices = json.loads(request.args.get("prices", "{}"))
    except Exception:
        stock_prices = {}

    rules = [
        {"id": r.id, "name": r.name, "rule_type": r.rule_type, "amount": r.amount,
         "frequency": r.frequency, "start_date": r.start_date, "end_date": r.end_date,
         "schedule": r.schedule, "config": r.config, "is_active": r.is_active,
         "tax_treatment": r.tax_treatment}
        for r in Rule.query.filter_by(is_active=True).all()
    ]
    changes = [
        {"id": c.id, "date": c.date, "description": c.description, "amount": c.amount,
         "change_type": c.change_type, "tax_treatment": c.tax_treatment}
        for c in ChangeEvent.query.all()
    ]
    assets = [
        {"id": a.id, "name": a.name, "category": a.category, "current_value": a.current_value,
         "cost_basis": a.cost_basis, "acquired_date": a.acquired_date,
         "scheduled_events": a.scheduled_events}
        for a in Asset.query.all()
    ]
    loans = [
        {"id": l.id, "name": l.name, "type": l.type, "original_balance": l.original_balance,
         "interest_rate": l.interest_rate, "monthly_payment": l.monthly_payment,
         "start_date": l.start_date}
        for l in Loan.query.all()
    ]

    result = estimate_taxes(rules, changes, assets, loans, _settings().tax_profile, year, stock_prices)
    return jsonify(result)
