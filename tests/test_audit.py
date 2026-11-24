"""Who changed what, the stale-save check, and identity from Tailscale Serve."""

import pytest

from app import create_app
from config import TestingConfig
from models import AuditLog, Rule, db

RULE = {"name": "Gym", "rule_type": "expense", "amount": 12000, "frequency": "monthly", "start_date": "2026-01-01"}


def make_rule(client, **headers):
    res = client.post("/api/rules", json=RULE, headers=headers)
    assert res.status_code == 201, res.get_json()
    return res.get_json()["id"]


def rev(client):
    return client.get("/api/rules").headers["X-Data-Rev"]


def test_every_change_is_logged_without_values(client):
    rule_id = make_rule(client)
    assert client.patch(f"/api/rules/{rule_id}", json={"amount": 15000, "name": "Gym plus"}).status_code == 200
    assert client.delete(f"/api/rules/{rule_id}").status_code == 204

    entries = client.get("/api/activity").get_json()["entries"]
    assert [e["action"] for e in entries] == ["delete", "update", "create"]  # newest first
    update = entries[1]
    assert update["kind"] == "Recurring entry" and update["who"] == "local"
    assert update["fields"] == ["amount", "name"]
    assert "15000" not in str(entries)  # field names only, never the amounts


def test_saving_without_a_real_change_logs_nothing(client):
    rule_id = make_rule(client)
    client.patch(f"/api/rules/{rule_id}", json={"amount": 12000})
    assert AuditLog.query.filter_by(action="update").count() == 0


def test_api_answers_carry_the_data_revision(client):
    assert rev(client) == "0"
    make_rule(client)
    assert rev(client) == "1"
    assert "X-Data-Rev" not in client.get("/healthz").headers


def test_a_save_on_top_of_someone_elses_change_is_refused(client):
    rule_id = make_rule(client)
    phone_read = rev(client)                                    # the phone loads the list
    laptop = {"X-Client-Id": "laptop", "X-Base-Rev": rev(client)}
    assert client.patch(f"/api/rules/{rule_id}", json={"amount": 20000}, headers=laptop).status_code == 200

    phone = {"X-Client-Id": "phone", "X-Base-Rev": phone_read}  # the phone still shows the old amount
    res = client.patch(f"/api/rules/{rule_id}", json={"name": "Climbing gym"}, headers=phone)
    assert res.status_code == 409
    body = res.get_json()
    assert body["stale"] is True and "Reload" in body["error"]
    rule = db.session.get(Rule, rule_id)
    assert (rule.name, rule.amount) == ("Gym", 20000)           # the laptop's edit survived, the phone's did not land

    assert client.delete(f"/api/rules/{rule_id}", headers=phone).status_code == 409
    phone["X-Base-Rev"] = rev(client)                           # after a reload it goes through
    assert client.patch(f"/api/rules/{rule_id}", json={"name": "Climbing gym"}, headers=phone).status_code == 200


def test_your_own_earlier_change_is_not_a_conflict(client):
    rule_id = make_rule(client)
    me = {"X-Client-Id": "me", "X-Base-Rev": rev(client)}
    assert client.patch(f"/api/rules/{rule_id}", json={"amount": 1}, headers=me).status_code == 200
    assert client.patch(f"/api/rules/{rule_id}", json={"amount": 2}, headers=me).status_code == 200


def test_a_change_to_a_different_record_is_not_a_conflict(client):
    a, b = make_rule(client), make_rule(client)
    phone = {"X-Client-Id": "phone", "X-Base-Rev": rev(client)}
    client.patch(f"/api/rules/{a}", json={"amount": 1}, headers={"X-Client-Id": "laptop"})
    assert client.patch(f"/api/rules/{b}", json={"amount": 2}, headers=phone).status_code == 200


def test_callers_that_do_not_say_what_they_read_are_not_checked(client):
    rule_id = make_rule(client)
    client.patch(f"/api/rules/{rule_id}", json={"amount": 1}, headers={"X-Client-Id": "laptop"})
    assert client.patch(f"/api/rules/{rule_id}", json={"amount": 2}).status_code == 200


# ── identity ──────────────────────────────────────────────────────────────────

@pytest.fixture
def tailnet_app(tmp_path):
    class Cfg(TestingConfig):
        IMPORT_STORAGE_DIR = str(tmp_path / "imports")
        TRUST_TAILSCALE_HEADERS = True
        ALLOWED_LOGINS = ["owner@example.com"]

    app = create_app(Cfg)
    with app.app_context():
        yield app
        db.session.remove()


def test_tailscale_header_is_ignored_unless_trusted(client):
    spoof = {"Tailscale-User-Login": "someone@example.com"}
    assert client.get("/api/whoami", headers=spoof).get_json() == {
        "login": "local", "name": "This computer", "trusted": False}
    make_rule(client, **spoof)
    assert AuditLog.query.one().who == "local"


def test_behind_serve_changes_are_recorded_under_the_tailscale_login(tailnet_app):
    client = tailnet_app.test_client()
    owner = {"Tailscale-User-Login": "Owner@Example.com", "Tailscale-User-Name": "The Owner"}
    assert client.get("/api/whoami", headers=owner).get_json() == {
        "login": "owner@example.com", "name": "The Owner", "trusted": True}
    make_rule(client, **owner)
    assert AuditLog.query.one().who == "owner@example.com"


def test_only_listed_people_get_in_and_the_health_check_stays_open(tailnet_app):
    client = tailnet_app.test_client()
    assert client.get("/api/rules", headers={"Tailscale-User-Login": "guest@example.com"}).status_code == 403
    assert client.get("/overview", headers={"Tailscale-User-Login": "guest@example.com"}).status_code == 403
    assert client.get("/api/rules").status_code == 403           # a tagged machine has no login at all
    assert client.get("/healthz").get_json() == {"ok": True}


def test_the_import_workers_progress_is_not_activity(client, accounts):
    from tests.conftest import upload
    upload(client, "checking-activity.csv")
    kinds = [(e["who"], e["action"]) for e in client.get("/api/activity").get_json()["entries"]
             if e["kind"] == "Imported file"]
    # The upload itself (create, then the stored file's path); none of the reading progress.
    assert kinds[-1] == ("local", "create") and len(kinds) <= 2 and all(who == "local" for who, _ in kinds)
