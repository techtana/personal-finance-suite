# Quick Start Guide

## Get the Flask App Running in 5 Minutes

### Prerequisites
- Python 3.9+
- A terminal/command prompt
- A web browser

### Step 1: Set Up Virtual Environment

```bash
cd personal-finance-suite

# Create virtual environment
python -m venv .venv

# Activate it
# On macOS/Linux:
source .venv/bin/activate

# On Windows:
.venv\Scripts\activate
```

### Step 2: Install Dependencies

```bash
pip install -r requirements.txt
```

### Step 3: Initialize Database

```bash
flask db upgrade
```

This creates the SQLite database at `instance/finance.db` with all 11 tables.

### Step 4: Load Sample Data (Optional)

```bash
# Option A: Via API (while app is running)
curl -X POST http://localhost:5000/api/seed

# Option B: Via Flask shell
flask shell
>>> from api.settings import seed_sample_data
>>> from app import create_app
>>> app = create_app()
>>> with app.app_context():
...     seed_sample_data()
>>> exit()
```

### Step 5: Run the App

```bash
flask run
```

You should see:
```
 * Running on http://127.0.0.1:5000
```

### Step 6: Open in Browser

Go to **http://localhost:5000** and start exploring!

---

## What You Can Do Right Away

### If You Loaded Sample Data:
1. **Dashboard**: See net worth cards, monthly cash flow, and upcoming events
2. **Transactions**: Browse the sample monthly salary transaction
3. **Timeline**: View the 5-year projection (with sample salary data)
4. **Settings**: Export data as JSON or load a fresh sample dataset

### Via API (Use curl or Postman):

**List all accounts:**
```bash
curl http://localhost:5000/api/accounts
```

**Get projection:**
```bash
curl "http://localhost:5000/api/projection?from=2026-05-10&to=2027-05-10"
```

**List categories:**
```bash
curl http://localhost:5000/api/categories
```

**Create a one-time transaction:**
```bash
curl -X POST http://localhost:5000/api/transactions/one-time \
  -H "Content-Type: application/json" \
  -d '{
    "type": "income",
    "amount": 50000,
    "date": "2026-05-15",
    "category": "bonus",
    "account_id": "<account_id_from_/api/accounts>",
    "note": "Sign-on bonus"
  }'
```

---

## Common Next Steps

### Add Your Own Data

1. Go to **Settings** → **Load Sample Data** to clear existing data first
2. Go to **Accounts** → **Add Account** and add your bank accounts
3. Go to **Transactions** → **Add Transaction** for your income/expenses
4. Go to **Timeline** to see your 5-year projection

### Export/Backup Data

```bash
curl http://localhost:5000/api/export > my_backup.json
```

### Test the Projection Engine

```bash
curl "http://localhost:5000/api/projection?from=2026-05-10&to=2026-06-10"
```

This shows monthly buckets with income, expenses, net cash flow, and cumulative net worth.

### Use Scenario Mode

```bash
curl "http://localhost:5000/api/projection?from=2026-05-10&to=2027-05-10&disabled=id1,id2"
```

Replace `id1,id2` with transaction IDs to exclude them from the projection (what-if analysis).

---

## Troubleshooting

### "pydantic-core" build error on Windows
If you see `CalledProcessError` or `Rust not found`, this is a known Windows issue with binary compilation.

**Solution**: The requirements.txt now uses `--only-binary :all: pydantic-core` to use pre-built wheels. If the error persists:

```bash
# Option 1: Clear pip cache and reinstall
pip cache purge
pip install -r requirements.txt

# Option 2: Use a specific pre-built version
pip install "pydantic==2.5.3" "pydantic-core==2.14.6"
```

If still failing, try upgrading pip first:
```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### "database is locked"
SQLite uses file-level locking. If you see this:
1. Stop the Flask server (`Ctrl+C`)
2. Wait a few seconds
3. Run `flask run` again

### "No module named 'flask_migrate'"
Reinstall dependencies:
```bash
pip install -r requirements.txt
```

### "No such table: accounts"
Database hasn't been initialized. Run:
```bash
flask db upgrade
```

### Port 5000 already in use
Run on a different port:
```bash
flask run --port 5001
```

Then visit http://localhost:5001

---

## Architecture Overview

The app is organized into clean layers:

```
Browser (Jinja2 Templates + Alpine.js)
    ↓
Flask Page Routes (/dashboard, /transactions, etc.)
    ↓
REST API Endpoints (/api/accounts, /api/projection, etc.)
    ↓
Engine Modules (projection, recurrence, vest_builder, espp, amortization)
    ↓
SQLAlchemy ORM
    ↓
SQLite Database (instance/finance.db)
```

All code is in Python—no build step, no Node.js, no additional tools needed.

---

## Documentation

- **README.md** - Full setup, API reference, security notes
- **BUILD_SUMMARY.md** - What was built, file structure, next steps
- **docs/PRD.md** - Product requirements (features, goals, personas)
- **docs/SRD.md** - Software requirements (architecture, database schema, calculations)
- **docs/wireframes-v3/** - UI mockups of all 7 pages

---

## Need Help?

1. Check **README.md** for detailed API reference
2. Review **docs/SRD.md** for architecture and data format
3. Try the **POST /api/seed** endpoint to load sample data
4. Use **GET /api/export** to download all data as JSON (for debugging)

---

**Status**: ✅ Ready to Use  
**Last Updated**: 2026-05-10
