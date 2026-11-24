"""Where AI work runs: endpoint order, the home runner's queue, and what each page is told to show."""

import json
import threading
import time

import pytest

import home_runner
from ai import relay
from ai.endpoints import build_endpoints, routed_client
from app import create_app
from config import TestingConfig
from importer.llm import LLMError, LLMUnavailable
from models import ImportBatch, db
from tests.conftest import sample_bytes, upload


@pytest.fixture(autouse=True)
def clean_relay():
    relay.reset()
    yield
    relay.reset()


def make_app(tmp_path, **settings):
    cfg = type("Cfg", (TestingConfig,), {"IMPORT_STORAGE_DIR": str(tmp_path / "imports"), **settings})
    return create_app(cfg)


@pytest.fixture
def home_app(tmp_path):
    app = make_app(tmp_path, AI_HOME_RUNNER=True)
    with app.app_context():
        yield app
        db.session.remove()


class Runner(threading.Thread):
    """A stand-in for home_runner.py: answers every request with reply(job)."""

    def __init__(self, reply):
        super().__init__(daemon=True)
        self.reply, self.stop, self.jobs = reply, threading.Event(), []

    def run(self):
        while not self.stop.is_set():
            job = relay.poll({"name": "desk", "model": "home-model"}, wait=0.2)
            if job:
                self.jobs.append(job)
                try:
                    relay.complete(job["id"], content=self.reply(job))
                except LLMError as e:
                    relay.complete(job["id"], error=str(e), unavailable=isinstance(e, LLMUnavailable))

    def __enter__(self):
        self.start()
        deadline = time.time() + 2
        while not relay.online() and time.time() < deadline:
            time.sleep(0.01)
        return self

    def __exit__(self, *exc):
        self.stop.set()
        self.join(2)


def features(client):
    return {f["id"]: f for f in client.get("/api/capabilities").get_json()["features"]}


# ── the queue ─────────────────────────────────────────────────────────────────

def test_no_runner_means_not_available_straight_away():
    started = time.time()
    with pytest.raises(LLMUnavailable):
        relay.submit({"task": "x"}, timeout=30)
    assert time.time() - started < 1


def test_runner_collects_a_request_and_its_answer_comes_back():
    with Runner(lambda job: json.dumps({"echo": job["messages"][0]["content"]})) as runner:
        client = routed_client({"AI_HOME_RUNNER": True, "AI_RUNNER_TIMEOUT": 5}, "batch")
        answer = client.chat_json([{"role": "user", "content": "hi"}], {"type": "object"}, task="classify",
                                  images=[b"\xff\xd8photo"])
    assert answer == {"echo": "hi"}
    job = runner.jobs[0]
    assert job["task"] == "classify" and job["schema"] == {"type": "object"} and len(job["images"]) == 1
    assert client.usage()["calls"] == 1 and client.usage()["through"] == "Your home computer"
    assert client.model == "home-model"


def test_a_model_error_at_home_is_reported_not_retried_elsewhere():
    def boom(job):
        raise LLMError("the model returned nonsense")

    with Runner(boom):
        client = routed_client({"AI_HOME_RUNNER": True, "AI_RUNNER_TIMEOUT": 5}, "batch")
        with pytest.raises(LLMError) as err:
            client.chat_text([{"role": "user", "content": "hi"}], task="classify")
    assert not isinstance(err.value, LLMUnavailable)


def test_a_runner_that_goes_quiet_times_out():
    relay.poll({"name": "desk"}, wait=0)  # it was here a moment ago, then stopped asking
    with pytest.raises(LLMUnavailable, match="didn't answer in time"):
        relay.submit({"task": "x"}, timeout=0.2)
    assert relay.info()["waiting_jobs"] == 0


# ── which endpoint ────────────────────────────────────────────────────────────

LISTED = json.dumps([
    {"name": "api", "kind": "paid", "provider": "openai", "base_url": "https://api.example.com/v1", "model": "paid-1",
     "features": ["import"]},
    {"name": "gpu-job", "kind": "own-cloud", "provider": "ollama", "base_url": "https://ai-xyz.a.run.app",
     "model": "qwen", "use_for": ["batch"], "assume_up": True, "auth": "google-id-token"},
])


def test_your_own_machines_come_before_a_paid_service_whatever_the_listed_order():
    kinds = [e.kind for e in build_endpoints({"AI_HOME_RUNNER": True, "AI_ENDPOINTS": LISTED})]
    assert kinds == ["home", "own-cloud", "paid"]


def test_a_sleeping_service_is_batch_only_and_a_paid_one_serves_only_its_listed_features():
    cfg = {"AI_ENDPOINTS": LISTED}
    batch, realtime = routed_client(cfg, "batch"), routed_client(cfg, "realtime")
    status = batch.status()
    assert status["ok"] and status["through"] == "Your cloud AI service" and status["asleep"]
    assert not realtime.enabled                       # nothing may answer the assistant: not the sleeping
    assert realtime.status()["ok"] is False           # service (batch only), not the paid one (import only)
    with pytest.raises(LLMUnavailable):
        realtime.chat_text([{"role": "user", "content": "hi"}], task="assistant_answer")


def test_a_paid_service_with_no_features_listed_is_never_used():
    cfg = {"AI_ENDPOINTS": json.dumps([{"kind": "paid", "base_url": "https://api.example.com/v1", "model": "m"}])}
    assert not routed_client(cfg, "batch").enabled and not routed_client(cfg, "realtime").enabled


def test_the_single_endpoint_settings_still_work_and_keep_their_privacy_gate():
    local = routed_client({"LLM_PROVIDER": "ollama", "LLM_BASE_URL": "http://127.0.0.1:9", "LLM_MODEL": "m"})
    assert local.enabled and [e.kind for e in local.endpoints] == ["server"]
    remote = routed_client({"LLM_PROVIDER": "openai", "LLM_BASE_URL": "https://elsewhere.example", "LLM_MODEL": "m"})
    assert not remote.enabled and "LLM_ALLOW_REMOTE" in remote.blocked_reason


def test_bad_endpoint_json_turns_ai_off_with_a_reason():
    client = routed_client({"AI_ENDPOINTS": "{not json"})
    assert not client.enabled and "AI_ENDPOINTS" in client.blocked_reason


# ── what the pages are told ───────────────────────────────────────────────────

def test_with_nothing_set_up_every_ai_feature_is_hidden(client):
    f = features(client)
    assert not f["assistant"]["shown"] and not f["import_ai"]["shown"]
    assert f["assistant"]["reason"]
    assert client.get("/api/assistant/status").get_json()["ok"] is False


def test_home_computer_off_hides_realtime_but_batch_waits(home_app):
    client = home_app.test_client()
    f = features(client)
    assert f["assistant"]["shown"] is False
    assert f["import_ai"]["available"] is False and f["import_ai"]["waiting"] and f["import_ai"]["shown"]
    assert "home computer is on" in f["import_ai"]["note"]


def test_home_computer_on_makes_both_available(home_app):
    client = home_app.test_client()
    with Runner(lambda job: "{}"):
        f = features(client)
        caps = client.get("/api/capabilities").get_json()
    assert f["assistant"]["available"] and f["assistant"]["through"] == "Your home computer"
    assert f["import_ai"]["available"] and not f["import_ai"]["waiting"]
    assert caps["endpoints"][0]["state"] == "ready" and caps["home_runner"]["name"] == "desk"


# ── the runner's door ─────────────────────────────────────────────────────────

def test_runner_door_is_shut_unless_the_server_turns_it_on(client):
    assert client.post("/api/ai/runner/poll", json={"wait": 0}).status_code == 404


def test_runner_token_is_checked_when_one_is_set(tmp_path):
    app = make_app(tmp_path, AI_HOME_RUNNER=True, AI_RUNNER_TOKEN="s3cret")
    with app.app_context():
        client = app.test_client()
        assert client.post("/api/ai/runner/poll", json={"wait": 0}).status_code == 403
        ok = client.post("/api/ai/runner/poll", json={"wait": 0}, headers={"X-Runner-Token": "s3cret"})
        assert ok.status_code == 200 and ok.get_json() == {"job": None}
        db.session.remove()


def test_home_runner_script_serves_one_request_end_to_end(home_app):
    """home_runner.serve against the real endpoints, with a scripted local model."""
    http = home_app.test_client()

    class ViaTestClient:
        base_url = "http://test"

        def post(self, path, payload, timeout):
            return http.post(path, json={**payload, "wait": 2} if path.endswith("/poll") else payload).get_json()

    class LocalModel:
        model, vision_model = "desk-model", "desk-model"

        def _chat(self, messages, task, schema=None, images=None):
            return "Paris" if "capital" in messages[-1]["content"] else ""

    http.post("/api/ai/runner/poll", json={"wait": 0, "name": "desk", "model": "desk-model"})  # the runner says hello
    result = {}
    asker = threading.Thread(target=lambda: result.update(answer=routed_client(
        {"AI_HOME_RUNNER": True, "AI_RUNNER_TIMEOUT": 5}).chat_text(
        [{"role": "user", "content": "capital of France?"}], task="assistant_answer")))
    asker.start()
    logged = []
    home_runner.serve(ViaTestClient(), LocalModel(), "desk", once=True, log=logged.append)
    asker.join(5)
    assert result == {"answer": "Paris"}
    assert logged and logged[0].startswith("assistant_answer: done") and "Paris" not in logged[0]


# ── files that need the home computer ─────────────────────────────────────────

def test_a_photo_waits_for_the_home_computer_instead_of_failing(home_app, monkeypatch):
    client = home_app.test_client()
    batch = upload(client, "receipt-photo.jpg")
    assert batch["status"] == "waiting" and not batch.get("error")

    resumed = []
    monkeypatch.setattr("importer.worker.submit", lambda app, batch_id: resumed.append(batch_id))
    client.post("/api/ai/runner/poll", json={"wait": 0, "name": "desk"})   # the home computer connects
    assert resumed == [batch["id"]]
    assert db.session.get(ImportBatch, batch["id"]).status == "processing"


def test_without_a_home_computer_a_photo_still_fails_with_a_reason(client):
    batch = upload(client, "receipt-photo.jpg")
    assert batch["status"] == "failed" and batch["error"]


def test_a_text_file_does_not_wait_for_ai(home_app):
    batch = upload(home_app.test_client(), "checking-activity.csv")
    assert batch["status"] == "review"


def test_sample_photo_exists():
    assert sample_bytes("receipt-photo.jpg")[:2] == b"\xff\xd8"
