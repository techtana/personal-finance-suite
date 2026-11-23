import io
import os
from collections import Counter

import pytest

from app import create_app
from config import TestingConfig
from importer.llm import LLMUnavailable
from models import Account, db

SAMPLES = os.path.join(os.path.dirname(__file__), "..", "docs", "sample-data", "imports")


def sample_bytes(name: str) -> bytes:
    with open(os.path.join(SAMPLES, name), "rb") as f:
        return f.read()


@pytest.fixture
def app(tmp_path):
    class Cfg(TestingConfig):
        IMPORT_STORAGE_DIR = str(tmp_path / "imports")

    app = create_app(Cfg)
    with app.app_context():
        yield app
        db.session.remove()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def accounts(app):
    accts = {
        "chk": Account(name="Everyday Checking", type="checking", institution="Example Bank", current_balance=400000,
                       note="ending 1234", last_updated_date="2026-11-01"),
        "sav": Account(name="High Yield Savings", type="savings", institution="Example Savings Bank",
                       current_balance=1800000, note="…5678", last_updated_date="2026-11-01"),
        "card": Account(name="Rewards Visa 4821", type="credit_card", institution="Example Card Co", current_balance=0,
                        last_updated_date="2026-11-01"),
        "k401": Account(name="401k", type="retirement_401k", institution="Employer", current_balance=4500000,
                        last_updated_date="2026-11-01"),
    }
    for a in accts.values():
        db.session.add(a)
    db.session.commit()
    return accts


class FakeLLM:
    """Scripted stand-in for the local model. answers: task -> list of replies or a callable(messages, images)."""

    provider, model, vision_model, base_url = "fake", "fake-model", "fake-model", "http://127.0.0.1:0"
    blocked_reason = None
    enabled = True

    def __init__(self, answers=None, ok=True):
        self.answers = answers or {}
        self.ok = ok
        self.calls = 0
        self.tasks = Counter()
        self.seen = []

    def status(self, max_age=15.0):
        return {"ok": self.ok, "model": self.model, "base_url": self.base_url, "provider": "fake",
                "error": None if self.ok else "fake offline"}

    def _next(self, task, messages, images):
        self.calls += 1
        self.tasks[task] += 1
        self.seen.append((task, messages, images))
        ans = self.answers.get(task)
        if ans is None:
            raise LLMUnavailable(f"no scripted answer for {task}")
        if callable(ans):
            return ans(messages, images)
        if isinstance(ans, list):
            if not ans:
                raise LLMUnavailable(f"scripted answers for {task} ran out")
            return ans.pop(0) if len(ans) > 1 else ans[0]
        return ans

    def chat_json(self, messages, schema, task, images=None):
        return self._next(task, messages, images)

    def chat_text(self, messages, task, images=None):
        return self._next(task, messages, images)

    def usage(self):
        return {"model": self.model, "calls": self.calls, "failures": 0, "seconds": 0.0, "tasks": dict(self.tasks)}


@pytest.fixture
def fake_llm(app):
    def install(answers=None, ok=True):
        fake = FakeLLM(answers, ok)
        app.extensions["llm_factory"] = lambda: fake
        return fake

    yield install
    app.extensions.pop("llm_factory", None)


def upload(client, name, data=None, **form):
    data = sample_bytes(name) if data is None else data
    payload = {"files": (io.BytesIO(data), name), **{k: v for k, v in form.items() if v is not None}}
    res = client.post("/api/imports", data=payload, content_type="multipart/form-data")
    body = res.get_json()
    assert res.status_code == 202, body
    batch_id = body["imports"][0]["id"]
    return client.get(f"/api/imports/{batch_id}").get_json()
