# One server in the cloud, many devices, AI wherever it can run

Decided 2026-11-23. Status: deployed 2026-11-24 with `deploy/deploy.sh` (see
[deploy/README.md](../../deploy/README.md)). The private cloud AI endpoint is not deployed.

## The shape

```
 Phone / laptop / desktop (installed web app)          Google Cloud project
 ─────────────────────────────────────────         ┌───────────────────────────────────────────┐
  Tailscale ── WireGuard ────────────────────────▶ │ small VM, no public IP                     │
  https://finance.<tailnet>.ts.net                 │  tailscale serve :443                      │
                                                   │    └▶ 127.0.0.1:8080  the app (one process) │
 Home desktop with the GPU                         │         SQLite on a separate data disk      │
  home_runner.py ── asks for AI work ────────────▶ │         daily disk snapshots                │
  (outbound only; runs it on local Ollama)         │         daily backups ─▶ bucket (add-only)  │
                                                   └───────────────┬───────────────────────────┘
                                                                   │ identity token (optional)
                                                                   ▼
                                                   Private Cloud Run GPU service (same or another project)
```

- **The server is the one copy of the data** and the one place the calculations run. Every
  device is a client of it. There is no sync between devices and no data stored on them.
- **Tailscale is the only way in.** The app listens on loopback; Tailscale Serve publishes it
  and tells the app who is asking. There are no app passwords.
- **AI is optional and runs wherever something can take it.** The app itself never needs it.

This replaces the earlier rule "no data ever leaves the user's device" (PRD goal G5) with:
**data stays on machines the owner controls** (the server, the home computer, the owner's own
cloud endpoint). A paid AI service is the one exception, and only for features the owner
switches on for it.

## Why a VM and not Cloud Run for the app

SQLite needs a disk that persists, and three things live in the app process's memory: the
backup timer, the import worker, and the queue of AI requests the home computer collects.
Scale-to-zero gives neither. The cost is that every device needs Tailscale running.

## Safe updates

| Risk | What stops it | Where |
|---|---|---|
| Someone unknown opens the app | No public address; tailnet rule for `tag:finance`; optional `ALLOWED_LOGINS` | `deploy/`, `audit.py` |
| A forged "who am I" header | `Tailscale-User-Login` is believed only when `TRUST_TAILSCALE_HEADERS=1`, which the deploy sets because nothing but Serve can reach the app | `audit.py` |
| Two devices edit the same entry | Every answer carries the data revision (`X-Data-Rev`); a change says which revision the page read (`X-Base-Rev`); if another page changed that record since, the save gets 409 and a "reload" message | `audit.py`, `static/app.js` |
| "Who changed this?" | Every create, change and delete writes a row to `audit_log`: time, Tailscale login, record, field names. Never values. Settings → Activity shows it | `audit.py`, `api/activity.py` |
| A bug or break-in erases the backups | The VM's service account can add and read backups but not delete or overwrite them (`BACKUP_PRUNE=bucket`); a bucket rule expires old scheduled ones; deleted objects stay recoverable for 30 days | `deploy/deploy.sh`, `backup.py` |
| The disk or VM is lost | Daily disk snapshots kept 14 days, on a disk that survives deleting the VM | `deploy/deploy.sh` |
| Backups that don't restore | Weekly restore drill on the VM: `flask backups verify` downloads the newest backup into a scratch file and checks it opens | `deploy/startup.sh`, `backup.py` |

The stale-save check and the audit log are hooked into the database session, so no endpoint
has to remember them and a new endpoint gets both for free. Whole-database actions (restore,
clear) add one event row each.

Limits worth knowing:

- The revision a page sends is per kind of record (the last time it loaded that list), so a
  save can very occasionally be refused when the page already showed the newer data through
  another list. Reloading clears it. It never lets a stale save through for a record the page
  loaded through its own list.
- Callers that send no `X-Base-Rev` (scripts, the import worker) are not checked.
- Restoring a backup also restores that backup's activity log.

## Where AI work runs

`ai/endpoints.py` builds an ordered list; each request goes to the first endpoint that can
take it and falls to the next if that one is down.

| Order | Kind | What it is | Set with |
|---|---|---|---|
| 1 | `home` | The home computer. It runs `home_runner.py`, which asks the server for work and posts answers back | `AI_HOME_RUNNER=1` on the server |
| 2 | `server` | A model on the same machine as the app (the original single-PC setup) | `LLM_PROVIDER`, `LLM_BASE_URL`, `LLM_MODEL` |
| 3 | `own-cloud` | A machine the owner rents: Cloud Run with a GPU, or an always-on one | `AI_ENDPOINTS` (JSON list) |
| 4 | `paid` | Someone else's API. Used only for the features it lists | `AI_ENDPOINTS` with `"kind": "paid", "features": [...]` |

Each endpoint says what it is for:

- **realtime**: a person is waiting (Ask, filter in words, explain, draft).
- **batch**: the work can wait (reading imported files).

A Cloud Run service that sleeps when idle is marked `"use_for": ["batch"], "assume_up": true`:
it is never used for the assistant (waking takes too long) and the app doesn't wake it just to
ask whether it is there. Kept warm (`MIN_INSTANCES=1`) it serves both and bills all month.

**The server never connects into the home.** The home computer makes every connection. That
is also what lets a phone use the desktop's GPU: the phone asks the server, the server queues
the request in memory (`ai/relay.py`), the desktop collects it. Nothing about a request is
written to the server's disk, and the runner's log shows task names only.

A private Cloud Run service is called with a Google identity token for the VM's service
account (`"auth": "google-id-token"`); only that account has `run.invoker`.

## Show only what works on this device

`GET /api/capabilities` reports each AI feature as available (and through which place),
waiting, or not available with the reason. The pages follow three rules:

1. A feature that can't work is not shown. No greyed-out buttons.
2. A realtime feature shows only while something can answer right now. A batch feature shows
   whenever a runner is set up: a photo dropped while the home computer is off gets the status
   **Waiting** and is read by itself when the runner connects.
3. Settings → **This device** is the one place that lists every optional feature, including
   the hidden ones, with why and what would enable it. It also covers what the device itself
   offers: the camera button on Import appears only on a device with a camera and only when a
   model can read the photo.

Results are never hidden: rows read on the desktop show on the phone.

Dictation was considered and left out: the browser's speech recognition sends audio to the
browser vendor on most devices, which breaks "data stays on machines the owner controls". The
phone keyboard's own microphone key remains the owner's choice.

## Things that would quietly undo this

- Publishing the container on `0.0.0.0`, or adding a public IP, a load balancer or Tailscale
  Funnel: the identity header could then be forged.
- Running more than one app process (the runner queue, backup timer and import worker are
  per process).
- A tailnet rule from `tag:finance` to a person's device or the home network.
- Giving the VM's service account delete rights on the backup bucket, or setting
  `BACKUP_PRUNE=app` on the server.
- `--allow-unauthenticated` on the AI service, or `roles/run.invoker` for anyone but the
  finance VM's service account.
- Adding a paid endpoint with features listed "to try it": that sends financial documents to
  a third party from then on.
- Caching `/api/` answers in the service worker: financial data would then live on phones.

## Not done

- `deploy/deploy.sh` and `deploy/startup.sh` have run once, for the first deploy (2026-11-24),
  from Git Bash on Windows. The re-deploy path (an existing VM) has not been exercised.
  `deploy/ai-endpoint/` has never been run at all.
- The weekly restore drill is installed on the VM but its first result has not been looked at.
- One household, one database. There are no per-person permissions: anyone the tailnet rule
  (and `ALLOWED_LOGINS`) lets in can see and change everything.
- A per-person check for the most sensitive actions (restore, clear all data) is not built;
  Tailscale vouches for the device, not for who is holding it.
