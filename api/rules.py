"""REST API for recurring/scheduled rules."""

from flask import Blueprint, request, jsonify
from models import db, Rule
from schemas import RuleSchema
from engine.vest_builder import build_vest_schedule

bp = Blueprint("api_rules", __name__)


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

    # Auto-build RSU vest schedule from config
    if rule_type == "rsu" and config:
        schedule = build_vest_schedule(
            config.get("grant_date", data.get("start_date", "")),
            config.get("total_shares", 0),
            config.get("cliff_months", 12),
            config.get("cliff_percent", 2500),
            config.get("subsequent_frequency", "monthly"),
            config.get("subsequent_percent", 208),
        )

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
        note=data.get("note") or None,
    )
    db.session.add(rule)
    db.session.commit()
    return jsonify(RuleSchema.model_validate(rule).model_dump()), 201


@bp.route("/rules/rsu-preview", methods=["POST"])
def preview_rsu_schedule():
    data = request.get_json() or {}
    config = data.get("config", {})
    schedule = build_vest_schedule(
        config.get("grant_date", ""),
        config.get("total_shares", 0),
        config.get("cliff_months", 12),
        config.get("cliff_percent", 2500),
        config.get("subsequent_frequency", "monthly"),
        config.get("subsequent_percent", 208),
    )
    return jsonify({"schedule": schedule})


@bp.route("/rules/<rule_id>", methods=["PATCH"])
def update_rule(rule_id):
    rule = Rule.query.get(rule_id)
    if not rule:
        return jsonify({"error": "not found"}), 404

    data = request.get_json() or {}

    # Re-build RSU schedule if config fields changed
    if rule.rule_type == "rsu" and "config" in data:
        config = data["config"]
        data["schedule"] = build_vest_schedule(
            config.get("grant_date", rule.start_date),
            config.get("total_shares", 0),
            config.get("cliff_months", 12),
            config.get("cliff_percent", 2500),
            config.get("subsequent_frequency", "monthly"),
            config.get("subsequent_percent", 208),
        )

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
