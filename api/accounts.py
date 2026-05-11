"""REST API for accounts and loans."""

from flask import Blueprint, request, jsonify
from models import db, Account, Loan, AccountSnapshot
from schemas import AccountSchema, LoanSchema, AccountSnapshotSchema

bp = Blueprint("api_accounts", __name__)


@bp.route("/accounts", methods=["GET"])
def list_accounts():
    accounts = Account.query.filter_by(is_active=True).all()
    return jsonify([AccountSchema.model_validate(a).model_dump() for a in accounts])


@bp.route("/accounts", methods=["POST"])
def create_account():
    try:
        data = request.get_json()
        schema = AccountSchema(**data)
    except Exception as e:
        return jsonify({"error": str(e)}), 422

    account = Account(**schema.model_dump(exclude={"id"}))
    db.session.add(account)
    db.session.commit()

    return jsonify(AccountSchema.model_validate(account).model_dump()), 201


@bp.route("/accounts/<account_id>", methods=["GET"])
def get_account(account_id):
    account = Account.query.get(account_id)
    if not account:
        return jsonify({"error": "not found"}), 404

    return jsonify(AccountSchema.model_validate(account).model_dump())


@bp.route("/accounts/<account_id>", methods=["PATCH"])
def update_account(account_id):
    account = Account.query.get(account_id)
    if not account:
        return jsonify({"error": "not found"}), 404

    data = request.get_json()
    for key, value in data.items():
        if hasattr(account, key) and key not in ["id", "created_at"]:
            setattr(account, key, value)

    db.session.commit()
    return jsonify(AccountSchema.model_validate(account).model_dump())


@bp.route("/accounts/<account_id>", methods=["DELETE"])
def delete_account(account_id):
    account = Account.query.get(account_id)
    if not account:
        return jsonify({"error": "not found"}), 404

    account.is_active = False
    db.session.commit()
    return "", 204


@bp.route("/loans", methods=["GET"])
def list_loans():
    loans = Loan.query.all()
    return jsonify([LoanSchema.model_validate(l).model_dump() for l in loans])


@bp.route("/loans", methods=["POST"])
def create_loan():
    try:
        data = request.get_json()
        schema = LoanSchema(**data)
    except Exception as e:
        return jsonify({"error": str(e)}), 422

    loan = Loan(**schema.model_dump(exclude={"id"}))
    db.session.add(loan)
    db.session.commit()

    return jsonify(LoanSchema.model_validate(loan).model_dump()), 201


@bp.route("/loans/<loan_id>", methods=["PATCH"])
def update_loan(loan_id):
    loan = Loan.query.get(loan_id)
    if not loan:
        return jsonify({"error": "not found"}), 404

    data = request.get_json()
    for key, value in data.items():
        if hasattr(loan, key) and key not in ["id", "created_at"]:
            setattr(loan, key, value)

    db.session.commit()
    return jsonify(LoanSchema.model_validate(loan).model_dump())


@bp.route("/loans/<loan_id>", methods=["DELETE"])
def delete_loan(loan_id):
    loan = Loan.query.get(loan_id)
    if not loan:
        return jsonify({"error": "not found"}), 404

    db.session.delete(loan)
    db.session.commit()
    return "", 204


@bp.route("/accounts/<account_id>/snapshots", methods=["POST"])
def create_snapshot(account_id):
    account = Account.query.get(account_id)
    if not account:
        return jsonify({"error": "account not found"}), 404

    try:
        data = request.get_json()
        schema = AccountSnapshotSchema(**data)
    except Exception as e:
        return jsonify({"error": str(e)}), 422

    snapshot = AccountSnapshot(**schema.model_dump(exclude={"id"}))
    db.session.add(snapshot)
    db.session.commit()

    return jsonify(AccountSnapshotSchema.model_validate(snapshot).model_dump()), 201


@bp.route("/accounts/<account_id>/snapshots", methods=["GET"])
def list_snapshots(account_id):
    account = Account.query.get(account_id)
    if not account:
        return jsonify({"error": "account not found"}), 404

    snapshots = AccountSnapshot.query.filter_by(account_id=account_id).order_by(AccountSnapshot.date.desc()).all()
    return jsonify([AccountSnapshotSchema.model_validate(s).model_dump() for s in snapshots])


@bp.route("/accounts/<account_id>/snapshots/<snap_id>", methods=["PATCH"])
def update_snapshot(account_id, snap_id):
    snap = AccountSnapshot.query.filter_by(id=snap_id, account_id=account_id).first()
    if not snap:
        return jsonify({"error": "not found"}), 404

    data = request.get_json()
    for key, value in data.items():
        if hasattr(snap, key) and key not in ["id", "created_at", "account_id"]:
            setattr(snap, key, value)

    db.session.commit()
    return jsonify(AccountSnapshotSchema.model_validate(snap).model_dump())


@bp.route("/accounts/<account_id>/snapshots/<snap_id>", methods=["DELETE"])
def delete_snapshot(account_id, snap_id):
    snap = AccountSnapshot.query.filter_by(id=snap_id, account_id=account_id).first()
    if not snap:
        return jsonify({"error": "not found"}), 404

    db.session.delete(snap)
    db.session.commit()
    return "", 204
