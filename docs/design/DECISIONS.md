# Design decisions

A running log, newest first. Each entry gives the date, the decision, why, what was rejected, and where it came from. Entries are never deleted. A reversed entry is marked **Superseded** with the date and the entry that replaced it.

Plans are in [plans/](plans/), indexed in [README.md](README.md).

## 2026-11-24

- **Re-deploy by stopping and starting the VM, not over SSH.** The wait succeeds only on this run's own `deploy-id`. Why: `gcloud compute ssh` creates an OS Login key and needs a path into the VM; a "ready" from the previous boot ended the wait early. Rejected: SSH. Source: PR #7, [plan](plans/2026-11-24-deploy-script-fixes.md).
- **Deploy scripts choose the project per run (`CLOUDSDK_CORE_PROJECT`) and turn off prompts.** Why: `gcloud config set project` silently changed the owner's default project, and a hidden prompt could stall the run. Rejected: `gcloud config set project`. Source: PR #5.
- **The owner pastes the Tailscale auth key and edits the tailnet policy themselves.** The assistant guides but does not type credentials or change the live policy. Why: the owner keeps control of credentials and access rules. Source: deploy sessions, 2026-11-24; [deploy/README.md](../../deploy/README.md).
- **Stock-plan documents get their own type, `equity`.** Why: their "total" and "tax" lines were misread as a receipt. Source: PR #6.
- **An RSU grant's vest schedule comes from the notice; you type the ticker.** Why: the schedule must match the document, and notices don't print a ticker. Source: PR #8.
- **A model's value is kept only if it appears in the document.** The same grounding rule as the original importer. Source: PR #8, commit `8b196b6`.
- **The import review loads one page of rows at a time; bulk change acts on every matching row, not only the visible page.** Why: a 3,000-row file made the page heavy (first response about 1.3 MB, now about 25 KB). Rejected: loading all rows. Source: PR #9.
- **The desktop installer copies the app out of the checkout and uses the signed python.org Python.** Why: the Start menu entry must not depend on a working copy, and Smart App Control blocks unsigned interpreters. Uninstall never deletes data. Source: PR #10.
- **The tray runs as `Finance.exe`, a renamed `pythonw`.** Why: Task Manager shows "Finance" instead of "pythonw". Source: PR #10.
- **Keep the first AI placement review, marked superseded.** Why: its prices and volume estimates still apply. Source: PR #11, [ai-placement.md](ai-placement.md).

## 2026-11-23

- **One private cloud server holds the data; every device is a client.** Why: the owner's phone, laptop and desktop should see one copy, and the owner's other projects already use this pattern. Rejected: an on-device core with whole-file sync. Source: [cloud-server-and-ai-endpoints.md](cloud-server-and-ai-endpoints.md), [plan](plans/2026-11-23-private-cloud-server-ai-endpoints.md).
- **The server is a VM reachable only on the tailnet, not Cloud Run.** Why: SQLite needs a persistent disk; the backup timer, import worker and AI queue live in process memory; a public URL was not wanted. Rejected: Cloud Run with a public URL and an access key. Source: same design doc, "Why a VM".
- **Tailscale is the only way in; the app has no passwords.** Identity comes from Tailscale's header, trusted only with `TRUST_TAILSCALE_HEADERS=1`. Why: one tailnet policy decides who reaches which app. Rejected: a login inside the app. Supersedes the 2026-05-09 "no auth, localhost only" entry for the server. Source: PR #4.
- **The home computer pulls AI work; the server never connects into the home.** Why: a phone can use the desktop GPU without any tailnet rule pointing at the home. Source: design doc, "Where AI work runs".
- **AI endpoints are tried in a fixed order: home computer, the app's own machine, your own cloud endpoint, then a paid API only for the features it lists.** Why: a paid API sends financial documents to a third party. Source: design doc; [deploy/README.md](../../deploy/README.md).
- **A cloud endpoint that sleeps when idle is used for batch work only.** Why: waking it takes too long for the assistant. Source: design doc.
- **AI controls that can't work on this device are hidden, not greyed out.** Photos wait for the home computer. **Settings → This device** says why. Source: design doc, PR #4.
- **Browser dictation is left out.** Why: browser speech recognition sends audio to the browser vendor. Source: design doc.
- **The server can add backups but not delete them (`BACKUP_PRUNE=bucket`).** A bucket rule expires old scheduled backups. Why: a compromised server can't erase the history. Supersedes the app-side pruning of PR #2 on the server. Source: PR #4.
- **Every save carries the revision it was based on; a stale save is refused (HTTP 409).** The audit log keeps field names, never values. Both hook into the database session, so new endpoints get them for free. Source: PR #4.
- **Data stays on machines the owner controls; a paid AI service for a named feature is the only exception.** Restates PRD goal G5, which said no data ever leaves the device. Source: [docs/PRD.md](../PRD.md) §2, design doc.
- **Pages are grouped by role (view only, you manage, guidance), not by data type.** Old addresses redirect. Why: the owner wanted to know exactly what is editable. Rejected: the old sidebar by data type. Source: PR #3.
- **The assistant only picks read-only lookups and words the answer; any number the app did not compute is discarded; it never saves.** Source: PR #3.
- **The service worker never caches `/api/`.** Why: financial data would otherwise sit on phones. Source: PR #3.
- **Alpine.js, Chart.js and the compiled Tailwind file are served from the app; no CDN at run time.** Supersedes the CDN plan in [SRD](../SRD.md) §2. Source: PR #3.
- **Phones reach the app over HTTPS through Tailscale Serve, never an open network address or Funnel.** Why: the app has no sign-in, and browsers install web apps only from secure addresses. Source: PR #3.
- **Then vs. Now is a real page, not only a wireframe.** Source: commit `0aa992e`, [plan](plans/2026-11-22-then-vs-now.md).
- **Clear All Data and Restore always back up first; Clear deletes nothing if the backup fails.** Why: no destructive action may lose data. Source: PR #2.
- **Backup credentials come from Application Default Credentials and are never stored by the app.** Source: PR #2.
- **"Load Sample Data" is removed; the sample set lives in `tests/sample_data.py`.** Supersedes PRD F7's sample loader. Source: PR #2, PR #3.
- **The importer reuses the agent stack's Ollama server rather than its own model process.** Why: one 12 GB GPU; a second model would reload or not fit. Source: import session, 2026-11-23; `LLM_NUM_CTX` comment in `config.py`.

## 2026-11-22

- **Tax estimates cover 2026 US federal tax only, with a flat state rate; amounts are taken as gross.** Why: a planning estimate, not filing. Left out: credits, AMT, phase-outs, state brackets. Supersedes the PRD non-goal "no tax engine". Source: PR #1, [plan](plans/2026-11-22-tax-treatments-taxes-page.md).
- **401(k), HSA and IRA contributions are transfers in the forecast, not spending.** Source: PR #1.
- **No migration tool; the app creates tables and adds missing columns at startup.** Supersedes Alembic in [SRD](../SRD.md) §3.3. Source: PR #1, `_ADDED_COLUMNS` in `app.py`.
- **Import uses rules first and the AI last; every AI answer is checked, retried once with the reason, then flagged.** Source: commit `8b196b6`, [plan](plans/2026-11-22-import-statements-local-ai.md).
- **The model is local by default (Ollama `qwen3.5:9b`); a non-local address is refused unless `LLM_ALLOW_REMOTE=1`.** Why: the documents are financial. Partly superseded 2026-11-23 by the endpoint list. Source: [ai-placement.md](ai-placement.md).
- **A paid API fallback for imports is recommended as opt-in per batch, not built.** Superseded 2026-11-23 by paid endpoints limited to named features. Source: ai-placement.md, "Open questions".
- **A private cloud GPU is judged no gain while the app runs on the desktop.** Superseded 2026-11-23 when the app moved to a server. Source: ai-placement.md.
- **Then vs. Now uses share prices typed in by hand; no price feed.** Source: commit `0aa992e`, [PRD](../PRD.md) §8.

## 2026-05-17

- **Loans keep a balance history from recorded snapshots, shown as a chart.** Source: commit `4b02b0d`.

## 2026-05-11

- **Rewrite as Flask + SQLite + Jinja2, with no front-end build step.** Rejected: the React single-page app. Source: commit `bb0a1e9`, [BUILD_SUMMARY.md](../../BUILD_SUMMARY.md), [plan](plans/2026-05-09-prd-srd-v1-flask-sqlite.md).
- **Flask over Django; SQLite over PostgreSQL; money as integers in minor units; ISO date strings; nanoid ids; schedules as JSON.** Source: BUILD_SUMMARY.md, "Key Implementation Decisions".
- **Accounts are soft-deleted; other records are hard-deleted.** Source: BUILD_SUMMARY.md, "API Design".
- **RSU net value and ESPP purchase price formulas.** Source: [SRD](../SRD.md) §9.1–9.2.

## 2026-05-09

- **Local SQLite instead of Google Drive; a Flask app instead of a single-page app.** Source: PRD and SRD v0.2 headers.
- **Firebase Auth and Firestore instead of Google OAuth PKCE and Drive.** Superseded 2026-05-11 by the Flask rewrite. Source: commit `a4d1ca3`, [plan](plans/2026-05-09-spa-firebase-first-plan.md).
- **v1 has no sign-in and listens on localhost only.** Superseded 2026-11-23 for the server by "Tailscale is the only way in". Source: [SRD](../SRD.md) §10.
- **PRD non-goals: no bank pulls, no receipt scanning, no tax engine, no several users, no native phone app, no cloud sync.** Later reversed: receipts (2026-11-22), tax engine (2026-11-22), a private server instead of cloud sync (2026-11-23). Still in force: no bank pulls, no native phone app. Source: [PRD](../PRD.md) §3.
