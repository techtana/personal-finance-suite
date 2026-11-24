"""Client for the app's local model (used by the importer; meant for any feature).

Standard library only and no imports from the rest of the app, so it can move
to a neutral place (a top-level llm.py) unchanged. Configured by the LLM_*
settings in config.py; get_client(app) builds one per use.

Two wire formats:
  ollama  native /api/chat. Output is constrained to a JSON schema by Ollama's
          grammar sampler, so a small model can't return malformed JSON or a
          category that isn't in the list. Supports photos.
  openai  /chat/completions on any OpenAI-compatible server (the agent stack's
          LiteLLM gateway, llama.cpp, LM Studio). Uses response_format
          json_schema when the server honours it; answers are parsed leniently.

Financial data is private: a base URL that isn't this machine is refused
unless LLM_ALLOW_REMOTE=1.

This class talks to one endpoint. get_client() returns a router over every
endpoint the owner has set up (ai/endpoints.py), with this same interface.
"""

from __future__ import annotations

import base64
import json
import re
import threading
import time
import urllib.error
import urllib.request
from collections import Counter
from urllib.parse import quote, urlparse

LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1", "0.0.0.0"}


class LLMError(Exception):
    pass


class LLMUnavailable(LLMError):
    pass


def extract_json(text: str):
    """Parse a JSON answer, tolerating code fences and chatter around it."""
    if text is None:
        raise LLMError("empty answer")
    s = text.strip()
    s = re.sub(r"^```(?:json)?\s*|\s*```$", "", s)
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        pass
    for opener, closer in (("{", "}"), ("[", "]")):
        start = s.find(opener)
        while start != -1:
            depth, in_str, esc = 0, False, False
            for i in range(start, len(s)):
                ch = s[i]
                if in_str:
                    if esc:
                        esc = False
                    elif ch == "\\":
                        esc = True
                    elif ch == '"':
                        in_str = False
                elif ch == '"':
                    in_str = True
                elif ch == opener:
                    depth += 1
                elif ch == closer:
                    depth -= 1
                    if depth == 0:
                        try:
                            return json.loads(s[start : i + 1])
                        except json.JSONDecodeError:
                            break
            start = s.find(opener, start + 1)
    raise LLMError(f"answer is not JSON: {s[:120]!r}")


_id_tokens: dict = {}
_id_token_lock = threading.Lock()


def google_id_token(audience: str) -> str:
    """An identity token for this machine's service account, from Google's metadata server.

    A private Cloud Run service accepts only callers it has been told to trust; this token
    is how the app's server proves which account it is. Works only on Google Cloud.
    """
    with _id_token_lock:
        hit = _id_tokens.get(audience)
        if hit and hit[0] > time.time():
            return hit[1]
    url = ("http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/identity"
           f"?audience={quote(audience, safe='')}")
    req = urllib.request.Request(url, headers={"Metadata-Flavor": "Google"})
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            token = resp.read().decode("utf-8").strip()
    except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
        raise LLMUnavailable(f"couldn't get a Google identity token (this only works on Google Cloud): "
                             f"{getattr(e, 'reason', e)}")
    with _id_token_lock:
        _id_tokens[audience] = (time.time() + 45 * 60, token)  # tokens last an hour
    return token


class LLMClient:
    """One client per import batch, so usage is counted per batch."""

    _status_cache: dict = {}
    _status_lock = threading.Lock()

    def __init__(self, provider="ollama", base_url="http://127.0.0.1:11434", model="qwen3.5:9b",
                 vision_model=None, api_key=None, num_ctx=32768, timeout=180, think=False,
                 allow_remote=False, auth=None, assume_up=False):
        self.provider = (provider or "off").lower()
        self.base_url = (base_url or "").rstrip("/")
        self.model = model
        self.vision_model = vision_model or model
        self.api_key = api_key or None
        self.num_ctx = num_ctx
        self.timeout = timeout
        self.think = think
        self.auth = auth              # "google-id-token": prove this server's identity to Cloud Run
        self.assume_up = assume_up    # a service that sleeps until called: don't wake it to ask if it's there
        self.calls = 0
        self.failures = 0
        self.seconds = 0.0
        self.tasks: Counter = Counter()
        self.blocked_reason = None
        if self.provider not in ("ollama", "openai"):
            self.blocked_reason = "The local AI is turned off (LLM_PROVIDER=off)."
        else:
            host = (urlparse(self.base_url).hostname or "").lower()
            if host not in LOCAL_HOSTS and not allow_remote:
                self.blocked_reason = (
                    f"LLM_BASE_URL points at {host or 'an unknown host'}, not this computer. Financial "
                    "data stays local unless LLM_ALLOW_REMOTE=1."
                )

    # ── status ────────────────────────────────────────────────────────────
    @property
    def enabled(self) -> bool:
        return self.blocked_reason is None

    def status(self, max_age: float = 15.0) -> dict:
        """{ok, model, vision_model, models, error}; cached briefly so the UI can poll it."""
        base = {"provider": self.provider, "base_url": self.base_url, "model": self.model,
                "vision_model": self.vision_model}
        if not self.enabled:
            return {**base, "ok": False, "error": self.blocked_reason, "models": []}
        if self.assume_up:
            return {**base, "ok": True, "error": None, "models": [], "asleep": True}
        key = (self.provider, self.base_url, self.model)
        with self._status_lock:
            hit = self._status_cache.get(key)
            if hit and time.time() - hit[0] < max_age:
                return hit[1]
        try:
            if self.provider == "ollama":
                data = self._request("GET", "/api/tags", None, timeout=4)
                models = [m.get("name") for m in data.get("models", [])]
            else:
                data = self._request("GET", "/models", None, timeout=4)
                models = [m.get("id") for m in data.get("data", [])]
            present = self.model in models or f"{self.model}:latest" in models
            result = {**base, "ok": present, "models": models,
                      "error": None if present else f"Model {self.model} isn't available on {self.base_url}."}
        except LLMError as e:
            result = {**base, "ok": False, "models": [], "error": f"Can't reach the local AI at {self.base_url}: {e}"}
        with self._status_lock:
            self._status_cache[key] = (time.time(), result)
        return result

    def usage(self) -> dict:
        return {"model": self.model, "calls": self.calls, "failures": self.failures,
                "seconds": round(self.seconds, 1), "tasks": dict(self.tasks)}

    # ── calls ─────────────────────────────────────────────────────────────
    def chat_json(self, messages: list[dict], schema: dict, task: str, images: list[bytes] | None = None):
        content = self._chat(messages, task, schema=schema, images=images)
        return extract_json(content)

    def chat_text(self, messages: list[dict], task: str, images: list[bytes] | None = None) -> str:
        return self._chat(messages, task, schema=None, images=images).strip()

    def _chat(self, messages, task, schema=None, images=None) -> str:
        if not self.enabled:
            raise LLMUnavailable(self.blocked_reason)
        model = self.vision_model if images else self.model
        started = time.time()
        self.calls += 1
        self.tasks[task] += 1
        try:
            if self.provider == "ollama":
                msgs = [dict(m) for m in messages]
                if images:
                    msgs[-1]["images"] = [base64.b64encode(b).decode() for b in images]
                payload = {"model": model, "messages": msgs, "stream": False, "think": self.think,
                           "options": {"temperature": 0, "num_ctx": self.num_ctx}}
                if schema is not None:
                    payload["format"] = schema
                data = self._request("POST", "/api/chat", payload, timeout=self.timeout)
                content = (data.get("message") or {}).get("content", "")
            else:
                msgs = [dict(m) for m in messages]
                if images:
                    parts = [{"type": "text", "text": msgs[-1]["content"]}]
                    parts += [{"type": "image_url", "image_url": {
                        "url": "data:image/jpeg;base64," + base64.b64encode(b).decode()}} for b in images]
                    msgs[-1]["content"] = parts
                payload = {"model": model, "messages": msgs, "temperature": 0}
                if schema is not None:
                    payload["response_format"] = {"type": "json_schema",
                                                  "json_schema": {"name": task, "schema": schema}}
                data = self._request("POST", "/chat/completions", payload, timeout=self.timeout)
                content = ((data.get("choices") or [{}])[0].get("message") or {}).get("content", "")
            if not content or not content.strip():
                raise LLMError("the model returned an empty answer")
            return content
        except LLMError:
            self.failures += 1
            raise
        finally:
            self.seconds += time.time() - started

    def _request(self, method, path, payload, timeout):
        headers = {"Content-Type": "application/json"}
        if self.auth == "google-id-token":
            origin = urlparse(self.base_url)
            headers["Authorization"] = "Bearer " + google_id_token(f"{origin.scheme}://{origin.netloc}")
        elif self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        body = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(self.base_url + path, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:300]
            raise LLMError(f"HTTP {e.code}: {detail}")
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
            raise LLMUnavailable(str(getattr(e, "reason", e)))
        except json.JSONDecodeError as e:
            raise LLMError(f"bad response: {e}")


def build_client(config) -> LLMClient:
    """A client from a mapping with the LLM_* keys (Flask's app.config)."""
    return LLMClient(
        provider=config.get("LLM_PROVIDER", "off"),
        base_url=config.get("LLM_BASE_URL", ""),
        model=config.get("LLM_MODEL", ""),
        vision_model=config.get("LLM_VISION_MODEL") or None,
        api_key=config.get("LLM_API_KEY") or None,
        num_ctx=config.get("LLM_NUM_CTX", 32768),
        timeout=config.get("LLM_TIMEOUT", 180),
        think=config.get("LLM_THINK", False),
        allow_remote=config.get("LLM_ALLOW_REMOTE", False),
    )


def get_client(app, mode: str = "realtime"):
    """A fresh client (so usage counts per job) that sends each request to the first endpoint able
    to take it. mode is "realtime" when a person is waiting and "batch" when the work can wait.

    Tests put a factory in app.extensions['llm_factory'].
    """
    factory = app.extensions.get("llm_factory")
    if factory:
        return factory()
    # The app registers the router over every endpoint (ai/endpoints.py); this module stays free of app imports.
    router = app.extensions.get("llm_router")
    return router(app.config, mode) if router else build_client(app.config)
