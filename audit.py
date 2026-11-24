"""Who changed what, and refusing saves made on top of out-of-date data.

Three things, all hooked into the database session so no endpoint has to remember them:

  Identity     Behind Tailscale Serve the app learns who is asking from the
               Tailscale-User-Login header. That header is believed only when
               TRUST_TAILSCALE_HEADERS=1, which is only safe when nothing but Serve can
               reach the app (it listens on 127.0.0.1). ALLOWED_LOGINS narrows it further.

  Audit log    Every record created, changed or deleted through the app gets a row in
               audit_log: time, who, which record, which fields. Never the values.

  Stale saves  The newest audit row id is the data revision; every API answer carries it
               in X-Data-Rev. A page sends the revision it last read (X-Base-Rev) with a
               change. If someone else changed the same record after that, the save is
               refused with 409 instead of silently overwriting their edit.
"""

from __future__ import annotations

import logging
import threading
from contextlib import contextmanager

from flask import current_app, has_request_context, jsonify, request
from sqlalchemy import event, func, inspect, select

from models import AuditLog, db, get_iso_datetime

log = logging.getLogger(__name__)

# audit_log is the log itself. Import rows are proposals, logged once at the batch level.
SKIP_TABLES = {"audit_log", "import_rows"}
_LABEL_ATTRS = ("name", "label", "filename", "symbol", "slug", "date")


class StaleWrite(Exception):
    """Someone else changed this record after the page read it."""

    def __init__(self, what: str, who: str, at: str):
        self.what, self.who, self.at = what, who, at
        super().__init__(f"{what} was changed by {who} after this page loaded it. "
                         "Reload to see the latest version, then make your change again.")


# ── identity ──────────────────────────────────────────────────────────────────

def identity() -> dict:
    """{login, name, trusted}. 'local' when the app is not behind Tailscale Serve."""
    if not has_request_context():
        return {"login": "app", "name": "The app itself", "trusted": False}
    if not current_app.config.get("TRUST_TAILSCALE_HEADERS"):
        return {"login": "local", "name": "This computer", "trusted": False}
    login = (request.headers.get("Tailscale-User-Login") or "").strip().lower()
    name = (request.headers.get("Tailscale-User-Name") or "").strip()
    # Tagged machines (servers) reach the app with no login at all.
    return {"login": login or "tagged-device", "name": name or login or "A tagged device", "trusted": True}


def _client_id() -> str:
    return (request.headers.get("X-Client-Id") or "")[:40] if has_request_context() else ""


def _path() -> str | None:
    return f"{request.method} {request.path}"[:200] if has_request_context() else None


# ── session hooks ─────────────────────────────────────────────────────────────

def _pk(obj) -> str:
    return "/".join(str(v) for v in inspect(obj).mapper.primary_key_from_instance(obj))[:64]


def _label(obj) -> str | None:
    for attr in _LABEL_ATTRS:
        value = getattr(obj, attr, None)
        if isinstance(value, str) and value:
            return value[:120]
    return None


def _changed_fields(obj) -> list[str]:
    state = inspect(obj)
    return sorted(a.key for a in state.mapper.column_attrs
                  if a.key != "updated_at" and state.attrs[a.key].history.has_changes())


_quiet = threading.local()


@contextmanager
def processing():
    """Reading an imported file: its progress updates are not changes someone made."""
    _quiet.on = True
    try:
        yield
    finally:
        _quiet.on = False


def _tracked(obj) -> bool:
    table = getattr(obj, "__tablename__", None)
    if table == "import_batches" and getattr(_quiet, "on", False):
        return False
    return table is not None and table not in SKIP_TABLES


def _check_stale(session, flush_context, instances):
    if not has_request_context():
        return
    base = request.headers.get("X-Base-Rev", "")
    if not base.isdigit():
        return  # scripts and older pages don't say what they read; nothing to compare
    mine = _client_id()
    touched = [o for o in session.dirty if _tracked(o) and session.is_modified(o)]
    touched += [o for o in session.deleted if _tracked(o)]
    if not touched:
        return
    conn = session.connection()
    t = AuditLog.__table__
    for obj in touched:
        row = conn.execute(
            select(t.c.who, t.c.at).where(t.c.table_name == obj.__tablename__, t.c.record_id == _pk(obj),
                                          t.c.id > int(base), t.c.client != mine)
            .order_by(t.c.id.desc()).limit(1)).first()
        if row:
            what = _label(obj) or obj.__tablename__.replace("_", " ")
            raise StaleWrite(f'"{what}"', row.who, row.at)


def _record(session, flush_context):
    rows = []
    who, client, path, now = identity()["login"], _client_id(), _path(), get_iso_datetime()

    def add(action, obj, fields=None):
        rows.append({"at": now, "who": who, "client": client, "action": action,
                     "table_name": obj.__tablename__, "record_id": _pk(obj), "label": _label(obj),
                     "fields": fields, "path": path})

    for obj in session.new:
        if _tracked(obj):
            add("create", obj)
    for obj in session.dirty:
        if _tracked(obj) and session.is_modified(obj):
            fields = _changed_fields(obj)
            if fields:
                add("update", obj, fields)
    for obj in session.deleted:
        if _tracked(obj):
            add("delete", obj)
    if rows:
        session.connection().execute(AuditLog.__table__.insert(), rows)


def record_event(what: str, label: str | None = None) -> None:
    """A whole-database action (restore, clear) that the per-record hooks can't see."""
    db.session.add(AuditLog(who=identity()["login"], client=_client_id(), action="event", table_name=what,
                            record_id="", label=(label or "")[:120] or None, path=_path()))
    db.session.commit()


def current_rev() -> int:
    return db.session.execute(select(func.max(AuditLog.id))).scalar() or 0


# ── wiring ────────────────────────────────────────────────────────────────────

def init_app(app) -> None:
    if not event.contains(db.session, "before_flush", _check_stale):
        event.listen(db.session, "before_flush", _check_stale)
        event.listen(db.session, "after_flush", _record)

    @app.errorhandler(StaleWrite)
    def _stale(e):
        db.session.rollback()
        return jsonify({"error": str(e), "stale": True, "changed_by": e.who, "changed_at": e.at}), 409

    @app.before_request
    def _allowed_people():
        allowed = app.config.get("ALLOWED_LOGINS") or []
        if not allowed or not app.config.get("TRUST_TAILSCALE_HEADERS") or request.path == "/healthz":
            return None
        if identity()["login"] not in allowed:
            return jsonify({"error": "This Tailscale account isn't allowed to open this app."}), 403
        return None

    @app.after_request
    def _stamp_revision(resp):
        if request.path.startswith("/api/"):
            try:
                resp.headers["X-Data-Rev"] = str(current_rev())
            except Exception:  # a failed request may leave the session unusable; the header is optional
                db.session.rollback()
        return resp
