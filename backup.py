"""Restore points: full copies of the SQLite database kept in Google Cloud Storage.

Each backup is one object named ``finance_<UTC time>_<reason>.db``, for example
``finance_2026-11-22T14-30-05Z_before-clear.db``. The reason says why it was made:

  scheduled           regular backup made by the background scheduler
  manual              "Back up now" in Settings
  before-clear        made just before "Clear all data"
  before-restore      made just before restoring another restore point
  before-import       made just before a JSON import replaced the data

Google credentials are never stored by the app; the Google client library finds them
through Application Default Credentials (``gcloud auth application-default login``
or ``GOOGLE_APPLICATION_CREDENTIALS`` pointing at a service-account key).
"""

import logging
import os
import re
import shutil
import sqlite3
import tempfile
import threading
from datetime import datetime, timedelta, timezone

from flask import current_app

from models import db, Settings

log = logging.getLogger(__name__)

KINDS = {
    "scheduled": "Scheduled",
    "manual": "Manual",
    "before-clear": "Before clearing all data",
    "before-restore": "Before a restore",
    "before-import": "Before a JSON import",
}
FREQUENCIES = {"off": None, "daily": timedelta(days=1), "weekly": timedelta(weeks=1)}
NAME_RE = re.compile(r"^finance_(\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}Z)_([a-z-]+)\.db$")
_TIME_FMT = "%Y-%m-%dT%H-%M-%SZ"

# How often the background thread checks whether a scheduled backup is due.
CHECK_INTERVAL_SECONDS = 15 * 60

_lock = threading.Lock()
_status = {"last_scheduled_error": None, "last_scheduled_check": None}


class BackupError(Exception):
    """A backup or restore could not be completed; the message is shown to the user."""


# ── Configuration ─────────────────────────────────────────────────────────────

def default_config():
    return {
        "project": os.environ.get("GOOGLE_CLOUD_PROJECT", ""),
        "bucket": os.environ.get("GCS_BACKUP_BUCKET", ""),
        "prefix": os.environ.get("GCS_BACKUP_PREFIX", "finance-backups/"),
        "frequency": "daily",
        "keep": 14,
    }


def _settings_row():
    settings = Settings.query.first()
    if not settings:
        settings = Settings()
        db.session.add(settings)
        db.session.commit()
    return settings


def get_config():
    cfg = default_config()
    stored = _settings_row().backup_config or {}
    cfg.update({k: v for k, v in stored.items() if k in cfg and v not in (None, "")})
    return cfg


def update_config(data):
    cfg = get_config()
    for key in ("project", "bucket", "prefix"):
        if key in data:
            cfg[key] = (data[key] or "").strip()
    if cfg["prefix"] and not cfg["prefix"].endswith("/"):
        cfg["prefix"] += "/"
    if "frequency" in data:
        if data["frequency"] not in FREQUENCIES:
            raise BackupError("frequency must be one of: " + ", ".join(FREQUENCIES))
        cfg["frequency"] = data["frequency"]
    if "keep" in data:
        try:
            keep = int(data["keep"])
        except (TypeError, ValueError):
            raise BackupError("keep must be a whole number")
        if not 1 <= keep <= 365:
            raise BackupError("keep must be between 1 and 365")
        cfg["keep"] = keep

    settings = _settings_row()
    settings.backup_config = cfg
    db.session.commit()
    return cfg


# ── Storage targets ───────────────────────────────────────────────────────────

class GCSStore:
    def __init__(self, project, bucket, prefix):
        try:
            from google.cloud import storage
        except ImportError:
            raise BackupError("The google-cloud-storage package is not installed. Run: pip install -r requirements.txt")
        try:
            client = storage.Client(project=project or None)
        except Exception as e:
            raise BackupError(
                f"Could not sign in to Google Cloud ({e}). Run `gcloud auth application-default login`, "
                "or set GOOGLE_APPLICATION_CREDENTIALS to a service-account key file."
            )
        self.bucket = client.bucket(bucket)
        self.prefix = prefix
        self.description = f"gs://{bucket}/{prefix}"

    def list(self):
        try:
            blobs = list(self.bucket.list_blobs(prefix=self.prefix))
        except Exception as e:
            raise BackupError(f"Could not list backups in {self.description}: {e}")
        return [(b.name[len(self.prefix):], b.size or 0) for b in blobs]

    def upload(self, path, name):
        try:
            self.bucket.blob(self.prefix + name).upload_from_filename(path, content_type="application/vnd.sqlite3")
        except Exception as e:
            raise BackupError(f"Upload to {self.description} failed: {e}")

    def download(self, name, path):
        try:
            self.bucket.blob(self.prefix + name).download_to_filename(path)
        except Exception as e:
            raise BackupError(f"Download of {name} failed: {e}")

    def delete(self, name):
        try:
            self.bucket.blob(self.prefix + name).delete()
        except Exception as e:
            raise BackupError(f"Could not delete {name}: {e}")


class LocalStore:
    """Folder target used by tests (BACKUP_LOCAL_DIR); not offered in the UI."""

    def __init__(self, directory):
        os.makedirs(directory, exist_ok=True)
        self.directory = directory
        self.description = directory

    def list(self):
        return [(n, os.path.getsize(os.path.join(self.directory, n))) for n in os.listdir(self.directory)]

    def upload(self, path, name):
        shutil.copyfile(path, os.path.join(self.directory, name))

    def download(self, name, path):
        shutil.copyfile(os.path.join(self.directory, name), path)

    def delete(self, name):
        os.remove(os.path.join(self.directory, name))


def is_configured(cfg=None):
    cfg = cfg or get_config()
    return bool(current_app.config.get("BACKUP_LOCAL_DIR") or cfg["bucket"])


def get_store(cfg=None):
    cfg = cfg or get_config()
    local_dir = current_app.config.get("BACKUP_LOCAL_DIR")
    if local_dir:
        return LocalStore(local_dir)
    if not cfg["bucket"]:
        raise BackupError("No Google Cloud Storage bucket is set. Add one under Settings → Backups.")
    return GCSStore(cfg["project"], cfg["bucket"], cfg["prefix"])


# ── Listing ───────────────────────────────────────────────────────────────────

def _parse(name, size):
    m = NAME_RE.match(name)
    if not m or m.group(2) not in KINDS:
        return None
    created = datetime.strptime(m.group(1), _TIME_FMT).replace(tzinfo=timezone.utc)
    return {"name": name, "kind": m.group(2), "kind_label": KINDS[m.group(2)],
            "created_at": created.isoformat(), "size": size}


def list_backups(store=None):
    store = store or get_store()
    entries = [e for e in (_parse(n, s) for n, s in store.list()) if e]
    return sorted(entries, key=lambda e: e["created_at"], reverse=True)


def validate_name(name):
    if not NAME_RE.match(name or "") or _parse(name, 0) is None:
        raise BackupError("Not a backup file name")
    return name


# ── Snapshot and restore ──────────────────────────────────────────────────────

def _driver_connection(raw):
    return getattr(raw, "driver_connection", None) or raw.connection


def _snapshot_to(path):
    db.session.commit()
    raw = db.engine.raw_connection()
    try:
        dst = sqlite3.connect(path)
        try:
            _driver_connection(raw).backup(dst)
        finally:
            dst.close()
    finally:
        raw.close()


def create_backup(kind, store=None):
    """Upload a copy of the whole database and return its listing entry."""
    if kind not in KINDS:
        raise BackupError(f"unknown backup kind {kind}")
    store = store or get_store()
    name = f"finance_{datetime.now(timezone.utc).strftime(_TIME_FMT)}_{kind}.db"
    with _lock:
        tmp_dir = tempfile.mkdtemp(prefix="finance-backup-")
        try:
            path = os.path.join(tmp_dir, name)
            _snapshot_to(path)
            store.upload(path, name)
            return _parse(name, os.path.getsize(path))
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)


def backup_if_configured(kind):
    """Back up before a destructive action when backups are set up; None when they are not."""
    if not is_configured():
        return None
    return create_backup(kind)


def restore_backup(name):
    """Replace the whole database with a restore point, after backing up the current data."""
    validate_name(name)
    store = get_store()
    if name not in {e["name"] for e in list_backups(store)}:
        raise BackupError(f"Restore point {name} was not found")

    tmp_dir = tempfile.mkdtemp(prefix="finance-restore-")
    try:
        path = os.path.join(tmp_dir, name)
        store.download(name, path)
        _check_backup_file(path)
        safety = create_backup("before-restore", store)
        keep_cfg = get_config()

        with _lock:
            db.session.commit()
            db.session.remove()
            raw = db.engine.raw_connection()
            try:
                src = sqlite3.connect(path)
                try:
                    src.backup(_driver_connection(raw))
                finally:
                    src.close()
            finally:
                raw.close()

        # Older restore points may predate newer tables/columns.
        from app import _add_missing_columns
        db.create_all()
        _add_missing_columns()
        # Keep the current backup setup rather than the one stored in the restore point.
        _settings_row().backup_config = keep_cfg
        db.session.commit()
        return safety
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def _check_backup_file(path):
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise BackupError("The restore point is damaged")
            tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        finally:
            conn.close()
    except sqlite3.DatabaseError as e:
        raise BackupError(f"The restore point is not a readable database: {e}")
    if not {"settings", "accounts"} <= tables:
        raise BackupError("The restore point is not a Personal Finance Suite database")


def delete_backup(name):
    validate_name(name)
    if not can_delete():
        raise BackupError("This server can add backups but not delete them. Old scheduled backups are removed "
                          "by a rule on the bucket.")
    get_store().delete(name)


def verify_latest():
    """Restore drill: fetch the newest backup into a scratch file and check it opens. Changes nothing."""
    store = get_store()
    entries = list_backups(store)
    if not entries:
        raise BackupError(f"No backups found in {store.description}")
    newest = entries[0]
    tmp_dir = tempfile.mkdtemp(prefix="finance-verify-")
    try:
        path = os.path.join(tmp_dir, newest["name"])
        store.download(newest["name"], path)
        _check_backup_file(path)
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
            counts = {t: conn.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0] for t in tables}
        finally:
            conn.close()
        return {**newest, "tables": len(tables), "rows": sum(counts.values()),
                "counts": {t: n for t, n in counts.items() if n}}
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ── Clear all data ────────────────────────────────────────────────────────────

def clear_all_data():
    """Back up to the cloud, then delete every record. Nothing is deleted if the backup fails.

    The settings row (currency, locale, tax profile, backup setup) is kept.
    """
    backup = create_backup("before-clear")
    for table in reversed(db.metadata.sorted_tables):
        if table.name != Settings.__tablename__:
            db.session.execute(table.delete())
    db.session.commit()
    return backup


# ── Regular backups ───────────────────────────────────────────────────────────

def run_scheduled_backup(now=None):
    """Make a scheduled backup if one is due, then prune old scheduled ones. Returns the new entry or None."""
    now = now or datetime.now(timezone.utc)
    _status["last_scheduled_check"] = now.isoformat()
    cfg = get_config()
    interval = FREQUENCIES.get(cfg["frequency"])
    if interval is None or not is_configured(cfg):
        return None

    store = get_store(cfg)
    scheduled = [e for e in list_backups(store) if e["kind"] == "scheduled"]
    created = None
    if not scheduled or now - datetime.fromisoformat(scheduled[0]["created_at"]) >= interval:
        created = create_backup("scheduled", store)
        scheduled.insert(0, created)

    # Only scheduled backups are pruned; ones made before a clear/restore/import are kept.
    if can_delete():
        for old in scheduled[cfg["keep"]:]:
            store.delete(old["name"])
    return created


def can_delete():
    """False when a bucket rule expires old backups and the app has no right to delete any."""
    return current_app.config.get("BACKUP_PRUNE", "app") != "bucket"


def status():
    return dict(_status)


def start_scheduler(app):
    """Check for due backups in a background thread for as long as the app runs."""
    if app.config.get("TESTING"):
        return
    # With the debug reloader, only the child process that serves requests runs it.
    if app.debug and os.environ.get("WERKZEUG_RUN_MAIN") != "true":
        return

    stop = threading.Event()

    def loop():
        while not stop.wait(60 if _status["last_scheduled_check"] is None else CHECK_INTERVAL_SECONDS):
            with app.app_context():
                try:
                    made = run_scheduled_backup()
                    _status["last_scheduled_error"] = None
                    if made:
                        log.info("Scheduled backup saved: %s", made["name"])
                except Exception as e:
                    _status["last_scheduled_error"] = str(e)
                    log.warning("Scheduled backup failed: %s", e)
                finally:
                    db.session.remove()

    threading.Thread(target=loop, name="backup-scheduler", daemon=True).start()


# ── Command line ──────────────────────────────────────────────────────────────

import click  # noqa: E402
from flask.cli import AppGroup  # noqa: E402

backups_cli = AppGroup("backups", help="Cloud backups: make one now, or check that the newest one restores.")


@backups_cli.command("now")
def backup_now_cmd():
    """Make a backup right now."""
    try:
        entry = create_backup("manual")
    except BackupError as e:
        raise click.ClickException(str(e))
    click.echo(f"saved {entry['name']} ({entry['size']} bytes)")


@backups_cli.command("verify")
def backup_verify_cmd():
    """Restore drill: download the newest backup and check that it opens. Changes nothing."""
    try:
        result = verify_latest()
    except BackupError as e:
        raise click.ClickException(str(e))
    click.echo(f"ok: {result['name']} from {result['created_at']} opens cleanly "
               f"({result['tables']} tables, {result['rows']} rows)")
