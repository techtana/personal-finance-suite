"""REST API for recurring/scheduled rules."""

from flask import Blueprint, request, jsonify
from models import db, Rule
from schemas import RuleSchema
from engine.vest_builder import build_vest_schedule

bp = Blueprint("api_rules", __name__)

NO_SCHEDULE = ("These vesting settings don't make a schedule. Check the grant date, the cliff percent "
               "(0-100) and the percent per later vest (more than 0 unless the cliff vests everything).")


def _rsu_schedule(config: dict, default_date: str) -> list[dict]:
    """Vest dates from the Plan form's cliff + later-vest settings; [] if they don't make a schedule."""
    try:
        return build_vest_schedule(
            config.get("grant_date") or default_date or "",
            int(config.get("total_shares") or 0),
            int(config.get("cliff_months") if config.get("cliff_months") is not None else 12),
            int(config.get("cliff_percent") if config.get("cliff_percent") is not None else 2500),
            config.get("subsequent_frequency") or "monthly",
            int(config.get("subsequent_percent") if config.get("subsequent_percent") is not None else 208),
        )
    except (TypeError, ValueError):
        return []


@bp.route("/rules", methods=["GET"])
def list_rules():
    rule_type = request.args.get("rule_type")
    q = Rule.query.filter_by(is_active=True)
    if rule_type:
        q = q.filter_by(rule_type=rule_type)
    return jsonify([RuleSchema.model_validate(r).model_dump() for r in q.all()])


@bp.route("/rules", methods=["POST"])
def create_rule():
    data = request.get_json() or {}
    rule_type = data.get("rule_type", "income")
    config = data.get("config") or {}
    schedule = data.get("schedule")

    # Auto-build RSU vest schedule from config, unless the dates came from the grant document
    if rule_type == "rsu" and config and not (config.get("schedule_source") == "document" and schedule):
        schedule = _rsu_schedule(config, data.get("start_date", ""))
        if not schedule:
            return jsonify({"error": NO_SCHEDULE}), 400

    rule = Rule(
        name=data.get("name", ""),
        rule_type=rule_type,
        account_id=data.get("account_id") or None,
        amount=int(data["amount"]) if data.get("amount") is not None else None,
        frequency=data.get("frequency") or None,
        start_date=data.get("start_date", ""),
        end_date=data.get("end_date") or None,
        category=data.get("category") or None,
        schedule=schedule,
        config=config or None,
        tax_treatment=data.get("tax_treatment") or None,
        note=data.get("note") or None,
    )
    db.session.add(rule)
    db.session.commit()
    return jsonify(RuleSchema.model_validate(rule).model_dump()), 201


@bp.route("/rules/rsu-preview", methods=["POST"])
def preview_rsu_schedule():
    data = request.get_json() or {}
    config = data.get("config", {})
    schedule = _rsu_schedule(config, "")
    return jsonify({"schedule": schedule, "error": None if schedule else NO_SCHEDULE})


@bp.route("/rules/<rule_id>", methods=["PATCH"])
def update_rule(rule_id):
    rule = Rule.query.get(rule_id)
    if not rule:
        return jsonify({"error": "not found"}), 404

    data = request.get_json() or {}

    # Re-build RSU schedule if config fields changed, unless the dates came from the grant document
    from_document = ((rule.config or {}).get("schedule_source") == "document"
                     and (data.get("config") or {}).get("schedule_source", "document") == "document")
    if from_document and "config" in data:
        data["config"] = {**(rule.config or {}), **data["config"], "schedule_source": "document"}
        data.pop("schedule", None)
    elif rule.rule_type == "rsu" and "config" in data:
        config = data["config"]
        data["schedule"] = _rsu_schedule(config, rule.start_date)
        if not data["schedule"]:
            return jsonify({"error": NO_SCHEDULE}), 400

    for key, value in data.items():
        if hasattr(rule, key) and key not in ("id", "created_at"):
            setattr(rule, key, value)

    db.session.commit()
    return jsonify(RuleSchema.model_validate(rule).model_dump())


@bp.route("/rules/<rule_id>", methods=["DELETE"])
def delete_rule(rule_id):
    rule = Rule.query.get(rule_id)
    if not rule:
        return jsonify({"error": "not found"}), 404
    db.session.delete(rule)
    db.session.commit()
    return "", 204
