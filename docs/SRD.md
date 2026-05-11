# Software Requirements Document
## Personal Finance Suite

**Version:** 0.2  
**Date:** 2026-05-09  
**Status:** Draft  
**Changed from v0.1:** Replaced React SPA + Google Drive with Flask + SQLite. Removed OAuth/Drive integration. Updated stack, architecture, API, deployment.

---

## 1. System Overview

Personal Finance Suite is a **Flask web application** running on localhost. The Flask server handles all business logic, serves Jinja2-rendered pages, and exposes a REST JSON API consumed by lightweight frontend JavaScript. All data is persisted in a **local SQLite database**.

```
┌──────────────────────────────────────────────────────────┐
│                    Browser (localhost)                    │
│                                                          │
│  ┌─────────────────────────────────────────────────────┐ │
│  │  Jinja2 Pages + Vanilla JS / htmx                  │ │
│  └─────────────────────────────────────────────────────┘ │
└────────────────────────────┬─────────────────────────────┘
                             │ HTTP (localhost)
┌────────────────────────────▼─────────────────────────────┐
│                    Flask App (Python)                     │
│                                                          │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────────┐  │
│  │  Page Routes  │  │  REST API    │  │  Projection   │  │
│  │  (Jinja2)    │  │  /api/*      │  │  Engine       │  │
│  └──────────────┘  └──────────────┘  └───────────────┘  │
│                             │                            │
│                    ┌────────▼────────┐                   │
│                    │  SQLAlchemy ORM │                   │
│                    └────────┬────────┘                   │
│                             │                            │
│                    ┌────────▼────────┐                   │
│                    │   SQLite DB     │                   │
│                    │  (finance.db)   │                   │
│                    └─────────────────┘                   │
└──────────────────────────────────────────────────────────┘
```

No cloud services. No OAuth. No build step. Start with `flask run`, open `http://localhost:5000`.

---

## 2. Technology Stack

| Layer | Choice | Rationale |
|-------|--------|-----------|
| Web framework | Flask 3.x (Python) | Lightweight, no boilerplate, easy to run locally |
| ORM | Flask-SQLAlchemy 3.x | Declarative models, SQLite-native, migrations support |
| Migrations | Flask-Migrate (Alembic) | Schema versioning without manual SQL |
| Database | SQLite 3 | Zero-config, single file, sufficient for personal use |
| Templating | Jinja2 (bundled with Flask) | Server-rendered HTML, no JS build toolchain |
| Frontend interactivity | htmx + Alpine.js (CDN) | Lightweight; handles form submissions, modals, live updates without a build step |
| Charts | Chart.js 4.x (CDN) | Canvas-based; works with server-rendered data |
| Inline sparklines | Inline SVG (server-rendered) | No JS dependency; pre-computed in Python |
| Date math | Python `datetime` + `dateutil` | stdlib-first, `dateutil` for recurrence rules |
| Validation | Pydantic v2 | Schema-first validation shared between API and business logic |
| Serialization | `marshmallow` (for API responses) | Clean JSON serialization layer |
| Testing | `pytest` + `pytest-flask` | Standard Python testing stack |

No Node.js. No npm. No build step. No OAuth library. No CDN for data.

---

## 3. Data Architecture

### 3.1 Database File

The SQLite database is stored at `{APP_DATA_DIR}/finance.db`. `APP_DATA_DIR` defaults to `./instance/` (Flask's default instance folder), configurable via environment variable `FINANCE_DB_PATH`.

### 3.2 Schema Overview

```
accounts            ← bank, brokerage, retirement, property accounts
loans               ← mortgage, auto, student, HELOC liabilities
one_time_txns       ← single income/expense events
recurring_txns      ← repeating income/expense events
blanket_expenses    ← catch-all spending buckets
rsu_grants          ← equity grants with vest schedules (JSON column)
espp_plans          ← ESPP offering periods (purchase_periods as JSON)
account_snapshots   ← reconciliation history per account
categories          ← user-defined income/expense categories
settings            ← single-row app configuration
```

### 3.3 Schema Versioning

A `schema_version` integer is stored in the `settings` table. On each app start, Flask compares the stored version against the application's current version constant. If older, Alembic migrations run automatically. Migrations are numbered and append-only.

---

## 4. Data Models

All monetary amounts are stored as **integers in the minor unit of the user's currency** (cents for USD). The template layer converts for display.

All dates are stored as **ISO 8601 date strings** (`"YYYY-MM-DD"`). SQLite stores them as TEXT; Python compares them as strings (lexicographic order matches chronological order for ISO dates).

### 4.1 Common Columns

Every table has:
```
id          TEXT PRIMARY KEY    -- nanoid(), 21 chars
created_at  TEXT NOT NULL       -- ISO date
updated_at  TEXT NOT NULL       -- ISO date
note        TEXT                -- nullable free-text annotation
```

### 4.2 accounts

```sql
CREATE TABLE accounts (
  id                TEXT PRIMARY KEY,
  name              TEXT NOT NULL,
  type              TEXT NOT NULL,  -- see AccountType enum
  institution       TEXT NOT NULL,
  currency          TEXT NOT NULL DEFAULT 'USD',
  current_balance   INTEGER NOT NULL DEFAULT 0,  -- minor units
  last_updated_date TEXT NOT NULL,
  linked_loan_id    TEXT REFERENCES loans(id),
  is_active         INTEGER NOT NULL DEFAULT 1,  -- boolean
  note              TEXT,
  created_at        TEXT NOT NULL,
  updated_at        TEXT NOT NULL
);
```

`type` values: `checking`, `savings`, `brokerage`, `retirement_401k`, `retirement_ira`, `retirement_roth`, `hsa`, `crypto`, `property`, `other_asset`

### 4.3 loans

```sql
CREATE TABLE loans (
  id               TEXT PRIMARY KEY,
  name             TEXT NOT NULL,
  type             TEXT NOT NULL,  -- mortgage|auto|student|personal|heloc|other
  institution      TEXT NOT NULL,
  original_balance INTEGER NOT NULL,   -- minor units
  current_balance  INTEGER NOT NULL,   -- minor units; updated manually
  interest_rate    INTEGER NOT NULL,   -- annual rate × 10000 (e.g., 6.5% = 65000)
  monthly_payment  INTEGER NOT NULL,   -- minor units
  start_date       TEXT NOT NULL,
  payoff_date      TEXT NOT NULL,
  last_updated_date TEXT NOT NULL,
  linked_account_id TEXT REFERENCES accounts(id),
  note             TEXT,
  created_at       TEXT NOT NULL,
  updated_at       TEXT NOT NULL
);
```

### 4.4 one_time_txns

```sql
CREATE TABLE one_time_txns (
  id          TEXT PRIMARY KEY,
  type        TEXT NOT NULL,     -- 'income' | 'expense'
  amount      INTEGER NOT NULL,  -- minor units, always positive
  date        TEXT NOT NULL,
  category    TEXT NOT NULL REFERENCES categories(slug),
  account_id  TEXT NOT NULL REFERENCES accounts(id),
  note        TEXT,
  created_at  TEXT NOT NULL,
  updated_at  TEXT NOT NULL
);
```

### 4.5 recurring_txns

```sql
CREATE TABLE recurring_txns (
  id          TEXT PRIMARY KEY,
  type        TEXT NOT NULL,     -- 'income' | 'expense'
  amount      INTEGER NOT NULL,
  frequency   TEXT NOT NULL,     -- daily|weekly|biweekly|monthly|quarterly|annually
  start_date  TEXT NOT NULL,
  end_date    TEXT,              -- NULL = indefinite
  category    TEXT NOT NULL REFERENCES categories(slug),
  account_id  TEXT NOT NULL REFERENCES accounts(id),
  note        TEXT,
  created_at  TEXT NOT NULL,
  updated_at  TEXT NOT NULL
);
```

### 4.6 blanket_expenses

```sql
CREATE TABLE blanket_expenses (
  id          TEXT PRIMARY KEY,
  label       TEXT NOT NULL,
  amount      INTEGER NOT NULL,  -- per-period, minor units
  frequency   TEXT NOT NULL,
  start_date  TEXT NOT NULL,
  end_date    TEXT,
  category    TEXT NOT NULL REFERENCES categories(slug),
  note        TEXT,
  created_at  TEXT NOT NULL,
  updated_at  TEXT NOT NULL
);
```

### 4.7 rsu_grants

```sql
CREATE TABLE rsu_grants (
  id               TEXT PRIMARY KEY,
  label            TEXT NOT NULL,
  grant_date       TEXT NOT NULL,
  total_shares     INTEGER NOT NULL,  -- milliShares (× 1000)
  ticker           TEXT NOT NULL,
  price_at_grant   INTEGER,           -- minor units, optional
  vest_schedule    TEXT NOT NULL,     -- JSON: [{date, shares}, ...]
  withholding_rate INTEGER NOT NULL,  -- percent × 100, e.g., 2200 = 22%
  account_id       TEXT NOT NULL REFERENCES accounts(id),
  note             TEXT,
  created_at       TEXT NOT NULL,
  updated_at       TEXT NOT NULL
);
```

`vest_schedule` is stored as a JSON string. The vest schedule builder (Python function) accepts cliff/subsequent parameters and outputs the explicit `[{date, shares}]` list before save — future builder logic changes do not silently alter existing grants.

**Vest Schedule Builder inputs (used during create/edit only, not stored):**
```python
cliffMonths:           int
cliffPercent:          int   # percent × 100
subsequentFrequency:   str   # 'monthly' | 'quarterly'
subsequentPercent:     int   # percent × 100 per period
```
Builder validates cliff + all subsequent periods sum to exactly 100%.

### 4.8 espp_plans

```sql
CREATE TABLE espp_plans (
  id                  TEXT PRIMARY KEY,
  label               TEXT NOT NULL,
  offering_start_date TEXT NOT NULL,
  offering_end_date   TEXT NOT NULL,
  contribution_mode   TEXT NOT NULL,   -- 'percent' | 'fixed'
  contribution_value  INTEGER NOT NULL,
  base_salary         INTEGER,         -- minor units/yr; required if mode = 'percent'
  discount_rate       INTEGER NOT NULL DEFAULT 1500,  -- percent × 100
  has_lookback        INTEGER NOT NULL DEFAULT 1,     -- boolean
  purchase_periods    TEXT NOT NULL,   -- JSON: [{start_date, end_date, estimated_purchase_amount}]
  account_id          TEXT NOT NULL REFERENCES accounts(id),
  note                TEXT,
  created_at          TEXT NOT NULL,
  updated_at          TEXT NOT NULL
);
```

### 4.9 account_snapshots

```sql
CREATE TABLE account_snapshots (
  id                         TEXT PRIMARY KEY,
  account_id                 TEXT NOT NULL REFERENCES accounts(id),
  date                       TEXT NOT NULL,
  actual_balance             INTEGER NOT NULL,   -- minor units
  predicted_balance          INTEGER NOT NULL,   -- minor units; computed at snapshot time
  delta                      INTEGER NOT NULL,   -- actual - predicted
  resolution                 TEXT NOT NULL,      -- 'accepted' | 'adjusted' | 'ignored'
  adjustment_transaction_id  TEXT REFERENCES one_time_txns(id),
  note                       TEXT,
  created_at                 TEXT NOT NULL
);
```

### 4.10 categories

```sql
CREATE TABLE categories (
  slug        TEXT PRIMARY KEY,   -- kebab-case, foreign key used across tables
  label       TEXT NOT NULL,
  type        TEXT NOT NULL,      -- 'income' | 'expense' | 'both'
  color       TEXT NOT NULL       -- hex, e.g., '#3b82f6'
);
```

### 4.11 settings

```sql
CREATE TABLE settings (
  id                      INTEGER PRIMARY KEY DEFAULT 1,  -- single row
  currency                TEXT NOT NULL DEFAULT 'USD',
  locale                  TEXT NOT NULL DEFAULT 'en-US',
  fiscal_year_start_month INTEGER NOT NULL DEFAULT 1,     -- 1–12
  default_withholding_rate INTEGER NOT NULL DEFAULT 2200, -- percent × 100
  divergence_thresholds   TEXT NOT NULL,  -- JSON: {account_type: percent×100, ...}
  schema_version          INTEGER NOT NULL DEFAULT 1
);
```

---

## 5. Projection Engine

The projection engine is a **pure Python function** with no side effects and no database access. It is called by API endpoints and passes its output to templates/JSON responses.

```python
def project(inputs: ProjectionInputs, from_date: str, to_date: str) -> ProjectionResult:
    ...
```

### 5.1 ProjectionInputs (Pydantic model)

```python
class ProjectionInputs(BaseModel):
    transactions:      list[OneTimeTxn | RecurringTxn]
    blanket_expenses:  list[BlanketExpense]
    rsu_grants:        list[RSUGrant]
    espp_plans:        list[ESPPPlan]
    accounts:          list[Account]
    loans:             list[Loan]
    stock_prices:      dict[str, int]   # ticker → minor units per share
    disabled_ids:      set[str] = set() # scenario mode: filter out these source IDs
```

### 5.2 Algorithm

1. **Expand all recurring objects** into a flat `list[CashFlowEvent]` over `[from_date, to_date]`:
   - `RecurringTxn`: one event per occurrence date (see §9.4 for date rules)
   - `BlanketExpense`: one event per period
   - `RSUGrant`: one event per `VestEvent` (gross and net-of-withholding variants)
   - `ESPPPlan`: one event per purchase period end date
   - `Loan`: one event per monthly payment
2. **Filter** events whose `source_id` is in `disabled_ids` (scenario mode).
3. **Sort events by date.**
4. **Bucket by month.** For each `YYYY-MM`, sum `income` events and `expense` events.
5. **Carry-forward balance.** Starting from `sum(account.current_balance) − sum(loan.current_balance)`, add each month's net cash flow to produce projected net worth.
6. **Attach actuals.** For months where an `AccountSnapshot` exists, attach `actual_net_worth`.
7. **Return** `MonthlyBucket[]` (for timeline table) and `CashFlowEvent[]` (for drill-down and waterfall chart).

```python
@dataclass
class CashFlowEvent:
    date:        str
    source_id:   str
    source_type: str   # 'transaction'|'recurring'|'blanket'|'rsu'|'espp'|'loan_payment'
    type:        str   # 'income' | 'expense'
    amount:      int
    label:       str
    category:    str

@dataclass
class MonthlyBucket:
    month:                str   # "YYYY-MM"
    income:               int
    expenses:             int
    net_cash_flow:        int
    cumulative_net_worth: int   # predicted
    actual_net_worth:     int | None
    events:               list[CashFlowEvent]
```

### 5.3 Scenario Mode

Pass `disabled_ids` as a set of object IDs to exclude from projection. The API `/api/projection?scenario=custom&disabled=id1,id2` accepts a comma-separated disabled list. The timeline page overlays the scenario line on the baseline chart in a distinct color.

---

## 6. REST API Endpoints

All endpoints are under `/api/`. Request and response bodies are JSON. Errors return `{"error": "message"}` with appropriate HTTP status.

### 6.1 Accounts & Loans

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/accounts` | List all active accounts |
| POST | `/api/accounts` | Create account |
| GET | `/api/accounts/<id>` | Get account |
| PATCH | `/api/accounts/<id>` | Update account fields |
| DELETE | `/api/accounts/<id>` | Soft-delete (set `is_active = false`) |
| GET | `/api/loans` | List all loans |
| POST | `/api/loans` | Create loan |
| PATCH | `/api/loans/<id>` | Update loan |
| DELETE | `/api/loans/<id>` | Delete loan |
| POST | `/api/accounts/<id>/snapshots` | Record a reconciliation snapshot |
| GET | `/api/accounts/<id>/snapshots` | List snapshot history |

### 6.2 Transactions

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/transactions/one-time` | List one-time transactions (filter: `?from=&to=&category=&account=`) |
| POST | `/api/transactions/one-time` | Create |
| PATCH | `/api/transactions/one-time/<id>` | Update |
| DELETE | `/api/transactions/one-time/<id>` | Delete |
| GET | `/api/transactions/recurring` | List recurring transactions |
| POST | `/api/transactions/recurring` | Create |
| PATCH | `/api/transactions/recurring/<id>` | Update |
| DELETE | `/api/transactions/recurring/<id>` | Delete |
| GET | `/api/blanket-expenses` | List blanket expenses |
| POST | `/api/blanket-expenses` | Create |
| PATCH | `/api/blanket-expenses/<id>` | Update |
| DELETE | `/api/blanket-expenses/<id>` | Delete |

### 6.3 Equity

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/equity/rsu` | List RSU grants |
| POST | `/api/equity/rsu` | Create grant (vest schedule built server-side) |
| PATCH | `/api/equity/rsu/<id>` | Update grant |
| DELETE | `/api/equity/rsu/<id>` | Delete grant |
| POST | `/api/equity/rsu/preview-schedule` | Preview vest schedule from builder inputs (no save) |
| GET | `/api/equity/espp` | List ESPP plans |
| POST | `/api/equity/espp` | Create plan |
| PATCH | `/api/equity/espp/<id>` | Update plan |
| DELETE | `/api/equity/espp/<id>` | Delete plan |

### 6.4 Projection

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/projection` | Run projection (`?from=YYYY-MM-DD&to=YYYY-MM-DD&disabled=id1,id2`) |
| GET | `/api/projection/month/<YYYY-MM>` | Get drill-down events for a specific month |

### 6.5 Settings & Data Management

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/settings` | Get current settings |
| PATCH | `/api/settings` | Update settings |
| GET | `/api/categories` | List categories |
| POST | `/api/categories` | Create category |
| PATCH | `/api/categories/<slug>` | Update category |
| DELETE | `/api/categories/<slug>` | Delete category (validate no FK references first) |
| GET | `/api/export` | Download full database as JSON |
| POST | `/api/import` | Restore from JSON export (replaces all data) |
| POST | `/api/seed` | Load sample dataset (dev/demo only) |

---

## 7. Flask Route Structure (Page Routes)

Page routes render Jinja2 templates. Data is passed as template context, computed server-side. JavaScript fetches only incremental updates via the API.

```
/                   → dashboard (redirect to /dashboard)
/dashboard          → Dashboard template (F1)
/transactions       → Transactions list template (F2)
/equity             → Equity Comp template (F3)
/accounts           → Accounts & Net Worth template (F4)
/loans              → Loans template (within Accounts section)
/timeline           → Timeline & Projections template (F5)
/settings           → Settings template (F8)
```

Drawers/modals are rendered as partial templates fetched via htmx (`hx-get`) or pre-embedded in the page and toggled with Alpine.js.

---

## 8. Python Module Structure

```
personal-finance-suite/
├── app.py                  ← Flask app factory, config
├── config.py               ← Config classes (dev/prod/test)
├── models.py               ← SQLAlchemy ORM models (all tables)
├── api/
│   ├── __init__.py
│   ├── accounts.py         ← /api/accounts, /api/loans, /api/accounts/<id>/snapshots
│   ├── transactions.py     ← /api/transactions/*, /api/blanket-expenses
│   ├── equity.py           ← /api/equity/rsu, /api/equity/espp
│   ├── projection.py       ← /api/projection
│   └── settings.py         ← /api/settings, /api/categories, /api/export, /api/import
├── pages/
│   ├── __init__.py
│   └── routes.py           ← Page routes (GET /dashboard etc.)
├── engine/
│   ├── __init__.py
│   ├── projection.py       ← Pure projection function
│   ├── vest_builder.py     ← RSU vest schedule builder
│   ├── espp.py             ← ESPP calculation helpers
│   ├── amortization.py     ← Loan amortization math
│   └── recurrence.py       ← Recurring date expansion
├── schemas.py              ← Pydantic models for API validation
├── templates/
│   ├── base.html           ← Layout with sidebar
│   ├── dashboard.html
│   ├── transactions.html
│   ├── equity.html
│   ├── accounts.html
│   ├── loans.html
│   ├── timeline.html
│   ├── settings.html
│   └── partials/           ← htmx partial templates (drawers, modals, rows)
├── static/
│   ├── wf.css              ← Main stylesheet (from wireframes)
│   └── app.js              ← Minimal JS (Alpine.js init, chart setup)
├── migrations/             ← Alembic migration files
├── tests/
│   ├── test_projection.py
│   ├── test_vest_builder.py
│   ├── test_espp.py
│   ├── test_amortization.py
│   └── test_api.py
├── instance/
│   └── finance.db          ← SQLite database (gitignored)
├── requirements.txt
└── README.md
```

---

## 9. Calculation Rules

### 9.1 RSU Net Value

```python
gross_value   = (shares / 1000) * stock_price_per_share   # shares in milliShares
tax_withheld  = gross_value * (withholding_rate / 10000)
net_proceeds  = gross_value - tax_withheld
```

The UI shows both gross and net. Net proceeds flow into projected cash flow for the linked account.

### 9.2 ESPP Purchase Price

```python
base_price      = min(price_at_period_start, price_at_purchase) if has_lookback \
                  else price_at_purchase
purchase_price  = base_price * (1 - discount_rate / 10000)

if contribution_mode == 'percent':
    periods_in_offering    = len(purchase_periods)
    contribution_per_period = (base_salary / 12) * (contribution_value / 10000)
    contribution_total     = contribution_per_period * periods_in_offering
else:
    contribution_total = contribution_value * len(purchase_periods)

shares_purchased  = contribution_total / purchase_price   # display only; stored as milliShares
immediate_gain    = contribution_total * (discount_rate / 10000)
```

### 9.3 Loan Amortization

Standard amortization formula for monthly payment and payoff date computation:

```python
monthly_rate     = (interest_rate / 10000) / 12
payment          = balance * monthly_rate / (1 - (1 + monthly_rate) ** -remaining_months)
```

If `payoff_date` is provided by the user, it is stored as-is. If not, it is computed from amortization starting from `start_date` and `original_balance`.

### 9.4 Recurring Transaction Occurrence Dates

Given `start_date`, `end_date` (optional), `frequency`:
- `daily`: every calendar day
- `weekly`: same weekday as `start_date`
- `biweekly`: every 14 days from `start_date`
- `monthly`: same day-of-month as `start_date` (clamped to last day of month for short months)
- `quarterly`: 3-month intervals from `start_date`
- `annually`: same month + day each year

All occurrence dates within the projection window are returned as a list of ISO date strings.

---

## 10. Security Requirements

| Requirement | Implementation |
|-------------|---------------|
| Data stays local | No network calls except localhost; no telemetry; no CDN for data |
| No authentication (v1) | Single-user, localhost-only; bind to `127.0.0.1` in production mode |
| SQL injection prevention | SQLAlchemy parameterized queries; no raw string interpolation in SQL |
| XSS prevention | Jinja2 auto-escaping on all template variables; `Content-Security-Policy` header |
| CSRF protection | `Flask-WTF` CSRF token on all state-changing form submissions |
| Import validation | JSON import validated against Pydantic schemas before writing to DB; reject unknown keys |
| Debug mode off | `FLASK_DEBUG=0` in production; debug mode must never be on when binding to non-loopback addresses |

---

## 11. Performance Requirements

| Scenario | Target |
|----------|--------|
| App startup (`flask run` to first response) | < 3 s |
| Page load (server-rendered, SQLite read) | < 300 ms |
| Projection re-compute (5-yr horizon, ~500 events) | < 150 ms in Python |
| Dashboard render including projection | < 500 ms total |
| Database file size at 5 years of data | < 10 MB |

The projection engine runs synchronously in the request cycle in v1. If benchmarks exceed 500 ms on a 10-year horizon, move computation to a background thread with a cached result.

---

## 12. Error Handling

| Error Type | Behavior |
|------------|----------|
| API validation error | 422 with `{"error": "...", "fields": {...}}` |
| Database constraint violation | 409 Conflict with descriptive message |
| Object not found | 404 with `{"error": "not found"}` |
| Projection math error (e.g., division by zero in amortization) | 400 with explanation; log to stderr |
| JSON import parse failure | 400 with `{"error": "invalid JSON"}` before any DB write |
| Import schema mismatch | 422 with list of failed fields; DB unchanged (transaction rollback) |
| Unhandled exception | 500; stack trace logged to stderr; generic error page shown to user |

All API errors are logged to stderr (structured log line with method, path, status, duration).

---

## 13. Testing Requirements

| Layer | Tool | Coverage target |
|-------|------|-----------------|
| Projection engine (`engine/projection.py`) | pytest | 90% branch coverage |
| Vest schedule builder (`engine/vest_builder.py`) | pytest | 100% (finite rule set) |
| ESPP calculations (`engine/espp.py`) | pytest | 100% |
| Amortization (`engine/amortization.py`) | pytest | 90% |
| Recurrence date expansion (`engine/recurrence.py`) | pytest | 90% |
| REST API endpoints | pytest-flask | Happy path + validation errors for each resource |
| Import/export round-trip | pytest | Full export → import → re-export; assert equality |

Run with: `pytest --cov=. --cov-report=term-missing`

---

## 14. Deployment

### Local Development

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
flask db upgrade                 # apply migrations, creates finance.db
flask run                        # http://localhost:5000
```

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `FLASK_ENV` | `development` | `production` disables debug mode |
| `FINANCE_DB_PATH` | `instance/finance.db` | Path to SQLite database file |
| `SECRET_KEY` | (required) | Flask session secret; generate with `python -c "import secrets; print(secrets.token_hex())"` |

### Database Backup

```bash
# Manual backup
cp instance/finance.db instance/finance.backup.$(date +%Y%m%d).db

# Or use the in-app Export button (Settings → Export JSON)
```

### `requirements.txt` (key packages)

```
flask>=3.0
flask-sqlalchemy>=3.1
flask-migrate>=4.0
pydantic>=2.0
python-dateutil>=2.9
nanoid>=2.0
pytest>=8.0
pytest-flask>=1.3
pytest-cov>=5.0
```

---

## 15. Future Considerations (Not in v1 Scope)

- Optional password protection for the local web server (single password, no user accounts)
- Stock price feed via free API (Yahoo Finance or similar) to auto-populate ticker prices
- PWA manifest for "install as app" on desktop
- CSV bulk import for historical transaction data
- Multi-workspace support (multiple SQLite databases, workspace switcher in UI)
- Optional cloud sync via rsync/Dropbox/iCloud folder (user-managed, not app-managed)
- Read-only advisor view (export static HTML snapshot of dashboard)
- 401k contribution limit tracking and warnings
