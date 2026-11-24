"""Model requests waiting for the home computer to collect them.

The server never opens a connection to the home network. home_runner.py, running on
the computer with the GPU, asks this app for work (a long poll), runs each request on
its local model and posts the answer back. To the rest of the app this looks like a
slow model call.

Everything here lives in this process's memory: nothing about a request is written to
disk, and a restart drops whatever was waiting (the caller sees "not available").
"""

from __future__ import annotations

import threading
import time
import uuid
from collections import deque

from importer.llm import LLMError, LLMUnavailable

ONLINE_WINDOW = 45.0  # seconds since the runner last asked for work

_cv = threading.Condition()
_pending: deque[str] = deque()
_jobs: dict[str, dict] = {}
_runner = {"seen": 0.0, "name": "", "model": "", "vision_model": "", "busy": 0}
_on_connect: list = []


def reset() -> None:
    """Forget everything (tests)."""
    with _cv:
        _pending.clear()
        _jobs.clear()
        _runner.update(seen=0.0, name="", model="", vision_model="", busy=0)
        _cv.notify_all()


def on_connect(callback) -> None:
    """callback() runs each time a runner appears after there was none."""
    if callback not in _on_connect:
        _on_connect.append(callback)


def _online_locked() -> bool:
    return _runner["busy"] > 0 or time.time() - _runner["seen"] < ONLINE_WINDOW


def online() -> bool:
    with _cv:
        return _online_locked()


def info() -> dict:
    with _cv:
        return {"online": _online_locked(), "name": _runner["name"], "model": _runner["model"],
                "vision_model": _runner["vision_model"], "last_seen": _runner["seen"] or None,
                "waiting_jobs": len(_pending)}


def submit(payload: dict, timeout: float) -> str:
    """Queue one model request and wait for the runner's answer (the model's text)."""
    job = {"id": uuid.uuid4().hex, "payload": payload, "done": threading.Event(), "content": None,
           "error": None, "unavailable": False, "claimed": False}
    with _cv:
        if not _online_locked():
            raise LLMUnavailable("The home computer isn't connected right now.")
        _jobs[job["id"]] = job
        _pending.append(job["id"])
        _cv.notify_all()
    try:
        if not job["done"].wait(timeout):
            raise LLMUnavailable("The home computer didn't answer in time.")
        if job["error"]:
            raise (LLMUnavailable if job["unavailable"] else LLMError)(job["error"])
        return job["content"] or ""
    finally:
        with _cv:
            _jobs.pop(job["id"], None)
            try:
                _pending.remove(job["id"])
            except ValueError:
                pass
            if job["claimed"] and not job["done"].is_set():
                _runner["busy"] = max(0, _runner["busy"] - 1)


def poll(runner: dict, wait: float) -> dict | None:
    """Called by the runner: the next request, or None after `wait` seconds with nothing to do."""
    with _cv:
        was_online = _online_locked()
        _runner.update(seen=time.time(), name=str(runner.get("name") or "")[:80],
                       model=str(runner.get("model") or "")[:80],
                       vision_model=str(runner.get("vision_model") or "")[:80])
    if not was_online:
        for callback in list(_on_connect):
            callback()
    deadline = time.time() + max(0.0, wait)
    with _cv:
        while True:
            while _pending:
                job = _jobs.get(_pending.popleft())
                if job:
                    job["claimed"] = True
                    _runner["busy"] += 1
                    _runner["seen"] = time.time()
                    return {"id": job["id"], **job["payload"]}
            remaining = deadline - time.time()
            if remaining <= 0:
                _runner["seen"] = time.time()
                return None
            _cv.wait(min(remaining, 5.0))
            _runner["seen"] = time.time()


def complete(job_id: str, content: str | None = None, error: str | None = None, unavailable: bool = False) -> bool:
    """Called by the runner with the answer. False if nobody is waiting for it any more."""
    with _cv:
        job = _jobs.get(job_id)
        if not job or job["done"].is_set():
            return False
        job["content"], job["error"], job["unavailable"] = content, error, bool(unavailable)
        if job["claimed"]:
            _runner["busy"] = max(0, _runner["busy"] - 1)
        _runner["seen"] = time.time()
        job["done"].set()
        return True
