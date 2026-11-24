"""The desktop app's parts that don't need a screen: settings, finding the server, what gets
installed, and the runner loop the tray hosts."""

import json
import threading

import pytest

import home_runner
from desktop import install
from desktop import settings as cfg


@pytest.fixture(autouse=True)
def own_data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "local"))
    monkeypatch.setenv("APPDATA", str(tmp_path / "roaming"))
    monkeypatch.setenv("FINANCE_APP_HOME", str(tmp_path / "app"))


def test_settings_start_from_defaults_and_keep_only_known_keys():
    assert cfg.load() == cfg.DEFAULTS
    saved = cfg.save({"server_url": "https://finance.example.ts.net", "nonsense": 1})
    assert saved["server_url"] == "https://finance.example.ts.net" and "nonsense" not in saved
    assert cfg.load()["server_url"] == "https://finance.example.ts.net"


def test_a_damaged_settings_file_falls_back_to_defaults():
    cfg.settings_file().parent.mkdir(parents=True)
    cfg.settings_file().write_text("{not json", encoding="utf-8")
    assert cfg.load() == cfg.DEFAULTS


def test_the_server_is_found_on_the_tailnet_by_its_name():
    status = {"Peer": {"a": {"DNSName": "logseq-sync.example-tailnet.ts.net."},
                       "b": {"DNSName": "finance.example-tailnet.ts.net."}}}
    assert cfg.server_from_tailscale(json.dumps(status)) == "https://finance.example-tailnet.ts.net"
    assert cfg.server_from_tailscale(json.dumps({"Peer": {"a": {"DNSName": "finance-old.x.ts.net."}}})) == ""
    assert cfg.server_from_tailscale("not json") == ""


def test_the_app_address_follows_the_mode():
    assert cfg.app_url({"mode": "local"}) == f"http://127.0.0.1:{cfg.LOCAL_PORT}"
    assert cfg.app_url({"mode": "server", "server_url": "https://finance.x.ts.net/"}) == "https://finance.x.ts.net"


def test_the_installed_copy_leaves_out_data_secrets_and_development_files(tmp_path):
    target = tmp_path / "app"
    target.mkdir()
    (target / ".venv").mkdir()                      # the installed environment survives an update
    (target / "old_module.py").write_text("x")      # files removed from the app don't linger
    install.copy_app(target)
    names = {p.name for p in target.iterdir()}
    assert {"app.py", "desktop", "static", "home_runner.py", "requirements.txt", ".venv"} <= names
    assert not names & {".git", ".claude", "instance", "tests", ".env", "skill-updates", "old_module.py"}
    assert not list(target.rglob("*.pyc"))


def test_shortcuts_point_at_the_installed_app():
    assert install.program().name == "Finance.exe" and install.program().is_relative_to(install.app_dir())
    assert install.menu_shortcut().name == "Personal Finance.lnk"
    assert cfg.startup_shortcut().parent.name == "Startup"


class FakeServer:
    base_url = "https://finance.example.ts.net"

    def __init__(self, jobs):
        self.jobs, self.results = list(jobs), []

    def post(self, path, payload, timeout):
        if path.endswith("/poll"):
            return {"job": self.jobs.pop(0) if self.jobs else None}
        self.results.append(payload)
        return {"accepted": True}


class FakeModel:
    model = vision_model = "m"

    def _chat(self, messages, task, schema=None, images=None):
        return "ok"


def test_the_runner_reports_its_status_and_stops_when_asked():
    stop, status = threading.Event(), {}
    server = FakeServer([{"id": "1", "task": "classify", "messages": [{"role": "user", "content": "x"}]}])
    t = threading.Thread(target=home_runner.serve, args=(server, FakeModel(), "desk"),
                         kwargs={"log": lambda m: None, "stop": stop, "status": status}, daemon=True)
    t.start()
    for _ in range(200):
        if status.get("jobs"):
            break
        threading.Event().wait(0.01)
    assert status["connected"] and status["jobs"] == 1 and server.results == [{"id": "1", "content": "ok"}]
    stop.set()
    t.join(2)
    assert not t.is_alive() and status["connected"] is False
