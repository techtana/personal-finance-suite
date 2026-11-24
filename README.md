# Personal Finance Suite

A self-hosted Flask web application for personal financial planning. Track income, expenses, equity compensation, and project your net worth over time—all stored locally on your device.

## Features

The app is organised by what you do on each page, and every block on screen is marked with one of these roles:

| Group | Pages | Role |
|---|---|---|
| **Your picture** | Overview, Forecast, Then vs. Now, Taxes | **View only**: computed from your inputs |
| **Your inputs** | Plan, Balances, Import | **You manage**: the only places data is entered or edited |
| **Guidance** | Insights | What the app notices, each item with its basis and a link to act on it |

- **Overview**: Net worth, this month's planned cash flow, what needs attention, history by cash / assets / liabilities
- **Plan**: Recurring rules (income, expenses, RSU grants, ESPP plans) and one-off entries
- **Balances**: Every account, asset and liability in one table; update a value inline or run the monthly check-in;
  share prices
- **Forecast**: Net worth and monthly cash flow from your plan, with what-if (untick any rule or entry)
- **Insights**: Stale balances, net worth off plan, months that run negative, upcoming one-off events, loan
  payoffs, missing share prices, imports waiting for review, tax findings
- **Search, filter and sort** on every list, kept in the page address so a filtered view can be linked
- **AI assistant** (optional, local by default): ask a question, describe a filter in words, get an insight
  explained, draft a Plan entry (see [AI assistant](#ai-assistant))
- **Taxes**: Estimated US federal tax for a year, with charts and plain-language findings; every input is optional
- **Settings**: Configure categories, divergence thresholds, and more
- **Import**: Drop bank/card exports, PDF statements, receipts or pay stubs (text, PDF or a photo); a local AI
  helps read them, you review, then they land in the right place (see [File import](#file-import))
- **Data Management**: Export/import all data as JSON

## Requirements

- Python 3.9+
- SQLite3 (included in Python)

## Setup

### 1. Clone and Navigate

```bash
cd personal-finance-suite
```

### 2. Create Virtual Environment

```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Initialize Database

```bash
flask db upgrade
```

This creates the SQLite database with all tables at `instance/finance.db`.

### 5. Set Up Google Cloud Backups (Optional)

Backups and restore points are full copies of the database saved to a Google Cloud Storage bucket.

1. Create a private bucket in your Google Cloud project (for example `<project-id>-finance-backups`).
2. Sign in once on this computer so the app can reach it:

   ```bash
   gcloud auth application-default login
   ```

3. In the app, open **Settings → Backups**, enter the project and bucket, pick how often to back up, and save.

Backup files are named `finance_<UTC time>_<reason>.db`, where the reason is `scheduled`, `manual`,
`before-clear`, `before-restore` or `before-import`. **Settings → Data → Clear All Data** always saves a backup
first and deletes nothing if that backup fails.

### 6. Run the App

```bash
flask run
```

Open http://localhost:5000 in your browser.

### 7. Install it as an app (optional)

The app is a Progressive Web App: it can be installed and opens full screen with its own icon. On a
phone it uses a bottom tab bar and a menu; on a wide screen, a sidebar.

- **On this computer:** in Chrome or Edge, open the app and choose **Install app** in the sidebar (or the
  install icon in the address bar).
- **On a phone:** the phone must reach the app over **HTTPS**; browsers only install, and only run the
  offline support, on secure addresses. `localhost` counts as secure on the computer itself, but a phone
  can't use it, and a plain `http://192.168.x.x` address won't install. The app has no sign-in, so don't
  expose it to your network or the internet as is. Use [Tailscale Serve](https://tailscale.com/kb/1312/serve),
  which gives the app a private HTTPS address that only devices on your tailnet can open:
  1. Install Tailscale on the computer and the phone and sign in to the same tailnet. In the admin console,
     turn on MagicDNS and HTTPS certificates (DNS page).
  2. On the computer, start the app as usual with `flask run`. It listens on `127.0.0.1:5000` only; keep it
     that way (no `--host 0.0.0.0`). If you use another port, use that port below too.
  3. Once, on the computer, publish it to the tailnet. The setting survives restarts:

     ```bash
     tailscale serve --bg 5000
     ```

     `tailscale serve status` should show `https://<machine>.<tailnet>.ts.net (tailnet only)` proxying to
     `http://127.0.0.1:5000`. Never use `tailscale funnel` for this app: Funnel puts it on the public internet.
  4. On the phone, with Tailscale connected, open `https://<machine>.<tailnet>.ts.net/overview`
     (`<machine>` is this computer's Tailscale name, `<tailnet>` your tailnet's name; both are shown by
     `tailscale serve status`).
  - **Android (Chrome):** menu → **Install app**, or **Install** in the app's menu sheet.
  - **iPhone (Safari):** Share → **Add to Home Screen**. The app's menu shows these steps too.

  **The tailnet is the only lock.** Anyone whose device your tailnet policy lets reach this computer can
  open the app and see everything, with no sign-in. Keep the policy limited to your own devices, remove
  old phones and computers from the tailnet, and leave Funnel off. To stop sharing the app:
  `tailscale serve --https=443 off`. If the phone shows "Can't reach your finance app", check that Tailscale
  is connected on the phone and that `flask run` is running on the computer (a 502 error means Serve is up
  but the app isn't).

What the installed app keeps on the device: only its own styles, scripts, icons and an offline page.
Your financial data is never cached on the phone; every figure comes from the computer running the app.
Without a connection the app shows "Can't reach your finance app" with a retry button. When a new
version of the app is running, a **Reload** bar appears; nothing reloads under an open form.

## Environment Variables

Create a `.env` file in the project root:

```
FLASK_ENV=development
FLASK_APP=app.py
SECRET_KEY=<generate with: python -c "import secrets; print(secrets.token_hex())">
FINANCE_DB_PATH=instance/finance.db
```

## File import

Open **Import** in the sidebar and drop files: CSV/TSV, Excel (.xlsx), OFX/QFX/QBO, JSON, PDF (text or scanned),
plain text, or a photo (JPG/PNG). Each file is read on this computer, staged for review, and only written to your
data when you click **Import**. Every import can be undone.

What goes where:

| Document | Becomes |
|---|---|
| Statement or export | one Plan entry (`ChangeEvent`, type `imported`) per transaction; the closing balance as an account balance snapshot; regular payments (same merchant, steady amount and gap) as *suggested* recurring rules, off until you tick them |
| Receipt | one expense entry with the receipt total; items, tax and tip in the note |
| Pay stub | net pay as income to the account it was paid into; 401(k)/403(b) contributions plus employer match as income to your retirement account; a suggested salary rule |

Transfers between your own accounts and credit card payments are recognised and left unticked, so they aren't
counted as spending or income. Duplicates are caught across files and sources: the same file twice, overlapping
statements, a receipt and the card statement line for the same purchase, a pay stub and the payroll deposit.

### How the local AI is used

The model is small and runs locally, so it only gets narrow questions, and nothing it says is trusted on its own.

1. **Rules first.** OFX files, standard CSV headers, dates, amounts, sign conventions, known merchants and
   transfers are handled by code (`importer/parsing.py`, `importer/statements.py`, `importer/taxonomy.py`).
2. **Memory next.** A column layout you imported before is reused, keyed by the header row
   (`import_profiles`); a category you picked for a merchant is reused (`import_merchant_rules`).
3. **The AI fills gaps** through seven single-purpose tools in `importer/ai_tools.py`: read a photo into text,
   tell what kind of document it is, map a table's columns, find transactions in statement text, read a receipt,
   read a pay stub, categorize unfamiliar merchants (once per merchant, not per row). Each answer's shape is fixed by
   a JSON schema (Ollama constrains decoding to it, so categories can only come from your list).
4. **Every answer is checked.** Amounts must appear in the document, dates must be printed on it, column choices
   must parse across all rows, income categories can't go on spending, receipts must add up
   (subtotal + tax + tip = total) and pay stubs must reconcile (gross − deductions = net). A receipt or pay stub
   is also read by plain rules, and disagreements are flagged. Rejected answers go back to the model once with the
   reason; anything still wrong is dropped and flagged.
5. **You review.** Rows show where each value came from (rules, your earlier choice, the document, the AI) and
   flags such as *Possible duplicate*, *Readers disagree* or *Doesn't add up*. Filters isolate rows that need a
   look or that the AI decided.

If the AI is offline, everything except photos and scanned PDFs still works with rules only.

### Configuration

By default the importer reuses the Ollama server of the personal agent stack (`http://127.0.0.1:11434`, model
`qwen3.5:9b`, `num_ctx` 32768 to match the stack so the loaded model is shared, not reloaded). See
`.env.example` for the `LLM_*` settings (the older `IMPORT_LLM_*` names still work), including routing through the stack's LiteLLM gateway. A base URL
that isn't this computer is refused unless `LLM_ALLOW_REMOTE=1`. Copies of dropped files are kept in
`instance/imports/` for review and re-reading; deleting an import deletes its copy.

From a terminal:

```bash
flask imports status
flask imports read path/to/statement.csv --account <account-id>
```

Sample files (fictional data) are in `docs/sample-data/imports/`. To check the model end to end after changing a
prompt or the model:

```bash
RUN_LOCAL_LLM_TESTS=1 pytest tests/test_import_live.py -v
```

## AI assistant

Optional. The same model client serves Import and the assistant, configured with environment variables:
`LLM_PROVIDER` (`ollama`, `openai` for any OpenAI-compatible server, or `off`), `LLM_BASE_URL`, `LLM_MODEL`,
`LLM_API_KEY`. With `LLM_PROVIDER=off` the app works fully without it.

- **Local by default.** An address that is not this computer is refused unless `LLM_ALLOW_REMOTE=1`, because that
  sends your financial data to that service.
- **Numbers come from the app.** The model picks one read-only lookup and words the reply; a reply containing a
  number the lookup did not produce is discarded and the raw figures are shown instead.
- **It never writes data.** Drafts open a form that you check and save. Words-to-filter can only choose values
  the list actually offers.
- Anything the model produced is marked with the **AI** chip.

## Database Backup

The SQLite database file is located at `instance/finance.db`. Back it up by:

1. **Manual copy**: `cp instance/finance.db instance/finance.backup.$(date +%Y%m%d).db`
2. **Export from app**: Go to Settings → Data → Export. The file holds everything: balances and their
   history, plan rules, one-off entries, share prices, categories and settings. Older export files are
   converted on import.

## API Endpoints

### Accounts & Loans

- `GET /api/accounts` — List accounts
- `POST /api/accounts` — Create account
- `PATCH /api/accounts/<id>` — Update account
- `GET /api/loans` — List loans
- `POST /api/loans` — Create loan
- `GET /api/accounts/<id>/snapshots` — Reconciliation history

### Plan

- `GET /api/rules`, `POST /api/rules`, `PATCH /api/rules/<id>`, `DELETE /api/rules/<id>` — Recurring rules
  (`rule_type`: income, expense, rsu, espp)
- `GET /api/changes`, `POST /api/changes`, `PATCH /api/changes/<id>`, `DELETE /api/changes/<id>` — One-off entries

### Balances

- `GET /api/balances` — Every cash account, asset and liability in one list, with totals and freshness
- `POST /api/balances/record` — Record a value (`entity_type` cash|asset|liability, `entity_id`, `value` in cents,
  optional `date`)
- `GET /api/net-worth/history?months=24&types=cash,asset` — Month-end recorded values by type
- `GET /api/assets`, `POST /api/assets`, `PATCH /api/assets/<id>` — Assets
- `GET /api/prices`, `POST /api/prices`, `DELETE /api/prices/<id>` — Share prices

### Insights

- `GET /api/insights` — Current observations: `{id, source, severity, title, detail, basis, action}`

### Assistant

- `GET /api/assistant/status` — Is the model reachable
- `POST /api/assistant/ask` — `{question}` → answer, the figures it is based on, and a link
- `POST /api/assistant/filter` — `{text, filters, sorts}` → filter values for a list
- `POST /api/assistant/explain` — `{title, detail, basis}` → plain-language wording
- `POST /api/assistant/draft` — `{text}` → a pre-filled Plan entry (nothing is saved)

### Import

- `POST /api/imports` — Upload files (multipart `files`, optional `account_id`, `doc_type`)
- `GET /api/imports`, `GET /api/imports/<id>` — List; one import with its rows
- `PATCH /api/imports/<id>` — Change account; or re-read with `doc_type`, `mapping`, `flip_signs`
- `PATCH /api/imports/<id>/rows/<row_id>` — Edit a row (action, date, amount, description, category)
- `POST /api/imports/<id>/commit`, `POST /api/imports/<id>/undo`, `DELETE /api/imports/<id>`
- `GET /api/imports/ai-status` — Is the local AI reachable

### Projection

- `GET /api/projection?from=2026-05-10&to=2027-05-10` — Run projection (one-time changes count only inside the
  range; balances already include past ones). Add `&disable=<id>,<id>` to leave rules, entries or loans out
  (the answer then includes the unchanged `baseline`), and `&history=12` for recorded net worth alongside

### Taxes

- `GET /api/taxes/summary?year=2026` — Tax estimate for a year (summary, charts data, findings, assumptions)
- `GET /api/taxes/treatments` — Tax treatments that income and expense entries can use
- `GET /api/taxes/profile`, `PATCH /api/taxes/profile` — Filing status, state rate, age, HSA coverage, loss carryover

Income and expense rules and logged changes take an optional `tax_treatment` (wages, 401(k), HSA, FSA,
limited FSA, investment sale, charity, and so on). Untagged income counts as W-2 wages and untagged
expenses as personal spending; the Taxes page lists every default it used. Yearly brackets and limits
live in `engine/tax_tables.py`.

### Settings & Data

- `GET /api/settings` — Get settings
- `GET /api/categories` — List categories
- `GET /api/export` — Download all data as JSON
- `POST /api/import` — Restore from JSON
- `GET /api/backups` — Backup setup and restore points
- `POST /api/backups` — Back up now
- `POST /api/backups/<name>/restore` — Restore a restore point (backs up current data first)
- `POST /api/data/clear` — Back up to Google Cloud, then delete all data

## Project Structure

```
personal-finance-suite/
├── app.py                  ← Flask app factory
├── config.py               ← Configuration
├── models.py               ← SQLAlchemy models
├── schemas.py              ← Pydantic validation schemas
├── api/                    ← REST API blueprints
│   ├── accounts.py
│   ├── transactions.py
│   ├── equity.py
│   ├── projection.py
│   └── settings.py
├── pages/                  ← Page routes (Jinja2)
│   └── routes.py
├── importer/               ← File import: readers, rules, AI tools, review pipeline
├── engine/                 ← Business logic
│   ├── projection.py       ← Core projection engine
│   ├── recurrence.py       ← Recurring date expansion
│   ├── vest_builder.py     ← RSU vest schedule
│   ├── espp.py             ← ESPP calculations
│   └── amortization.py     ← Loan amortization
├── templates/              ← Jinja2 templates
├── static/                 ← CSS and JavaScript
├── migrations/             ← Alembic database migrations
├── tests/                  ← Unit and integration tests
├── instance/               ← Runtime data (git-ignored)
│   └── finance.db          ← SQLite database
└── requirements.txt        ← Python dependencies
```

## Data Format

- **Monetary amounts**: Stored as integers in minor units (cents for USD)
  - Example: $1,234.56 → 123456
- **Dates**: ISO 8601 strings (YYYY-MM-DD)
- **IDs**: 21-character nanoids

## Technical Stack

- **Web Framework**: Flask 3.x
- **ORM**: Flask-SQLAlchemy 3.x
- **Database**: SQLite 3
- **Validation**: Pydantic v2
- **Templating**: Jinja2
- **Frontend**: Alpine.js 3 and Chart.js 4 (pinned copies in `static/vendor/`), Tailwind CSS 3 compiled
  ahead of time into `static/build/tailwind.css`; no CDN at run time
- **Installable app**: web manifest, service worker (`/sw.js`) and offline page in `pages/pwa.py`
- **Testing**: pytest + pytest-flask

## Security Notes

- **No authentication**: Single-user, localhost only (v1)
- **Data locality**: All data stays on your device; no cloud sync
- **SQL injection prevention**: SQLAlchemy parameterized queries
- **XSS prevention**: Jinja2 auto-escaping
- **CSRF protection**: Flask-WTF tokens on state-changing requests

## Development

### Run Tests

```bash
pytest --cov=. --cov-report=term-missing
```

### Rebuild the stylesheet

Tailwind classes are compiled into `static/build/tailwind.css`, which is committed so running the app
never needs Node.js. After adding or changing class names in `templates/` or `static/*.js`:

```bash
python scripts/build_css.py          # needs Node.js; add --watch while editing
```

### Redraw the app icon

```bash
python scripts/make_icons.py         # writes every size to static/icons/
```

Static files are served with a `?v=` version taken from their sizes and dates, and the service worker
carries the same version, so installed copies pick up changes on their own.

### Run with Debugger

```bash
export FLASK_ENV=development
export FLASK_DEBUG=1
flask run
```

### Database Migrations

```bash
flask db migrate -m "Add new column"
flask db upgrade
```

## Troubleshooting

### "database is locked"

SQLite uses file-level locking. This can happen if:
- Multiple processes are accessing the database simultaneously
- A transaction was not properly committed

Solution: Restart the Flask server.

### "ModuleNotFoundError"

Ensure your virtual environment is activated:

```bash
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
pip install -r requirements.txt
```

### Database file not created

Run migrations first:

```bash
flask db upgrade
```

## Limitations (v1)

- Single-user, no multi-user support
- No automatic bank/brokerage data pulls (manual entry, or drop exported files on the Import page)
- Import doesn't convert currencies; amounts are taken in the app's currency
- HEIC photos and old .xls files aren't read; export as JPEG or .xlsx/.csv
- No password protection for local web server
- SQLite limits concurrent writes (works for personal use)
- Tax figures are planning estimates: no credits, AMT, income phase-outs or state-specific rules, and no filing

## Future Roadmap

- Optional password protection
- Stock price API feeds
- Multi-workspace support
- Optional cloud sync (Dropbox, iCloud)
- PWA "install as app" support

## License

Personal use only.

## Support

For issues, questions, or feature requests, refer to the Software Requirements Document (SRD.md) and Product Requirements Document (PRD.md) in the docs/ folder.
