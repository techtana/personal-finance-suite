"""REST API for transactions."""

from flask import Blueprint, request, jsonify
from models import db, OneTimeTxn, RecurringTxn, BlanketExpense
from schemas import OneTimeTxnSchema, RecurringTxnSchema, BlanketExpenseSchema

bp = Blueprint("api_transactions", __name__)


@bp.route("/transactions/one-time", methods=["GET"])
def list_one_time_txns():
    query = OneTimeTxn.query

    date_from = request.args.get("from")
    date_to = request.args.get("to")
    category = request.args.get("category")
    account_id = request.args.get("account")

    if date_from:
        query = query.filter(OneTimeTxn.date >= date_from)
    if date_to:
        query = query.filter(OneTimeTxn.date <= date_to)
    if category:
        query = query.filter_by(category=category)
    if account_id:
        query = query.filter_by(account_id=account_id)

    txns = query.order_by(OneTimeTxn.date.desc()).all()
    return jsonify([OneTimeTxnSchema.model_validate(t).model_dump() for t in txns])


@bp.route("/transactions/one-time", methods=["POST"])
def create_one_time_txn():
    try:
        data = request.get_json()
        schema = OneTimeTxnSchema(**data)
    except Exception as e:
        return jsonify({"error": str(e)}), 422

    txn = OneTimeTxn(**schema.model_dump(exclude={"id"}))
    db.session.add(txn)
    db.session.commit()

    return jsonify(OneTimeTxnSchema.model_validate(txn).model_dump()), 201


@bp.route("/transactions/one-time/<txn_id>", methods=["PATCH"])
def update_one_time_txn(txn_id):
    txn = OneTimeTxn.query.get(txn_id)
    if not txn:
        return jsonify({"error": "not found"}), 404

    data = request.get_json()
    for key, value in data.items():
        if hasattr(txn, key) and key not in ["id", "created_at"]:
            setattr(txn, key, value)

    db.session.commit()
    return jsonify(OneTimeTxnSchema.model_validate(txn).model_dump())


@bp.route("/transactions/one-time/<txn_id>", methods=["DELETE"])
def delete_one_time_txn(txn_id):
    txn = OneTimeTxn.query.get(txn_id)
    if not txn:
        return jsonify({"error": "not found"}), 404

    db.session.delete(txn)
    db.session.commit()
    return "", 204


@bp.route("/transactions/recurring", methods=["GET"])
def list_recurring_txns():
    txns = RecurringTxn.query.all()
    return jsonify([RecurringTxnSchema.model_validate(t).model_dump() for t in txns])


@bp.route("/transactions/recurring", methods=["POST"])
def create_recurring_txn():
    try:
        data = request.get_json()
        schema = RecurringTxnSchema(**data)
    except Exception as e:
        return jsonify({"error": str(e)}), 422

    txn = RecurringTxn(**schema.model_dump(exclude={"id"}))
    db.session.add(txn)
    db.session.commit()

    return jsonify(RecurringTxnSchema.model_validate(txn).model_dump()), 201


@bp.route("/transactions/recurring/<txn_id>", methods=["PATCH"])
def update_recurring_txn(txn_id):
    txn = RecurringTxn.query.get(txn_id)
    if not txn:
        return jsonify({"error": "not found"}), 404

    data = request.get_json()
    for key, value in data.items():
        if hasattr(txn, key) and key not in ["id", "created_at"]:
            setattr(txn, key, value)

    db.session.commit()
    return jsonify(RecurringTxnSchema.model_validate(txn).model_dump())


@bp.route("/transactions/recurring/<txn_id>", methods=["DELETE"])
def delete_recurring_txn(txn_id):
    txn = RecurringTxn.query.get(txn_id)
    if not txn:
        return jsonify({"error": "not found"}), 404

    db.session.delete(txn)
    db.session.commit()
    return "", 204


@bp.route("/blanket-expenses", methods=["GET"])
def list_blanket_expenses():
    expenses = BlanketExpense.query.all()
    return jsonify([BlanketExpenseSchema.model_validate(e).model_dump() for e in expenses])


@bp.route("/blanket-expenses", methods=["POST"])
def create_blanket_expense():
    try:
        data = request.get_json()
        schema = BlanketExpenseSchema(**data)
    except Exception as e:
        return jsonify({"error": str(e)}), 422

    expense = BlanketExpense(**schema.model_dump(exclude={"id"}))
    db.session.add(expense)
    db.session.commit()

    return jsonify(BlanketExpenseSchema.model_validate(expense).model_dump()), 201


@bp.route("/blanket-expenses/<expense_id>", methods=["PATCH"])
def update_blanket_expense(expense_id):
    expense = BlanketExpense.query.get(expense_id)
    if not expense:
        return jsonify({"error": "not found"}), 404

    data = request.get_json()
    for key, value in data.items():
        if hasattr(expense, key) and key not in ["id", "created_at"]:
            setattr(expense, key, value)

    db.session.commit()
    return jsonify(BlanketExpenseSchema.model_validate(expense).model_dump())


@bp.route("/blanket-expenses/<expense_id>", methods=["DELETE"])
def delete_blanket_expense(expense_id):
    expense = BlanketExpense.query.get(expense_id)
    if not expense:
        return jsonify({"error": "not found"}), 404

    db.session.delete(expense)
    db.session.commit()
    return "", 204
