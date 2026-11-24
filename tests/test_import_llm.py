"""The model client: wire format, privacy guard, lenient JSON parsing."""

import json

import pytest

from importer.llm import LLMClient, LLMError, LLMUnavailable, extract_json


class _Resp:
    def __init__(self, body):
        self.body = json.dumps(body).encode()

    def read(self):
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@pytest.fixture
def captured(monkeypatch):
    seen = {}

    def fake_urlopen(req, timeout=None):
        seen["url"] = req.full_url
        seen["headers"] = dict(req.headers)
        seen["body"] = json.loads(req.data.decode()) if req.data else None
        if req.full_url.endswith("/api/chat"):
            return _Resp({"message": {"content": '{"ok": true}'}})
        if req.full_url.endswith("/chat/completions"):
            return _Resp({"choices": [{"message": {"content": '```json\n{"ok": true}\n```'}}]})
        return _Resp({"models": [{"name": "qwen3.5:9b"}]})

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    return seen


def test_ollama_request_is_schema_constrained_and_matches_stack_context(captured):
    llm = LLMClient(provider="ollama", base_url="http://127.0.0.1:11434", model="qwen3.5:9b", num_ctx=32768)
    out = llm.chat_json([{"role": "user", "content": "hi"}], {"type": "object"}, "t", images=[b"\xff\xd8jpg"])
    body = captured["body"]
    assert out == {"ok": True}
    assert body["format"] == {"type": "object"} and body["think"] is False and body["stream"] is False
    assert body["options"] == {"temperature": 0, "num_ctx": 32768}
    assert body["messages"][-1]["images"] == ["/9hqcGc="]
    assert llm.usage()["calls"] == 1 and llm.usage()["tasks"] == {"t": 1}


def test_openai_compatible_request(captured):
    llm = LLMClient(provider="openai", base_url="http://localhost:4000/v1", model="local-small", api_key="sk-test")
    out = llm.chat_json([{"role": "user", "content": "hi"}], {"type": "object"}, "task", images=[b"img"])
    body = captured["body"]
    assert out == {"ok": True}
    assert captured["url"] == "http://localhost:4000/v1/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer sk-test"
    assert body["response_format"]["json_schema"]["schema"] == {"type": "object"}
    assert body["messages"][-1]["content"][1]["image_url"]["url"].startswith("data:image/jpeg;base64,")


def test_remote_hosts_are_refused_unless_allowed(captured):
    llm = LLMClient(provider="ollama", base_url="http://gpu-box.example.com:11434")
    assert not llm.enabled and "stays local unless LLM_ALLOW_REMOTE=1" in llm.blocked_reason
    with pytest.raises(LLMUnavailable):
        llm.chat_text([{"role": "user", "content": "x"}], "t")
    assert "url" not in captured  # nothing was sent
    assert LLMClient(provider="ollama", base_url="http://gpu-box.example.com:11434", allow_remote=True).enabled


def test_provider_off():
    llm = LLMClient(provider="off")
    assert not llm.enabled and llm.status()["ok"] is False


def test_status_reports_missing_model(captured):
    LLMClient._status_cache.clear()
    s = LLMClient(provider="ollama", base_url="http://127.0.0.1:11434", model="other:7b").status()
    assert s["ok"] is False and "isn't available" in s["error"]


@pytest.mark.parametrize("text,expected", [
    ('{"a": 1}', {"a": 1}), ('```json\n{"a": 1}\n```', {"a": 1}), ('Sure! {"a": {"b": "}"}} done', {"a": {"b": "}"}}),
    ("[1, 2]", [1, 2]),
])
def test_extract_json(text, expected):
    assert extract_json(text) == expected


def test_extract_json_rejects_prose():
    with pytest.raises(LLMError):
        extract_json("I can't read this receipt.")


def test_generic_llm_settings_win_over_the_importer_names(monkeypatch):
    from config import _llm_env

    monkeypatch.setenv("IMPORT_LLM_MODEL", "old:7b")
    assert _llm_env("MODEL", "default") == "old:7b"
    monkeypatch.setenv("LLM_MODEL", "new:9b")
    assert _llm_env("MODEL", "default") == "new:9b"
    monkeypatch.delenv("LLM_MODEL")
    monkeypatch.delenv("IMPORT_LLM_MODEL")
    assert _llm_env("MODEL", "default") == "default"


def test_client_module_has_no_app_imports():
    import ast
    import importer.llm as mod

    tree = ast.parse(open(mod.__file__, encoding="utf-8").read())
    names = {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    names |= {n.module.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
    assert names <= {"__future__", "base64", "json", "re", "threading", "time", "urllib", "collections"}, names
