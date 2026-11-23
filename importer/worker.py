"""Background processing: one import at a time on a worker thread.

One at a time because the local GPU serves one model request at a time anyway
(the agent stack runs Ollama with OLLAMA_NUM_PARALLEL=1); dropped files queue.
"""

from __future__ import annotations

import logging
import threading
from concurrent.futures import ThreadPoolExecutor

log = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="import")
_active: set[str] = set()
_lock = threading.Lock()


def submit(app, batch_id: str) -> None:
    from importer.pipeline import process_batch

    if app.config.get("IMPORT_SYNC"):
        process_batch(batch_id)
        return
    with _lock:
        if batch_id in _active:
            return
        _active.add(batch_id)
    _executor.submit(_run, app, batch_id)


def _run(app, batch_id: str) -> None:
    from importer.pipeline import process_batch

    try:
        with app.app_context():
            process_batch(batch_id)
    except Exception:  # pragma: no cover - process_batch records its own failures
        log.exception("import worker crashed on %s", batch_id)
    finally:
        with _lock:
            _active.discard(batch_id)


def is_active(batch_id: str) -> bool:
    with _lock:
        return batch_id in _active


def reap_stale(batches, sync: bool) -> bool:
    """Mark batches left 'processing' by a restart as failed. Returns True if any changed."""
    changed = False
    for b in batches:
        if b.status == "processing" and not sync and not is_active(b.id):
            b.status = "failed"
            b.stage = None
            b.error = "Processing stopped before it finished (the app was restarted). Click Re-read to try again."
            changed = True
    return changed
