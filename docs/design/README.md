# Design record

What was planned, what was decided, when and why.

- [DECISIONS.md](DECISIONS.md): every decision, newest first.
- [cloud-server-and-ai-endpoints.md](cloud-server-and-ai-endpoints.md): the current architecture (one private server, AI wherever it can run).
- [ai-placement.md](ai-placement.md): the first AI placement review, superseded but kept for its prices and estimates.
- [../PRD.md](../PRD.md) and [../SRD.md](../SRD.md): the original product and software requirements (v0.2, 2026-05-09). Some parts are out of date; DECISIONS.md lists what changed.
- [../wireframes-v3/](../wireframes-v3/index.html): the wireframes the v1 pages were built from.

## Plans

| Date | Plan | Status |
|---|---|---|
| 2026-11-24 | [Account balances follow imported transactions](plans/2026-11-24-balances-follow-transactions.md) | Done, PR #13 |
| 2026-11-24 | [Windows desktop app: Start menu entry and tray](plans/2026-11-24-desktop-tray-start-menu.md) | Done, PR #10 |
| 2026-11-24 | [Paged import review and bulk change](plans/2026-11-24-import-paging-bulk-edit.md) | Done, PR #9 |
| 2026-11-24 | [Read RSU grant notices into a Plan RSU grant](plans/2026-11-24-rsu-grant-notice-import.md) | Done, PR #8 |
| 2026-11-24 | [Recognise stock-plan documents](plans/2026-11-24-equity-document-type.md) | Done, PR #6 |
| 2026-11-24 | [Deploy script fixes from the first real deploy](plans/2026-11-24-deploy-script-fixes.md) | Done, PR #5, PR #7 and PR #12 |
| 2026-11-23 | [One private cloud server for every device](plans/2026-11-23-private-cloud-server-ai-endpoints.md) | Done, PR #4; cloud AI endpoint not deployed |
| 2026-11-23 | [Pages by role, Insights, AI assistant, installable app](plans/2026-11-23-role-ui-insights-assistant-pwa.md) | Done, PR #3 |
| 2026-11-23 | [Google Cloud backups, restore points, Clear All Data](plans/2026-11-23-gcs-backups-restore-points.md) | Done, PR #2 |
| 2026-11-22 | [Where the AI models run (first review)](plans/2026-11-22-ai-placement-review.md) | Done; superseded 2026-11-23 |
| 2026-11-22 | [Import statements, receipts and pay stubs with a local AI](plans/2026-11-22-import-statements-local-ai.md) | Done, with PR #3 |
| 2026-11-22 | [Then vs. Now](plans/2026-11-22-then-vs-now.md) | Done, with PR #3 |
| 2026-11-22 | [Tax treatments and a Taxes page](plans/2026-11-22-tax-treatments-taxes-page.md) | Done, PR #1 |
| 2026-05-09 | [v1: a local Flask app with one SQLite file](plans/2026-05-09-prd-srd-v1-flask-sqlite.md) | Done 2026-05-11 |
| 2026-05-09 | [First plan: a single-page app with cloud storage](plans/2026-05-09-spa-firebase-first-plan.md) | Dropped 2026-05-11 |
