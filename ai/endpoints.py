"""The places AI work can run, and a client that picks one per request.

Order of preference, so private hardware is always tried first:

  home       a computer at home that pulls work from this app (ai/relay.py)
  server     a model on the same machine as the app
  own-cloud  a model on a machine you rent: a full-time VM, or Cloud Run that sleeps
  paid       someone else's API. Used only for the features it lists (opt-in per feature)

Each endpoint says what it is good for: "realtime" (a person is waiting: Ask, filter,
explain, draft) and/or "batch" (reading imported files; a wait is fine). A service that
sleeps until called should be batch only.

RoutedClient has the same interface as importer.llm.LLMClient, so the importer and the
assistant don't know or care where the model is.
"""

from __future__ import annotations

import base64
import json
import os
import time
from collections import Counter
from dataclasses import dataclass, field

from ai import relay
from importer.llm import LLMClient, LLMError, LLMUnavailable, extract_json

MODES = ("realtime", "batch")
FEATURES = ("assistant", "import")
KIND_ORDER = {"home": 0, "server": 1, "own-cloud": 2, "paid": 3}
KIND_LABELS = {"home": "Your home computer", "server": "This server", "own-cloud": "Your cloud AI service",
               "paid": "A paid AI service"}


def feature_of(task: str) -> str:
    return "assistant" if str(task).startswith("assistant") else "import"


class RelayClient:
    """Looks like an LLMClient; the work is done by the home runner."""

    provider, base_url, blocked_reason, enabled = "home", "home computer", None, True

    def __init__(self, timeout: float = 300):
        self.timeout = timeout
        self.calls = self.failures = 0
        self.seconds = 0.0
        self.tasks: Counter = Counter()

    @property
    def model(self) -> str:
        return relay.info()["model"] or "home model"

    @property
    def vision_model(self) -> str:
        return relay.info()["vision_model"] or self.model

    def status(self, max_age: float = 15.0) -> dict:
        ok = relay.online()
        return {"provider": self.provider, "base_url": self.base_url, "model": self.model,
                "vision_model": self.vision_model, "ok": ok, "models": [],
                "error": None if ok else "The home computer isn't connected right now."}

    def usage(self) -> dict:
        return {"model": self.model, "calls": self.calls, "failures": self.failures,
                "seconds": round(self.seconds, 1), "tasks": dict(self.tasks)}

    def chat_json(self, messages, schema, task, images=None):
        return extract_json(self._send(messages, schema, task, images))

    def chat_text(self, messages, task, images=None) -> str:
        return self._send(messages, None, task, images).strip()

    def _send(self, messages, schema, task, images) -> str:
        started = time.time()
        self.calls += 1
        self.tasks[task] += 1
        payload = {"task": task, "messages": messages, "schema": schema,
                   "images": [base64.b64encode(b).decode() for b in (images or [])]}
        try:
            content = relay.submit(payload, self.timeout)
            if not content.strip():
                raise LLMError("the model returned an empty answer")
            return content
        except LLMError:
            self.failures += 1
            raise
        finally:
            self.seconds += time.time() - started


@dataclass
class Endpoint:
    name: str
    kind: str
    client: object
    use_for: frozenset = frozenset(MODES)
    features: frozenset = frozenset(FEATURES)
    assume_up: bool = False
    problem: str | None = None  # why this entry can't be used at all (bad settings)

    def serves(self, mode: str, feature: str) -> bool:
        return self.problem is None and self.client.enabled and mode in self.use_for and feature in self.features

    def state(self) -> dict:
        """{state: ready | asleep | offline | off, error}"""
        if self.problem:
            return {"state": "off", "error": self.problem}
        if not self.client.enabled:
            return {"state": "off", "error": self.client.blocked_reason}
        if self.assume_up:
            return {"state": "asleep", "error": None}
        s = self.client.status()
        return {"state": "ready" if s.get("ok") else "offline", "error": s.get("error")}

    def up(self) -> bool:
        return self.state()["state"] in ("ready", "asleep")


def _legacy_endpoint(config) -> Endpoint | None:
    """The single endpoint described by LLM_PROVIDER / LLM_BASE_URL / LLM_MODEL."""
    if (config.get("LLM_PROVIDER") or "off").lower() not in ("ollama", "openai"):
        return None
    from importer.llm import LOCAL_HOSTS, build_client
    from urllib.parse import urlparse

    client = build_client(config)
    host = (urlparse(client.base_url).hostname or "").lower()
    kind = "server" if host in LOCAL_HOSTS else "own-cloud"
    return Endpoint(name="default", kind=kind, client=client)


def _listed_endpoint(raw: dict, config) -> Endpoint:
    name = str(raw.get("name") or raw.get("kind") or "endpoint")
    kind = raw.get("kind") if raw.get("kind") in ("server", "own-cloud", "paid") else "own-cloud"
    use_for = frozenset(m for m in (raw.get("use_for") or MODES) if m in MODES) or frozenset(MODES)
    # Your own machines serve everything unless narrowed. A paid service serves nothing unless listed.
    listed = [f for f in (raw.get("features") or []) if f in FEATURES]
    features = frozenset(listed) if (listed or kind == "paid") else frozenset(FEATURES)
    api_key = raw.get("api_key") or (os.environ.get(raw["api_key_env"], "") if raw.get("api_key_env") else "")
    client = LLMClient(
        provider=raw.get("provider", "openai"), base_url=raw.get("base_url", ""), model=raw.get("model", ""),
        vision_model=raw.get("vision_model") or None, api_key=api_key or None,
        num_ctx=int(raw.get("num_ctx") or config.get("LLM_NUM_CTX", 32768)),
        timeout=int(raw.get("timeout") or config.get("LLM_TIMEOUT", 180)),
        think=bool(raw.get("think", False)),
        allow_remote=True,  # listing an endpoint here is the owner's explicit choice to use it
        auth=raw.get("auth") or None, assume_up=bool(raw.get("assume_up", False)),
    )
    problem = None
    if kind == "paid" and not features:
        problem = "No features are listed for this paid service, so it is never used."
    elif not raw.get("base_url") or not raw.get("model"):
        problem = "base_url and model are required."
    return Endpoint(name=name, kind=kind, client=client, use_for=use_for, features=features,
                    assume_up=bool(raw.get("assume_up", False)), problem=problem)


def build_endpoints(config) -> list[Endpoint]:
    endpoints: list[Endpoint] = []
    if config.get("AI_HOME_RUNNER"):
        endpoints.append(Endpoint(name="home", kind="home",
                                  client=RelayClient(timeout=config.get("AI_RUNNER_TIMEOUT", 300))))
    listed = (config.get("AI_ENDPOINTS") or "").strip()
    if listed:
        try:
            items = json.loads(listed)
            if not isinstance(items, list):
                raise ValueError("expected a JSON list")
        except ValueError as e:
            endpoints.append(Endpoint(name="AI_ENDPOINTS", kind="own-cloud", client=LLMClient(provider="off"),
                                      problem=f"AI_ENDPOINTS isn't valid JSON: {e}"))
        else:
            endpoints += [_listed_endpoint(raw, config) for raw in items if isinstance(raw, dict)]
    else:
        legacy = _legacy_endpoint(config)
        if legacy:
            endpoints.append(legacy)
    # Stable sort: private hardware first, paid last, the owner's order within a kind.
    return sorted(endpoints, key=lambda e: KIND_ORDER.get(e.kind, 9))


class RoutedClient:
    """One per job. Sends each request to the first endpoint that can take it."""

    def __init__(self, endpoints: list[Endpoint], mode: str = "realtime", feature: str | None = None):
        self.endpoints = endpoints
        self.mode = mode if mode in MODES else "realtime"
        self.feature = feature or ("assistant" if self.mode == "realtime" else "import")
        self.last_used: Endpoint | None = None

    # ── which endpoint ────────────────────────────────────────────────────
    def _candidates(self, feature: str | None = None) -> list[Endpoint]:
        return [e for e in self.endpoints if e.serves(self.mode, feature or self.feature)]

    def _current(self) -> Endpoint | None:
        cands = self._candidates()
        for e in cands:
            if e.up():
                return e
        return cands[0] if cands else None

    @property
    def enabled(self) -> bool:
        return bool(self._candidates())

    @property
    def blocked_reason(self) -> str | None:
        if self._candidates():
            return None
        problems = [e.state()["error"] for e in self.endpoints if e.state()["error"]]
        if problems:
            return problems[0]
        if self.endpoints:
            return f"No AI endpoint is set up for {self.mode} work."
        return "The AI is turned off (no endpoint is set up)."

    def _attr(self, name: str, default: str = "") -> str:
        e = self.last_used or self._current()
        return getattr(e.client, name, default) if e else default

    provider = property(lambda self: self._attr("provider", "off"))
    model = property(lambda self: self._attr("model"))
    vision_model = property(lambda self: self._attr("vision_model"))
    base_url = property(lambda self: self._attr("base_url"))

    # ── status ────────────────────────────────────────────────────────────
    def status(self, max_age: float = 15.0) -> dict:
        cands = self._candidates()
        base = {"provider": "off", "base_url": "", "model": "", "vision_model": "", "ok": False,
                "waiting": False, "through": None, "endpoint": None, "kind": None, "models": []}
        if not cands:
            return {**base, "error": self.blocked_reason}
        errors = []
        for e in cands:
            st = e.state()
            if st["state"] in ("ready", "asleep"):
                return {**base, "provider": e.client.provider, "base_url": e.client.base_url,
                        "model": e.client.model, "vision_model": e.client.vision_model, "ok": True, "error": None,
                        "through": KIND_LABELS[e.kind], "endpoint": e.name, "kind": e.kind,
                        "asleep": st["state"] == "asleep"}
            if st["error"]:
                errors.append(st["error"])
        first = cands[0]
        # Batch work can wait for the home computer; a person at the keyboard can't.
        waiting = self.mode == "batch" and any(e.kind == "home" for e in cands)
        return {**base, "provider": first.client.provider, "base_url": first.client.base_url,
                "model": first.client.model, "vision_model": first.client.vision_model, "waiting": waiting,
                "error": " ".join(dict.fromkeys(errors)) or "No AI endpoint is reachable right now."}

    def usage(self) -> dict:
        clients = [e.client for e in self.endpoints if getattr(e.client, "calls", 0)]
        tasks: Counter = Counter()
        for c in clients:
            tasks.update(c.tasks)
        return {"model": self.model, "calls": sum(c.calls for c in clients),
                "failures": sum(c.failures for c in clients),
                "seconds": round(sum(c.seconds for c in clients), 1), "tasks": dict(tasks),
                "through": KIND_LABELS[self.last_used.kind] if self.last_used else None}

    # ── calls ─────────────────────────────────────────────────────────────
    def chat_json(self, messages, schema, task, images=None):
        return self._route(task, lambda c: c.chat_json(messages, schema, task, images=images))

    def chat_text(self, messages, task, images=None) -> str:
        return self._route(task, lambda c: c.chat_text(messages, task, images=images))

    def _route(self, task, call):
        last: Exception | None = None
        for e in self._candidates(feature_of(task)):
            if e.kind == "home" and not relay.online():
                last = LLMUnavailable("The home computer isn't connected right now.")
                continue
            try:
                result = call(e.client)
                self.last_used = e
                return result
            except LLMUnavailable as err:  # that endpoint is down: try the next one
                last = err
        raise last or LLMUnavailable(self.blocked_reason or "No AI endpoint can take this right now.")


def routed_client(config, mode: str = "realtime", feature: str | None = None) -> RoutedClient:
    return RoutedClient(build_endpoints(config), mode, feature)


def describe(config) -> list[dict]:
    """Every endpoint and its state, for Settings."""
    out = []
    for e in build_endpoints(config):
        st = e.state()
        runner = relay.info() if e.kind == "home" else None
        out.append({
            "name": e.name, "kind": e.kind, "label": KIND_LABELS[e.kind], "state": st["state"], "error": st["error"],
            "model": e.client.model if (e.kind != "home" or (runner and runner["model"])) else "",
            "use_for": sorted(e.use_for), "features": sorted(e.features),
            "runner": runner and {"name": runner["name"], "online": runner["online"], "last_seen": runner["last_seen"]},
        })
    return out
