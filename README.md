# Personal Finance Suite

A self-hosted planner for your own money. You enter what you know: accounts, salary, bills, RSU grants, ESPP, loans. It shows your net worth over time, projects it forward, estimates your US federal tax and tells you when reality drifts from the plan. The data stays on machines you control: one computer, or a private server that only your own devices can reach.

## When to use it

- You plan from scheduled events (paychecks, vests, bills, loan payments) and want a clear picture instead of a big spreadsheet.
- You have equity pay (RSUs, ESPP) and want it in the same picture as cash and loans.
- You don't want a bank-connected service holding your data.

It is for one person or household. It is not a bookkeeping tool, it doesn't pull data from banks, and it doesn't file taxes. Its tax and forecast figures are planning estimates, not financial or tax advice.

## How it works

```
 Phone / laptop / desktop  ──Tailscale (HTTPS)──▶  Flask app + one SQLite file  ──▶  Google Cloud Storage backups
 (installed web app)                               (your PC, or a private VM)
                                                          ▲
                                     home PC with a GPU ──┘  pulls AI work (optional)
```

One Flask app serves the pages and a REST API ([docs/api.md](docs/api.md)). The business rules live in `engine/` (forecast, tax, vesting, loans, Then vs. Now, Insights) and the file reader in `importer/`. An optional language model reads documents and words answers; the app computes every number itself. The full architecture and its reasons: [docs/design/cloud-server-and-ai-endpoints.md](docs/design/cloud-server-and-ai-endpoints.md).

## Setup across devices

| Device | Role | Set up |
|---|---|---|
| Private cloud VM | Holds the data, serves every device, backs up by itself | [Installation, C](docs/manuals/installation.md#c-private-cloud-server) and [deploy/README.md](deploy/README.md) |
| Windows PC (with GPU) | Opens the app from the Start menu; shares its AI with the server | [Installation, B](docs/manuals/installation.md#b-windows-desktop-app) |
| Phone, laptop | Installed web app over Tailscale | [Add a device](docs/manuals/installation.md#add-a-phone-or-another-device) |
| One computer only | Everything on one machine, for trying it out or development | [Installation, A](docs/manuals/installation.md#a-one-computer) |

Order: Tailscale on every device, then the server, then the desktop app, then phones.

## Quick start

On one computer, to see it work:

1. `python -m venv .venv`, then activate it (`.venv\Scripts\activate` on Windows, `source .venv/bin/activate` elsewhere).
2. `pip install -r requirements.txt`
3. `flask run`
4. Open http://localhost:5000.
5. On **Balances**, click **+ Add** and add a cash account with today's balance.
6. On **Plan**, click **+ Add rule** and add your salary and rent.
7. Open **Forecast**.
8. Optional: drop a sample file from `docs/sample-data/imports/` on **Import**.

Day-to-day use: [docs/manuals/user-guide.md](docs/manuals/user-guide.md). Problems: [docs/manuals/troubleshooting.md](docs/manuals/troubleshooting.md).

## Repository layout

| Folder or file | What it holds |
|---|---|
| `app.py`, `config.py`, `models.py`, `schemas.py` | App factory, settings from environment variables, database models, validation |
| `api/` | REST API blueprints ([docs/api.md](docs/api.md)) |
| `pages/` | Page routes, web app manifest, service worker |
| `templates/`, `static/` | Jinja2 pages, Alpine.js and Chart.js code, compiled Tailwind CSS (`static/build/`), pinned libraries (`static/vendor/`) |
| `engine/` | Forecast, recurrence, tax, RSU vesting, ESPP, loans, Then vs. Now, Insights, AI assistant |
| `importer/` | File import: readers, rules, matching, AI tools, review pipeline, `flask imports` commands |
| `ai/` | AI endpoint list and the relay that hands work to a home computer |
| `audit.py`, `backup.py` | Activity log, stale-save check, Tailscale identity; cloud backups and `flask backups` commands |
| `home_runner.py` | Runs on a home computer and answers the server's AI work with a local model |
| `desktop/`, `install-desktop.cmd` | Windows Start menu entry and tray app |
| `deploy/` | Private cloud server: deploy script, VM startup script, tailnet policy reference, optional cloud AI endpoint |
| `Dockerfile`, `wsgi.py` | The server image (waitress, one process) |
| `scripts/` | Rebuild the stylesheet and the app icons |
| `tests/` | pytest suite and sample data |
| `docs/` | Manuals, design record, knowledge base, API, PRD/SRD, wireframes, fictional sample data |
| `instance/` | Runtime data: `finance.db` and import copies (git-ignored) |

## Assumptions and where it applies

- US dollars and US federal tax rules for 2026. Other currencies can be displayed, but tax figures assume US rules.
- Planning, not bookkeeping: a recorded balance is the truth on its date, and the plan explains the rest.
- One person or household, trusted with all of the data.
- Access control is your Tailscale network. The app has no passwords of its own.
- One app process per database file.
- AI is optional. Without it, everything except reading photos and scanned PDFs works.

## Limitations and where it doesn't apply

- No automatic bank or brokerage data. You type values in or import exported files.
- Tax estimates: 2026 tables only (other years reuse them), a flat state rate, no credits, AMT or phase-outs, no filing.
- The forecast has no investment growth, inflation or loan principal/interest split.
- No share-price feed; Then vs. Now uses prices you enter.
- Import doesn't convert currencies, and doesn't read HEIC photos or old `.xls` files.
- Of stock-plan documents, only RSU grant notices are read.
- No per-person permissions: everyone the tailnet lets in sees and changes everything.
- The installer is Windows-only.

## Known issues

This repository's GitHub issues has no open issues as of 2026-11-24. Known so far:

- The cloud AI endpoint in `deploy/ai-endpoint/` has never been deployed.
- Installing the web app on a real phone hasn't been tested. Neither have the desktop tray's menu items and its "run on this computer" mode.
- The import review still loads every row on the server to count and match duplicates (PR #9).
- RSU grant notice import was tested on a made-up sample only (PR #8).
- [QUICK_START.md](QUICK_START.md) and [BUILD_SUMMARY.md](BUILD_SUMMARY.md) describe the May 2026 version. They mention `flask db upgrade` and a seed endpoint, and neither exists any more. Use the manuals instead.
- Possible code issues found while writing these docs, not yet confirmed or fixed, are listed under "Open questions" in [docs/knowledge/](docs/knowledge/README.md).

## Path forward

Running list. Newest first.

- 2026-11-24: Confirm or fix the code issues found while writing the knowledge base.
- 2026-11-24: Test the installable app on a real Android phone and iPhone.
- 2026-11-24: Read more stock-plan documents: other grant-notice layouts, vest summaries, release confirmations, ESPP.
- 2026-11-24: Keep the import review light on the server too, not only in the browser.
- 2026-11-23: Deploy the optional cloud AI endpoint, if the home PC is off too often.
- 2026-11-23: Per-person permissions, and a per-person check on Restore and Clear All Data.
- 2026-11-23: Confirm the 2026 SALT cap against the IRS documents.
- From the PRD: optional share-price feed; more tax years.

## Design decisions

The most important ones. The full log, with the reasons and rejected options: [docs/design/DECISIONS.md](docs/design/DECISIONS.md). Plans: [docs/design/README.md](docs/design/README.md).

- 2026-11-24: The desktop app is a copy installed outside the checkout, with a tray that opens the server and shares this PC's AI.
- 2026-11-24: The import review pages its rows; bulk change acts on every matching row.
- 2026-11-23: One private VM, reachable only on the tailnet, holds the data. Rejected: Cloud Run with a public URL. Why: SQLite needs a disk, and nothing should be public.
- 2026-11-23: Tailscale is the only way in; the app has no passwords. Supersedes "localhost only" (2026-05-09) for the server.
- 2026-11-23: AI runs wherever it can, in a fixed order: home PC, the app's own machine, your own cloud, then a paid API only for named features. Controls that can't work are hidden.
- 2026-11-23: The server can add backups but not delete them; Clear All Data and Restore always back up first.
- 2026-11-23: Every save carries its revision, and a stale save is refused. Changes are logged without values.
- 2026-11-23: Pages are grouped by role: view only, you manage, guidance.
- 2026-11-23: The AI never writes data and never supplies a number; the app computes every figure.
- 2026-11-22: Import uses rules first and the AI last, and checks every AI answer against the document.
- 2026-11-22: Tax is a 2026 US federal planning estimate. Supersedes the PRD non-goal "no tax engine".
- 2026-11-22: No migration tool; the app adds missing columns at startup. Supersedes Alembic (2026-05-09).
- 2026-05-11: Flask, SQLite and Jinja2 with no front-end build at run time; money stored as integer cents. Supersedes the React single-page app.

## Background knowledge

To work on this project you need some personal-finance basics: how US income tax and payroll tax work, how RSUs and ESPP vest and are taxed, how loans amortize, how a plan is reconciled against real balances, what bank export files look like, and how small local language models are kept honest. [docs/knowledge/README.md](docs/knowledge/README.md) explains them from zero.

## Development

Run the tests:

```bash
pytest --cov=. --cov-report=term-missing
```

The live-model tests need Ollama running:

```bash
RUN_LOCAL_LLM_TESTS=1 pytest tests/test_import_live.py -v
```

Rebuild the stylesheet after changing class names in `templates/` or `static/*.js`. It needs Node.js, and `static/build/tailwind.css` is committed, so running the app never does:

```bash
python scripts/build_css.py
```

Redraw the app icons:

```bash
python scripts/make_icons.py
```

Conventions:

- Money is an integer in minor units ($1,234.56 → `123456`). Dates are ISO `YYYY-MM-DD`. Ids are 21-character nanoids.
- A new database column goes into `_ADDED_COLUMNS` in `app.py`, so existing databases get it at startup.
- Every write goes through the database session, so it gets the activity log and the stale-save check.
- Static files carry a `?v=` version, and the service worker uses the same one, so installed copies update by themselves.
- After merging a change that users can see, redeploy the server (`deploy/deploy.sh`). Merging alone changes nothing there.

## License

Personal use only.
