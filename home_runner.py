"""Let the finance server use this computer's AI model, without the server reaching in.

Run this on the computer with the GPU (the one running Ollama or the agent stack):

    python home_runner.py --server https://finance.<your-tailnet>.ts.net

It asks the server for work, runs each request on the local model, and sends the answer
back. Every connection starts from this computer; the server never connects to it. When
this isn't running, the server's AI features that depend on it are hidden on every device,
and imported photos wait until it is back.

The local model is chosen the same way as for the app itself: LLM_PROVIDER, LLM_BASE_URL,
LLM_MODEL, LLM_VISION_MODEL, LLM_API_KEY, LLM_NUM_CTX, LLM_TIMEOUT (defaults: the agent
stack's Ollama on this machine). Standard library only.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time
import urllib.error
import urllib.request

from importer.llm import LLMClient, LLMError, LLMUnavailable


def _env(name: str, default: str) -> str:
    return os.environ.get(f"LLM_{name}", os.environ.get(f"IMPORT_LLM_{name}", default))


def local_client() -> LLMClient:
    return LLMClient(
        provider=_env("PROVIDER", "ollama"), base_url=_env("BASE_URL", "http://127.0.0.1:11434"),
        model=_env("MODEL", "qwen3.5:9b"), vision_model=_env("VISION_MODEL", "") or None,
        api_key=_env("API_KEY", "") or None, num_ctx=int(_env("NUM_CTX", "32768")),
        timeout=int(_env("TIMEOUT", "180")), think=_env("THINK", "0") == "1",
        allow_remote=False,  # the runner only ever talks to a model on this computer
    )


class Server:
    def __init__(self, base_url: str, token: str = ""):
        self.base_url = base_url.rstrip("/")
        self.token = token

    def post(self, path: str, payload: dict, timeout: float) -> dict:
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["X-Runner-Token"] = self.token
        req = urllib.request.Request(self.base_url + path, data=json.dumps(payload).encode(),
                                     headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))


def run_job(client: LLMClient, job: dict) -> str:
    images = [base64.b64decode(b) for b in (job.get("images") or [])] or None
    return client._chat(job.get("messages") or [], job.get("task") or "job", schema=job.get("schema"), images=images)


def serve(server: Server, client: LLMClient, name: str, once: bool = False, log=print, stop=None,
          status: dict | None = None) -> None:
    """Collect and answer model requests until `stop` (a threading.Event) is set.

    `status`, if given, is kept up to date for a caller that shows it (the tray): connected, jobs, last_error.
    """
    hello = {"name": name, "model": client.model, "vision_model": client.vision_model, "wait": 25}
    status = status if status is not None else {}
    status.update(connected=False, jobs=0, last_error=None)
    delay = 5

    def pause(seconds):
        if stop is not None:
            stop.wait(seconds)
        else:
            time.sleep(seconds)

    while not (stop is not None and stop.is_set()):
        try:
            job = server.post("/api/ai/runner/poll", hello, timeout=40).get("job")
            delay = 5
            status.update(connected=True, last_error=None)
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:200]
            log(f"The server refused the runner (HTTP {e.code}): {detail}")
            status.update(connected=False, last_error=f"The server refused the runner (HTTP {e.code})")
            if once:
                return
            pause(60)
            continue
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError, ValueError) as e:
            log(f"Can't reach {server.base_url} ({getattr(e, 'reason', e)}); trying again in {delay}s")
            status.update(connected=False, last_error=f"Can't reach the server ({getattr(e, 'reason', e)})")
            if once:
                return
            pause(delay)
            delay = min(delay * 2, 60)
            continue
        if job:
            started = time.time()
            result = {"id": job["id"]}
            try:
                result["content"] = run_job(client, job)
                outcome = "done"
            except LLMUnavailable as e:
                result.update(error=f"The home model isn't reachable: {e}", unavailable=True)
                outcome = "local model unreachable"
            except LLMError as e:
                result["error"] = str(e)
                outcome = "model error"
            try:
                server.post("/api/ai/runner/result", result, timeout=30)
            except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
                outcome = f"couldn't send the answer ({getattr(e, 'reason', e)})"
            status["jobs"] = status.get("jobs", 0) + 1
            # The task name only. What the request and the answer contain is never printed.
            log(f"{job.get('task', 'job')}: {outcome} in {time.time() - started:.1f}s")
        if once:
            return
    status["connected"] = False


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--server", default=os.environ.get("FINANCE_SERVER", ""),
                        help="The finance app's address, e.g. https://finance.<tailnet>.ts.net (or FINANCE_SERVER)")
    parser.add_argument("--token", default=os.environ.get("AI_RUNNER_TOKEN", ""),
                        help="Only if the server sets AI_RUNNER_TOKEN (or set the same variable here)")
    parser.add_argument("--name", default=os.environ.get("RUNNER_NAME", "home computer"),
                        help="Shown in the app's Settings")
    args = parser.parse_args(argv)
    if not args.server:
        parser.error("--server is required (or set FINANCE_SERVER)")
    client = local_client()
    if not client.enabled:
        print(client.blocked_reason, file=sys.stderr)
        return 2
    status = client.status()
    print(f"Local model: {client.model} at {client.base_url} "
          f"({'ready' if status.get('ok') else 'NOT READY: ' + str(status.get('error'))})")
    print(f"Serving {args.server} as \"{args.name}\". Ctrl+C to stop.")
    try:
        serve(Server(args.server, args.token), client, args.name)
    except KeyboardInterrupt:
        print("\nStopped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
