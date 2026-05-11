"""REST API for equity compensation and alternative assets."""

from flask import Blueprint, request, jsonify
from models import db, RSUGrant, ESPPPlan, RealEstate, OtherAsset, Asset
from schemas import RSUGrantSchema, RSUGrantCreateSchema, ESPPPlanSchema, RealEstateSchema, OtherAssetSchema, AssetSchema
from engine.vest_builder import build_vest_schedule

bp = Blueprint("api_equity", __name__)


@bp.route("/equity/rsu", methods=["GET"])
def list_rsu_grants():
    grants = RSUGrant.query.all()
    return jsonify([RSUGrantSchema.model_validate(g).model_dump() for g in grants])


@bp.route("/equity/rsu", methods=["POST"])
def create_rsu_grant():
    try:
        data = request.get_json()
        schema = RSUGrantCreateSchema(**data)
    except Exception as e:
        return jsonify({"error": str(e)}), 422

    vest_schedule = build_vest_schedule(
        schema.grant_date,
        schema.total_shares,
        schema.cliff_months,
        schema.cliff_percent,
        schema.subsequent_frequency,
        schema.subsequent_percent,
    )

    grant = RSUGrant(
        label=schema.label,
        grant_date=schema.grant_date,
        total_shares=schema.total_shares,
        ticker=schema.ticker,
        price_at_grant=schema.price_at_grant,
        vest_schedule=vest_schedule,
        withholding_rate=schema.withholding_rate,
        account_id=schema.account_id,
        note=schema.note,
    )
    db.session.add(grant)
    db.session.commit()

    return jsonify(RSUGrantSchema.model_validate(grant).model_dump()), 201


@bp.route("/equity/rsu/<grant_id>", methods=["PATCH"])
def update_rsu_grant(grant_id):
    grant = RSUGrant.query.get(grant_id)
    if not grant:
        return jsonify({"error": "not found"}), 404

    data = request.get_json()

    if any(k in data for k in ["cliff_months", "cliff_percent", "subsequent_frequency", "subsequent_percent"]):
        cliff_months = data.get("cliff_months", 12)
        cliff_percent = data.get("cliff_percent", 2500)
        subsequent_frequency = data.get("subsequent_frequency", "monthly")
        subsequent_percent = data.get("subsequent_percent", 208)

        vest_schedule = build_vest_schedule(
            grant.grant_date,
            grant.total_shares,
            cliff_months,
            cliff_percent,
            subsequent_frequency,
            subsequent_percent,
        )
        grant.vest_schedule = vest_schedule

    for key, value in data.items():
        if hasattr(grant, key) and key not in ["id", "created_at", "vest_schedule"]:
            setattr(grant, key, value)

    db.session.commit()
    return jsonify(RSUGrantSchema.model_validate(grant).model_dump())


@bp.route("/equity/rsu/<grant_id>", methods=["DELETE"])
def delete_rsu_grant(grant_id):
    grant = RSUGrant.query.get(grant_id)
    if not grant:
        return jsonify({"error": "not found"}), 404

    db.session.delete(grant)
    db.session.commit()
    return "", 204


@bp.route("/equity/rsu/preview-schedule", methods=["POST"])
def preview_rsu_schedule():
    try:
        data = request.get_json()
        schema = RSUGrantCreateSchema(**data)
    except Exception as e:
        return jsonify({"error": str(e)}), 422

    vest_schedule = build_vest_schedule(
        schema.grant_date,
        schema.total_shares,
        schema.cliff_months,
        schema.cliff_percent,
        schema.subsequent_frequency,
        schema.subsequent_percent,
    )

    return jsonify({"vest_schedule": vest_schedule})


@bp.route("/equity/espp", methods=["GET"])
def list_espp_plans():
    plans = ESPPPlan.query.all()
    return jsonify([ESPPPlanSchema.model_validate(p).model_dump() for p in plans])


@bp.route("/equity/espp", methods=["POST"])
def create_espp_plan():
    try:
        data = request.get_json()
        schema = ESPPPlanSchema(**data)
    except Exception as e:
        return jsonify({"error": str(e)}), 422

    purchase_periods = [
        {
            "start_date": p.get("start_date"),
            "end_date": p.get("end_date"),
            "estimated_purchase_amount": p.get("estimated_purchase_amount"),
        }
        for p in schema.purchase_periods
    ]

    plan = ESPPPlan(
        label=schema.label,
        offering_start_date=schema.offering_start_date,
        offering_end_date=schema.offering_end_date,
        contribution_mode=schema.contribution_mode,
        contribution_value=schema.contribution_value,
        base_salary=schema.base_salary,
        discount_rate=schema.discount_rate,
        has_lookback=schema.has_lookback,
        purchase_periods=purchase_periods,
        account_id=schema.account_id,
        note=schema.note,
    )
    db.session.add(plan)
    db.session.commit()

    return jsonify(ESPPPlanSchema.model_validate(plan).model_dump()), 201


@bp.route("/equity/espp/<plan_id>", methods=["PATCH"])
def update_espp_plan(plan_id):
    plan = ESPPPlan.query.get(plan_id)
    if not plan:
        return jsonify({"error": "not found"}), 404

    data = request.get_json()
    for key, value in data.items():
        if hasattr(plan, key) and key not in ["id", "created_at"]:
            setattr(plan, key, value)

    db.session.commit()
    return jsonify(ESPPPlanSchema.model_validate(plan).model_dump())


@bp.route("/equity/espp/<plan_id>", methods=["DELETE"])
def delete_espp_plan(plan_id):
    plan = ESPPPlan.query.get(plan_id)
    if not plan:
        return jsonify({"error": "not found"}), 404

    db.session.delete(plan)
    db.session.commit()
    return "", 204


# ── Real Estate ──────────────────────────────────────────────────────────────

@bp.route("/equity/real-estate", methods=["GET"])
def list_real_estate():
    props = RealEstate.query.all()
    return jsonify([RealEstateSchema.model_validate(p).model_dump() for p in props])


@bp.route("/equity/real-estate", methods=["POST"])
def create_real_estate():
    data = request.get_json() or {}
    prop = RealEstate(
        name=data.get("name", ""),
        address=data.get("address"),
        purchase_price=int(data.get("purchase_price", 0)),
        current_value=int(data.get("current_value", 0)),
        purchase_date=data.get("purchase_date", ""),
        linked_loan_id=data.get("linked_loan_id") or None,
        last_updated_date=data.get("last_updated_date") or None,
        note=data.get("note"),
    )
    db.session.add(prop)
    db.session.commit()
    return jsonify(RealEstateSchema.model_validate(prop).model_dump()), 201


@bp.route("/equity/real-estate/<prop_id>", methods=["PATCH"])
def update_real_estate(prop_id):
    prop = RealEstate.query.get(prop_id)
    if not prop:
        return jsonify({"error": "not found"}), 404

    data = request.get_json() or {}
    for key, value in data.items():
        if hasattr(prop, key) and key not in ["id", "created_at"]:
            setattr(prop, key, value)

    db.session.commit()
    return jsonify(RealEstateSchema.model_validate(prop).model_dump())


@bp.route("/equity/real-estate/<prop_id>", methods=["DELETE"])
def delete_real_estate(prop_id):
    prop = RealEstate.query.get(prop_id)
    if not prop:
        return jsonify({"error": "not found"}), 404

    db.session.delete(prop)
    db.session.commit()
    return "", 204


# ── Other Assets ─────────────────────────────────────────────────────────────

@bp.route("/equity/other-assets", methods=["GET"])
def list_other_assets():
    assets = OtherAsset.query.all()
    return jsonify([OtherAssetSchema.model_validate(a).model_dump() for a in assets])


@bp.route("/equity/other-assets", methods=["POST"])
def create_other_asset():
    data = request.get_json() or {}
    asset = OtherAsset(
        name=data.get("name", ""),
        type=data.get("type", "other"),
        purchase_price=int(data["purchase_price"]) if data.get("purchase_price") is not None else None,
        current_value=int(data.get("current_value", 0)),
        purchase_date=data.get("purchase_date") or None,
        last_updated_date=data.get("last_updated_date") or None,
        note=data.get("note"),
    )
    db.session.add(asset)
    db.session.commit()
    return jsonify(OtherAssetSchema.model_validate(asset).model_dump()), 201


@bp.route("/equity/other-assets/<asset_id>", methods=["PATCH"])
def update_other_asset(asset_id):
    asset = OtherAsset.query.get(asset_id)
    if not asset:
        return jsonify({"error": "not found"}), 404

    data = request.get_json() or {}
    for key, value in data.items():
        if hasattr(asset, key) and key not in ["id", "created_at"]:
            setattr(asset, key, value)

    db.session.commit()
    return jsonify(OtherAssetSchema.model_validate(asset).model_dump())


@bp.route("/equity/other-assets/<asset_id>", methods=["DELETE"])
def delete_other_asset(asset_id):
    asset = OtherAsset.query.get(asset_id)
    if not asset:
        return jsonify({"error": "not found"}), 404

    db.session.delete(asset)
    db.session.commit()
    return "", 204


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
