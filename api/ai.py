"""What AI can do right now, and the door the home computer collects its work through.

/capabilities is what the pages read to decide which AI controls to show. A feature that
can't work is simply not shown; Settings → This device lists every feature and why.
"""

import hmac
import logging

from flask import Blueprint, current_app, jsonify, request

import audit
from ai import endpoints, relay
from importer.llm import get_client

bp = Blueprint("api_ai", __name__)
log = logging.getLogger(__name__)

# kind "realtime": someone is waiting for the answer. kind "batch": the work can wait.
FEATURES = [
    {"id": "assistant", "kind": "realtime", "label": "Ask, filter in words, explain and draft",
     "where": "Insights, Plan and the list filters"},
    {"id": "import_ai", "kind": "batch", "label": "Read photos, scans and unusual files",
     "where": "Import"},
]


def feature_states(app) -> list[dict]:
    out = []
    for f in FEATURES:
        s = get_client(app, f["kind"]).status()
        ok, waiting = bool(s.get("ok")), bool(s.get("waiting"))
        note = None
        if ok and s.get("asleep"):
            note = "The service starts when it is needed, so the first answer takes longer."
        elif waiting:
            note = "Files wait and are read when the home computer is on."
        out.append({**f, "available": ok, "waiting": waiting, "shown": ok or waiting,
                    "through": s.get("through") or (ok and "The app's AI model") or None,
                    "model": s.get("model") if ok else None, "note": note,
                    "reason": None if ok else (s.get("error") or "No AI endpoint is set up.")})
    return out


@bp.route("/capabilities", methods=["GET"])
def capabilities():
    app = current_app._get_current_object()
    return jsonify({
        "features": feature_states(app),
        "endpoints": endpoints.describe(app.config),
        "home_runner": {"enabled": bool(app.config.get("AI_HOME_RUNNER")), **relay.info()},
        "identity": audit.identity(),
    })


# ── the home runner's side ────────────────────────────────────────────────────

def _runner_allowed():
    if not current_app.config.get("AI_HOME_RUNNER"):
        return jsonify({"error": "The home runner is turned off on this server (AI_HOME_RUNNER=1 turns it on)."}), 404
    token = current_app.config.get("AI_RUNNER_TOKEN") or ""
    if token and not hmac.compare_digest(token, request.headers.get("X-Runner-Token", "")):
        return jsonify({"error": "Wrong runner token."}), 403
    return None


@bp.route("/ai/runner/poll", methods=["POST"])
def runner_poll():
    """Long poll: answers with the next model request, or {"job": null} after `wait` seconds."""
    refused = _runner_allowed()
    if refused:
        return refused
    body = request.get_json(silent=True) or {}
    try:
        wait = max(0.0, min(float(body.get("wait", 25)), 25.0))
    except (TypeError, ValueError):
        wait = 25.0
    return jsonify({"job": relay.poll(body, wait)})


@bp.route("/ai/runner/result", methods=["POST"])
def runner_result():
    refused = _runner_allowed()
    if refused:
        return refused
    body = request.get_json(silent=True) or {}
    accepted = relay.complete(str(body.get("id") or ""), content=body.get("content"),
                              error=body.get("error") or None, unavailable=bool(body.get("unavailable")))
    return jsonify({"accepted": accepted})


# ── files that were waiting for the home computer ─────────────────────────────

_app = None


def _resume_waiting_imports():
    """The home computer just connected: read the files that were waiting for it."""
    app = _app
    if app is None:
        return
    from importer import worker
    from models import ImportBatch, db

    try:
        with app.app_context():
            waiting = ImportBatch.query.filter_by(status="waiting").all()
            for batch in waiting:
                batch.status, batch.stage = "processing", "Waiting to start"
            db.session.commit()
            for batch in waiting:
                worker.submit(app, batch.id)
    except Exception:  # never let this break the runner's poll
        log.exception("could not resume imports that were waiting for the home computer")


def init_app(app) -> None:
    global _app
    _app = app
    relay.on_connect(_resume_waiting_imports)
