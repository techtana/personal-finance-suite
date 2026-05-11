# Personal Finance Suite

A self-hosted Flask web application for personal financial planning. Track income, expenses, equity compensation, and project your net worth over time—all stored locally on your device.

## Features

- **Dashboard**: Net worth summary, monthly cash flow, upcoming events
- **Transactions**: One-time and recurring income/expenses
- **Equity Compensation**: RSU grants and ESPP plans with automatic calculations
- **Accounts & Loans**: Track all financial accounts and liabilities
- **Timeline & Projections**: Month-by-month cash flow and net worth forecasts
- **Settings**: Configure categories, divergence thresholds, and more
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

### Projection

- `GET /api/projection?from=2026-05-10&to=2027-05-10` — Run projection
- `GET /api/projection/month/2026-05` — Drill-down for a month

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
- No automatic bank/brokerage data pulls (manual entry only)
- No password protection for local web server
- SQLite limits concurrent writes (works for personal use)
- No tax optimization or filing features

## Future Roadmap

- Optional password protection
- Stock price API feeds
- CSV bulk import
- Multi-workspace support
- Optional cloud sync (Dropbox, iCloud)
- PWA "install as app" support

## License

Personal use only.

## Support

For issues, questions, or feature requests, refer to the Software Requirements Document (SRD.md) and Product Requirements Document (PRD.md) in the docs/ folder.
