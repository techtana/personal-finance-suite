# One private cloud server for every device, with AI wherever it can run

**Status:** done. Code in PR #4 (merged 2026-11-24); first deployed 2026-11-24, with fixes in PR #5 and PR #7. The private cloud AI endpoint (`deploy/ai-endpoint/`) is written but has never been deployed.

The full design is [cloud-server-and-ai-endpoints.md](../cloud-server-and-ai-endpoints.md). This page summarises it.

## Goal

One server holds the only copy of the data and does the work. The phone, laptop and desktop are all clients. AI features run wherever a model is available, and are hidden where none is.

## Approach

- A small Google Cloud VM with no public IP, reachable only through Tailscale Serve. Data on its own disk with daily snapshots. One waitress process.
- Who is asking comes from Tailscale's identity header, trusted only when `TRUST_TAILSCALE_HEADERS=1`. `ALLOWED_LOGINS` can narrow it further.
- An audit log (**Settings → Activity**) records every create, change and delete, with field names but not values.
- A stale-save check: the page sends the data revision it loaded (`X-Base-Rev`). If another device saved since, the save is refused (HTTP 409) and asks for a reload.
- Backups the server can add but not delete (`BACKUP_PRUNE=bucket`), and a weekly restore check (`backups verify`).
- AI endpoints in order: the home computer (`home_runner.py`, which pulls work, so the server never connects into the home), the app's own machine, your own cloud endpoint, then a paid API only for the features it lists. Each endpoint is marked realtime, batch or both.
- `/api/capabilities` tells each page what works on this device; **Settings → This device** explains it.

## Options considered

- The owner's two existing hosting patterns: a Tailscale-only VM (chosen), and a public Cloud Run service with its own key and code (rejected: public URL).
- Cloud Run for the app: rejected, because SQLite needs a persistent disk, and the backup timer, import worker and AI queue live in process memory.
- An on-device core with whole-file sync: dropped as no longer needed.

## Left out

Per-person permissions; a per-person check on restore and clear; deploying the cloud AI endpoint.
