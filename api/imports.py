"""REST API for dropping files to import (statements, receipts, pay stubs)."""

from __future__ import annotations

import hashlib
import os

from flask import Blueprint, current_app, jsonify, request, send_file
from werkzeug.utils import secure_filename

from importer import worker
from importer.extract import ACCEPTED_EXTENSIONS
from importer.llm import get_client
from importer.matching import refresh_matches
from importer.pipeline import (
    CommitError, batch_detail, batch_summary, commit_batch, discard_batch, prepare_reprocess, set_batch_account,
    undo_batch, update_row,
)
from models import Account, ImportBatch, ImportMerchantRule, ImportRow, db

bp = Blueprint("api_imports", __name__)


def _error(message, status=400):
    return jsonify({"error": message}), status


def _get_batch(batch_id):
    return db.session.get(ImportBatch, batch_id)


@bp.errorhandler(CommitError)
def _commit_error(e):
    return _error(str(e), e.status)


@bp.route("/imports/ai-status", methods=["GET"])
def ai_status():
    client = get_client(current_app, "batch")
    status = client.status() if client.enabled else {
        "ok": False, "error": client.blocked_reason, "provider": client.provider, "model": client.model}
    return jsonify(status)


@bp.route("/imports", methods=["GET"])
def list_imports():
    limit = min(int(request.args.get("limit", 30)), 200)
    batches = ImportBatch.query.order_by(ImportBatch.created_at.desc()).limit(limit).all()
    if worker.reap_stale(batches, current_app.config.get("IMPORT_SYNC", False)):
        db.session.commit()
    return jsonify([batch_summary(b) for b in batches])


@bp.route("/imports", methods=["POST"])
def upload():
    files = request.files.getlist("files") or request.files.getlist("file")
    if not files:
        return _error("Attach one or more files in the 'files' field.")
    account_id = request.form.get("account_id") or None
    if account_id and not db.session.get(Account, account_id):
        return _error("unknown account")
    doc_type = request.form.get("doc_type") or None
    if doc_type not in (None, "statement", "receipt", "payslip", "equity"):
        return _error("doc_type must be statement, receipt, payslip or equity")
    max_bytes = current_app.config.get("IMPORT_MAX_FILE_MB", 20) * 1024 * 1024
    storage = current_app.config["IMPORT_STORAGE_DIR"]
    os.makedirs(storage, exist_ok=True)

    created, rejected = [], []
    for f in files:
        name = (f.filename or "upload").strip()[:255]
        ext = os.path.splitext(name.lower())[1]
        if ext and ext not in ACCEPTED_EXTENSIONS:
            rejected.append({"filename": name, "error": f"{ext} files aren't supported. Drop CSV, Excel, OFX/QFX, "
                                                        "PDF, text or a photo (JPG/PNG)."})
            continue
        data = f.read()
        if not data:
            rejected.append({"filename": name, "error": "The file is empty."})
            continue
        if len(data) > max_bytes:
            rejected.append({"filename": name, "error": f"The file is over {max_bytes // (1024 * 1024)} MB."})
            continue
        sha = hashlib.sha256(data).hexdigest()
        batch = ImportBatch(filename=name, file_kind="unknown", file_sha256=sha, file_size=len(data),
                            account_id=account_id, doc_type=doc_type, doc_type_forced=bool(doc_type),
                            status="processing", stage="Waiting to start", warnings=[])
        seen = ImportBatch.query.filter_by(file_sha256=sha, status="committed").first()
        if seen:
            batch.warnings = [{"level": "warn", "sticky": True,
                               "text": f"This exact file was already imported on {(seen.committed_at or '')[:10]}. "
                                       "Rows already imported are marked as duplicates."}]
        db.session.add(batch)
        db.session.flush()
        path = os.path.join(storage, f"{batch.id}_{secure_filename(name) or 'upload'}")
        with open(path, "wb") as out:
            out.write(data)
        batch.stored_path = path
        db.session.commit()
        created.append(batch.id)
    app = current_app._get_current_object()
    for bid in created:
        worker.submit(app, bid)
    batches = [batch_summary(db.session.get(ImportBatch, bid)) for bid in created]
    status = 202 if created else 400
    return jsonify({"imports": batches, "rejected": rejected}), status


@bp.route("/imports/<batch_id>", methods=["GET"])
def get_import(batch_id):
    batch = _get_batch(batch_id)
    if not batch:
        return _error("not found", 404)
    if worker.reap_stale([batch], current_app.config.get("IMPORT_SYNC", False)):
        db.session.commit()
    if batch.status == "review":
        refresh_matches(batch)  # another import may have been committed since this one was read
        db.session.commit()
    return jsonify(batch_detail(batch))


@bp.route("/imports/<batch_id>", methods=["PATCH"])
def patch_import(batch_id):
    """account_id changes in place; doc_type, mapping or flip_signs re-read the file."""
    batch = _get_batch(batch_id)
    if not batch:
        return _error("not found", 404)
    data = request.get_json() or {}
    if "account_id" in data:
        set_batch_account(batch, data["account_id"])
    if any(k in data for k in ("doc_type", "mapping", "flip_signs")):
        prepare_reprocess(batch, doc_type=data.get("doc_type"), mapping=data.get("mapping"),
                          flip_signs=data.get("flip_signs"))
        worker.submit(current_app._get_current_object(), batch.id)
    return jsonify(batch_detail(_get_batch(batch_id)))


@bp.route("/imports/<batch_id>/reprocess", methods=["POST"])
def reprocess(batch_id):
    batch = _get_batch(batch_id)
    if not batch:
        return _error("not found", 404)
    data = request.get_json(silent=True) or {}
    if data.get("reset"):
        batch.mapping, batch.doc_type_forced = None, False
    prepare_reprocess(batch, doc_type=data.get("doc_type"))
    worker.submit(current_app._get_current_object(), batch.id)
    return jsonify(batch_summary(_get_batch(batch_id))), 202


@bp.route("/imports/<batch_id>/rows/<row_id>", methods=["PATCH"])
def patch_row(batch_id, row_id):
    batch = _get_batch(batch_id)
    row = db.session.get(ImportRow, row_id)
    if not batch or not row or row.batch_id != batch.id:
        return _error("not found", 404)
    update_row(batch, row, request.get_json() or {})
    return jsonify(batch_detail(batch))


@bp.route("/imports/<batch_id>/rows/bulk", methods=["POST"])
def bulk_rows(batch_id):
    batch = _get_batch(batch_id)
    if not batch:
        return _error("not found", 404)
    if batch.status != "review":
        return _error("Rows can only be changed while the import is in review.", 409)
    data = request.get_json() or {}
    action = data.get("action")
    if action not in ("import", "skip"):
        return _error("action must be import or skip")
    ids = set(data.get("ids") or [])
    for r in batch.rows:
        if r.id in ids:
            r.action, r.user_edited = action, True
    db.session.commit()
    return jsonify(batch_detail(batch))


@bp.route("/imports/<batch_id>/commit", methods=["POST"])
def commit(batch_id):
    batch = _get_batch(batch_id)
    if not batch:
        return _error("not found", 404)
    created = commit_batch(batch, force=bool((request.get_json(silent=True) or {}).get("force")))
    return jsonify({"created": created, "import": batch_detail(batch)})


@bp.route("/imports/<batch_id>/undo", methods=["POST"])
def undo(batch_id):
    batch = _get_batch(batch_id)
    if not batch:
        return _error("not found", 404)
    result = undo_batch(batch)
    return jsonify({**result, "import": batch_detail(batch)})


@bp.route("/imports/<batch_id>", methods=["DELETE"])
def delete_import(batch_id):
    batch = _get_batch(batch_id)
    if not batch:
        return _error("not found", 404)
    if batch.status == "processing" and worker.is_active(batch.id):
        return _error("Wait for this file to finish processing before deleting it.", 409)
    discard_batch(batch)
    return "", 204


@bp.route("/imports/<batch_id>/file", methods=["GET"])
def get_file(batch_id):
    batch = _get_batch(batch_id)
    if not batch or not batch.stored_path:
        return _error("not found", 404)
    storage = os.path.realpath(current_app.config["IMPORT_STORAGE_DIR"])
    path = os.path.realpath(batch.stored_path)
    if os.path.commonpath([storage, path]) != storage or not os.path.exists(path):
        return _error("not found", 404)
    return send_file(path, download_name=batch.filename, as_attachment=False)


@bp.route("/imports/merchant-rules", methods=["GET"])
def list_merchant_rules():
    rules = ImportMerchantRule.query.order_by(ImportMerchantRule.merchant_key).all()
    return jsonify([{"id": r.id, "merchant_key": r.merchant_key, "category": r.category, "hits": r.hits}
                    for r in rules])


@bp.route("/imports/merchant-rules/<rule_id>", methods=["DELETE"])
def delete_merchant_rule(rule_id):
    rule = db.session.get(ImportMerchantRule, rule_id)
    if not rule:
        return _error("not found", 404)
    db.session.delete(rule)
    db.session.commit()
    return "", 204
