"""Tests for restore points, clear-all-data and scheduled backups.

A local folder (BACKUP_LOCAL_DIR) stands in for the Google Cloud Storage bucket.
"""

import os
from datetime import datetime, timedelta, timezone

import pytest

import backup
from backup import NAME_RE


@pytest.fixture
def app(tmp_path):
    from app import create_app
    from config import TestingConfig
    from models import db

    class Cfg(TestingConfig):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{tmp_path / 'finance.db'}"
        BACKUP_LOCAL_DIR = str(tmp_path / "bucket")

    app = create_app(Cfg)
    with app.app_context():
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


def add_account(client, name="Checking"):
    r = client.post("/api/accounts", json={"name": name, "type": "checking", "institution": "Bank",
                                           "current_balance": 100_000, "last_updated_date": "2026-11-01"})
    assert r.status_code == 201, r.get_json()


def account_names(client):
    return sorted(a["name"] for a in client.get("/api/accounts").get_json())


def test_names_say_when_and_why():
    entry = backup._parse("finance_2026-11-22T14-30-05Z_before-clear.db", 10)
    assert entry["kind"] == "before-clear"
    assert entry["created_at"] == "2026-11-22T14:30:05+00:00"
    assert backup._parse("finance_2026-11-22T14-30-05Z_whatever.db", 1) is None
    with pytest.raises(backup.BackupError):
        backup.validate_name("../../finance.db")


def test_clear_backs_up_first_and_keeps_settings(client):
    add_account(client)
    client.patch("/api/settings", json={"currency": "THB"})

    r = client.post("/api/data/clear")
    assert r.status_code == 200
    name = r.get_json()["backup"]["name"]
    assert NAME_RE.match(name) and name.endswith("_before-clear.db")
    assert account_names(client) == []
    assert client.get("/api/settings").get_json()["currency"] == "THB"

    # The backup really holds the data that was cleared.
    assert client.post(f"/api/backups/{name}/restore").status_code == 200
    assert account_names(client) == ["Checking"]


def test_clear_deletes_nothing_when_backup_fails(app, client, monkeypatch):
    add_account(client)

    def fail(*a, **k):
        raise backup.BackupError("bucket unreachable")

    monkeypatch.setattr(backup.LocalStore, "upload", fail)
    r = client.post("/api/data/clear")
    assert r.status_code == 502
    assert "Nothing was deleted" in r.get_json()["error"]
    assert account_names(client) == ["Checking"]


def test_clear_refused_without_a_bucket(app, client):
    app.config["BACKUP_LOCAL_DIR"] = None
    add_account(client)
    r = client.post("/api/data/clear")
    assert r.status_code == 502 and "bucket" in r.get_json()["error"]
    assert account_names(client) == ["Checking"]


def test_restore_makes_a_safety_backup_and_keeps_backup_setup(client):
    add_account(client, "Old")
    name = client.post("/api/backups").get_json()["name"]
    add_account(client, "New")
    client.patch("/api/backups/config", json={"frequency": "weekly", "keep": 5})

    r = client.post(f"/api/backups/{name}/restore")
    assert r.status_code == 200
    assert account_names(client) == ["Old"]
    cfg = client.get("/api/backups").get_json()["config"]
    assert (cfg["frequency"], cfg["keep"]) == ("weekly", 5)

    kinds = [b["kind"] for b in client.get("/api/backups").get_json()["backups"]]
    assert sorted(kinds) == ["before-restore", "manual"]


def test_restore_rejects_unknown_and_bad_files(app, client):
    assert client.post("/api/backups/finance_2026-01-01T00-00-00Z_manual.db/restore").status_code == 502
    bad = "finance_2026-01-01T00-00-00Z_manual.db"
    with open(os.path.join(app.config["BACKUP_LOCAL_DIR"], bad), "w") as f:
        f.write("not a database")
    r = client.post(f"/api/backups/{bad}/restore")
    assert r.status_code == 502


def test_scheduled_backups_run_when_due_and_prune_old_ones(app, client):
    client.patch("/api/backups/config", json={"frequency": "daily", "keep": 2})
    store = backup.get_store()
    # Pretend three old scheduled backups and one made before a clear exist.
    for ts, kind in [("2026-11-01T00-00-00Z", "scheduled"), ("2026-11-02T00-00-00Z", "scheduled"),
                     ("2026-11-03T00-00-00Z", "scheduled"), ("2026-10-01T00-00-00Z", "before-clear")]:
        open(os.path.join(store.directory, f"finance_{ts}_{kind}.db"), "w").close()

    made = backup.run_scheduled_backup()
    assert made and made["kind"] == "scheduled"
    names = [b["name"] for b in backup.list_backups()]
    assert [n for n in names if "scheduled" in n] == [made["name"], "finance_2026-11-03T00-00-00Z_scheduled.db"]
    assert "finance_2026-10-01T00-00-00Z_before-clear.db" in names

    # Not due again until a day has passed.
    assert backup.run_scheduled_backup() is None
    later = datetime.now(timezone.utc) + timedelta(days=1, minutes=1)
    assert backup.run_scheduled_backup(now=later) is not None


def test_scheduled_backups_off(client):
    client.patch("/api/backups/config", json={"frequency": "off"})
    assert backup.run_scheduled_backup() is None


def test_config_validation(client):
    assert client.patch("/api/backups/config", json={"frequency": "hourly"}).status_code == 422
    assert client.patch("/api/backups/config", json={"keep": 0}).status_code == 422
    cfg = client.patch("/api/backups/config", json={"bucket": " my-bucket ", "prefix": "pfs"}).get_json()
    assert (cfg["bucket"], cfg["prefix"]) == ("my-bucket", "pfs/")


def test_import_backs_up_first(client):
    client.post("/api/import", json={"categories": []})
    kinds = [b["kind"] for b in client.get("/api/backups").get_json()["backups"]]
    assert kinds == ["before-import"]


def test_sample_data_endpoint_is_gone(client):
    assert client.post("/api/seed").status_code in (404, 405)


def test_delete_backup(client):
    name = client.post("/api/backups").get_json()["name"]
    assert client.delete(f"/api/backups/{name}").status_code == 204
    assert client.get("/api/backups").get_json()["backups"] == []
