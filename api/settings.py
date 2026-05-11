"""REST API for settings and data management."""

import json
from flask import Blueprint, request, jsonify
from models import (
    db,
    Settings,
    Category,
    Account,
    Loan,
    OneTimeTxn,
    RecurringTxn,
    BlanketExpense,
    RSUGrant,
    ESPPPlan,
    AccountSnapshot,
)
from schemas import SettingsSchema, CategorySchema

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
        OneTimeTxn.query.filter_by(category=slug).first()
        or RecurringTxn.query.filter_by(category=slug).first()
        or BlanketExpense.query.filter_by(category=slug).first()
    ):
        return jsonify({"error": "category in use"}), 409

    db.session.delete(category)
    db.session.commit()
    return "", 204


@bp.route("/export", methods=["GET"])
def export_data():
    data = {
        "meta": {"version": 1},
        "accounts": [
            {
                "id": a.id,
                "name": a.name,
                "type": a.type,
                "institution": a.institution,
                "currency": a.currency,
                "current_balance": a.current_balance,
                "last_updated_date": a.last_updated_date,
                "is_active": a.is_active,
                "note": a.note,
            }
            for a in Account.query.all()
        ],
        "loans": [
            {
                "id": l.id,
                "name": l.name,
                "type": l.type,
                "institution": l.institution,
                "original_balance": l.original_balance,
                "current_balance": l.current_balance,
                "interest_rate": l.interest_rate,
                "monthly_payment": l.monthly_payment,
                "start_date": l.start_date,
                "payoff_date": l.payoff_date,
                "note": l.note,
            }
            for l in Loan.query.all()
        ],
        "one_time_transactions": [
            {
                "id": t.id,
                "type": t.type,
                "amount": t.amount,
                "date": t.date,
                "category": t.category,
                "account_id": t.account_id,
                "note": t.note,
            }
            for t in OneTimeTxn.query.all()
        ],
        "recurring_transactions": [
            {
                "id": t.id,
                "type": t.type,
                "amount": t.amount,
                "frequency": t.frequency,
                "start_date": t.start_date,
                "end_date": t.end_date,
                "category": t.category,
                "account_id": t.account_id,
                "note": t.note,
            }
            for t in RecurringTxn.query.all()
        ],
        "blanket_expenses": [
            {
                "id": e.id,
                "label": e.label,
                "amount": e.amount,
                "frequency": e.frequency,
                "start_date": e.start_date,
                "end_date": e.end_date,
                "category": e.category,
                "note": e.note,
            }
            for e in BlanketExpense.query.all()
        ],
        "rsu_grants": [
            {
                "id": g.id,
                "label": g.label,
                "grant_date": g.grant_date,
                "total_shares": g.total_shares,
                "ticker": g.ticker,
                "price_at_grant": g.price_at_grant,
                "vest_schedule": g.vest_schedule,
                "withholding_rate": g.withholding_rate,
                "account_id": g.account_id,
                "note": g.note,
            }
            for g in RSUGrant.query.all()
        ],
        "espp_plans": [
            {
                "id": p.id,
                "label": p.label,
                "offering_start_date": p.offering_start_date,
                "offering_end_date": p.offering_end_date,
                "contribution_mode": p.contribution_mode,
                "contribution_value": p.contribution_value,
                "base_salary": p.base_salary,
                "discount_rate": p.discount_rate,
                "has_lookback": p.has_lookback,
                "purchase_periods": p.purchase_periods,
                "account_id": p.account_id,
                "note": p.note,
            }
            for p in ESPPPlan.query.all()
        ],
        "account_snapshots": [
            {
                "id": s.id,
                "account_id": s.account_id,
                "date": s.date,
                "actual_balance": s.actual_balance,
                "predicted_balance": s.predicted_balance,
                "delta": s.delta,
                "resolution": s.resolution,
                "note": s.note,
            }
            for s in AccountSnapshot.query.all()
        ],
        "categories": [
            {
                "slug": c.slug,
                "label": c.label,
                "type": c.type,
                "color": c.color,
            }
            for c in Category.query.all()
        ],
    }

    return jsonify(data), 200, {"Content-Disposition": "attachment; filename=finance_export.json"}


@bp.route("/import", methods=["POST"])
def import_data():
    try:
        data = request.get_json()
    except Exception as e:
        return jsonify({"error": f"invalid JSON: {str(e)}"}), 400

    try:
        db.session.query(AccountSnapshot).delete()
        db.session.query(ESPPPlan).delete()
        db.session.query(RSUGrant).delete()
        db.session.query(BlanketExpense).delete()
        db.session.query(RecurringTxn).delete()
        db.session.query(OneTimeTxn).delete()
        db.session.query(Loan).delete()
        db.session.query(Account).delete()
        db.session.query(Category).delete()

        for cat_data in data.get("categories", []):
            db.session.add(Category(**cat_data))

        for acc_data in data.get("accounts", []):
            db.session.add(Account(**acc_data))

        for loan_data in data.get("loans", []):
            db.session.add(Loan(**loan_data))

        for txn_data in data.get("one_time_transactions", []):
            db.session.add(OneTimeTxn(**txn_data))

        for txn_data in data.get("recurring_transactions", []):
            db.session.add(RecurringTxn(**txn_data))

        for exp_data in data.get("blanket_expenses", []):
            db.session.add(BlanketExpense(**exp_data))

        for grant_data in data.get("rsu_grants", []):
            db.session.add(RSUGrant(**grant_data))

        for plan_data in data.get("espp_plans", []):
            db.session.add(ESPPPlan(**plan_data))

        for snap_data in data.get("account_snapshots", []):
            db.session.add(AccountSnapshot(**snap_data))

        db.session.commit()
        return jsonify({"message": "import successful"}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"import failed: {str(e)}"}), 422


@bp.route("/seed", methods=["POST"])
def seed_sample_data():
    db.session.query(AccountSnapshot).delete()
    db.session.query(ESPPPlan).delete()
    db.session.query(RSUGrant).delete()
    db.session.query(BlanketExpense).delete()
    db.session.query(RecurringTxn).delete()
    db.session.query(OneTimeTxn).delete()
    db.session.query(Loan).delete()
    db.session.query(Account).delete()
    db.session.query(Category).delete()

    default_categories = [
        {"slug": "salary", "label": "Salary", "type": "income", "color": "#10b981"},
        {"slug": "bonus", "label": "Bonus", "type": "income", "color": "#06b6d4"},
        {"slug": "equity", "label": "Equity", "type": "income", "color": "#8b5cf6"},
        {"slug": "rent", "label": "Rent", "type": "expense", "color": "#ef4444"},
        {"slug": "utilities", "label": "Utilities", "type": "expense", "color": "#f59e0b"},
        {"slug": "groceries", "label": "Groceries", "type": "expense", "color": "#f97316"},
        {"slug": "misc", "label": "Misc", "type": "expense", "color": "#6b7280"},
        {"slug": "debt", "label": "Debt", "type": "expense", "color": "#dc2626"},
    ]

    for cat_data in default_categories:
        db.session.add(Category(**cat_data))

    accounts = [
        Account(
            name="Chase Checking",
            type="checking",
            institution="Chase",
            currency="USD",
            current_balance=1240000,
            last_updated_date="2026-05-10",
        ),
        Account(
            name="Fidelity Brokerage",
            type="brokerage",
            institution="Fidelity",
            currency="USD",
            current_balance=14280000,
            last_updated_date="2026-05-10",
        ),
        Account(
            name="401k",
            type="retirement_401k",
            institution="Employer",
            currency="USD",
            current_balance=45000000,
            last_updated_date="2026-05-10",
        ),
    ]

    for acc in accounts:
        db.session.add(acc)

    db.session.commit()

    salary_account = Account.query.filter_by(name="Chase Checking").first()
    if salary_account:
        salary_txn = RecurringTxn(
            type="income",
            amount=1000000,
            frequency="monthly",
            start_date="2026-01-01",
            category="salary",
            account_id=salary_account.id,
            note="Monthly salary",
        )
        db.session.add(salary_txn)

    db.session.commit()

    return jsonify({"message": "sample data loaded"}), 201
