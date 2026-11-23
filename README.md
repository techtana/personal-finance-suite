# Personal Finance Suite

A self-hosted Flask web application for personal financial planning. Track income, expenses, equity compensation, and project your net worth over time—all stored locally on your device.

## Features

- **Dashboard**: Net worth summary, monthly cash flow, upcoming events
- **Transactions**: One-time and recurring income/expenses
- **Equity Compensation**: RSU grants and ESPP plans with automatic calculations
- **Accounts & Loans**: Track all financial accounts and liabilities
- **Timeline & Projections**: Month-by-month cash flow and net worth forecasts
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

### 5. Load Sample Data (Optional)

```bash
flask shell
>>> from app import create_app, db
>>> from api.settings import seed_sample_data
>>> app = create_app()
>>> with app.app_context():
...     seed_sample_data()
```

Or call the API endpoint:

```bash
curl -X POST http://localhost:5000/api/seed
```

### 6. Run the App

```bash
flask run
```

Open http://localhost:5000 in your browser.

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
| Statement or export | one Cash Flow entry (`ChangeEvent`, type `imported`) per transaction; the closing balance as an account balance snapshot; regular payments (same merchant, steady amount and gap) as *suggested* recurring rules, off until you tick them |
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

## Database Backup

The SQLite database file is located at `instance/finance.db`. Back it up by:

1. **Manual copy**: `cp instance/finance.db instance/finance.backup.$(date +%Y%m%d).db`
2. **Export from app**: Go to Settings → Export JSON

## API Endpoints

### Accounts & Loans

- `GET /api/accounts` — List accounts
- `POST /api/accounts` — Create account
- `PATCH /api/accounts/<id>` — Update account
- `GET /api/loans` — List loans
- `POST /api/loans` — Create loan
- `GET /api/accounts/<id>/snapshots` — Reconciliation history

### Transactions

- `GET /api/transactions/one-time` — List one-time transactions
- `POST /api/transactions/one-time` — Create
- `GET /api/transactions/recurring` — List recurring transactions
- `GET /api/blanket-expenses` — List blanket expenses

### Equity

- `GET /api/equity/rsu` — List RSU grants
- `POST /api/equity/rsu` — Create RSU grant
- `GET /api/equity/espp` — List ESPP plans
- `POST /api/equity/espp` — Create ESPP plan

### Import

- `POST /api/imports` — Upload files (multipart `files`, optional `account_id`, `doc_type`)
- `GET /api/imports`, `GET /api/imports/<id>` — List; one import with its rows
- `PATCH /api/imports/<id>` — Change account; or re-read with `doc_type`, `mapping`, `flip_signs`
- `PATCH /api/imports/<id>/rows/<row_id>` — Edit a row (action, date, amount, description, category)
- `POST /api/imports/<id>/commit`, `POST /api/imports/<id>/undo`, `DELETE /api/imports/<id>`
- `GET /api/imports/ai-status` — Is the local AI reachable

### Projection

- `GET /api/projection?from=2026-05-10&to=2027-05-10` — Run projection (one-time changes count only inside the
  range; balances already include past ones)
- `GET /api/projection/month/2026-05` — Drill-down for a month

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
- `POST /api/seed` — Load sample data

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
- **Frontend**: htmx + Alpine.js (minimal, no build step)
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
