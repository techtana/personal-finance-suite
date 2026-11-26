# REST API

Every page uses these endpoints. Money is in integer minor units (cents for USD), dates are ISO `YYYY-MM-DD`, ids are 21-character nanoids.

Lists that grow with years of history (one-off entries and imported transactions, import rows, an account's
ledger, the activity log) are filtered and paged on the server; pages ask for one screenful at a time.
`python -m scripts.load_bench` seeds ten years of data in a throwaway database and times every read the pages
make (`--db instance/load-demo.db` keeps it, for the `load-demo` preview).


## Accounts & Loans

- `GET /api/accounts` — List accounts
- `POST /api/accounts` — Create account
- `PATCH /api/accounts/<id>` — Update account
- `GET /api/loans` — List loans
- `POST /api/loans` — Create loan
- `GET /api/accounts/<id>/snapshots` — Reconciliation history

## Plan

- `GET /api/rules`, `POST /api/rules`, `PATCH /api/rules/<id>`, `DELETE /api/rules/<id>` — Recurring rules
  (`rule_type`: income, expense, rsu, espp)
- `GET /api/changes`, `POST /api/changes`, `PATCH /api/changes/<id>`, `DELETE /api/changes/<id>` — One-off entries
  and imported transactions. With `?limit` (at most 500) and `?offset` the answer is one page:
  `{items, matched, total, sum, offset, limit, options}`, where `options` holds each dropdown's choices
  (`&options=0` skips them). Filters: `q`, `source`, `category`, `account`, `when=past|planned`, `from`, `to`,
  `min`, `max` (dollars, on the absolute amount), `today`; sort with `sort=date|description|amount|source|category|account`
  and `dir`. Without `limit` it returns every matching entry as a plain list

## Balances

- `GET /api/balances` — Every cash account, asset and liability in one list, with totals and freshness
- `POST /api/balances/record` — Record a value (`entity_type` cash|asset|liability, `entity_id`, `value` in cents,
  optional `date`). For a cash account the answer's `check` compares it with the previous record plus the
  transactions since
- `GET /api/balances/<account_id>/ledger?limit=&offset=` — One account's recorded balances and transactions,
  newest first, with the running balance and the unexplained gap at each record
- `POST /api/balances/reconcile` — `{snapshot_id}`: log a record's unexplained gap as an adjustment entry
- `GET /api/net-worth/history?months=24&types=cash,asset` — Month-end values by type
- `GET /api/plan-vs-actual?months=4` — Planned vs. imported amounts per category and month
- `GET /api/assets`, `POST /api/assets`, `PATCH /api/assets/<id>` — Assets
- `GET /api/prices`, `POST /api/prices`, `DELETE /api/prices/<id>` — Share prices (`?ticker=`; `?count=1` answers
  just `{count}`)

## Insights

- `GET /api/insights` — Current observations: `{id, source, severity, title, detail, basis, action}`

## Assistant

- `GET /api/assistant/status` — Is the model reachable
- `POST /api/assistant/ask` — `{question}` → answer, the figures it is based on, and a link
- `POST /api/assistant/filter` — `{text, filters, sorts}` → filter values for a list
- `POST /api/assistant/explain` — `{title, detail, basis}` → plain-language wording
- `POST /api/assistant/draft` — `{text}` → a pre-filled Plan entry (nothing is saved)

## Import

- `POST /api/imports` — Upload files (multipart `files`, optional `account_id`, `doc_type`)
- `GET /api/imports`, `GET /api/imports/<id>` — List; one import with its rows (`?rows=0` leaves the rows out)
- `GET /api/imports/<id>/rows` — One page of rows: `filter`, `q` (search), `target`, `offset`, `limit` (at most 200)
- `PATCH /api/imports/<id>` — Change account; or re-read with `doc_type`, `mapping`, `flip_signs`
- `PATCH /api/imports/<id>/rows/<row_id>` — Edit a row (action, date, amount, description, category)
- `POST /api/imports/<id>/rows/bulk` — Change many rows: `ids`, or every row matching `filter` / `q` / `target`;
  `set` holds `action`, `category`, `account_id`, `date` or `flip_sign`
- `POST /api/imports/<id>/commit`, `POST /api/imports/<id>/undo`, `DELETE /api/imports/<id>`
- `GET /api/imports/ai-status` — Is the local AI reachable

## Projection

- `GET /api/projection?from=2026-05-10&to=2027-05-10` — Run projection (one-time changes count only inside the
  range; balances already include past ones). Add `&disable=<id>,<id>` to leave rules, entries or loans out
  (the answer then includes the unchanged `baseline`), and `&history=12` for recorded net worth alongside.
  Events are listed once, in `events`; `&bucket_events=1` also repeats each month's events inside its bucket

## Taxes

- `GET /api/taxes/summary?year=2026` — Tax estimate for a year (summary, charts data, findings, assumptions).
  The entries behind it come grouped, largest first, as `item_groups` (`{label, treatment_label, count, total}`),
  with `item_count` dated amounts in all
- `GET /api/taxes/treatments` — Tax treatments that income and expense entries can use
- `GET /api/taxes/profile`, `PATCH /api/taxes/profile` — Filing status, state rate, age, HSA coverage, loss carryover

Income and expense rules and logged changes take an optional `tax_treatment` (wages, 401(k), HSA, FSA,
limited FSA, investment sale, charity, and so on). Untagged income counts as W-2 wages and untagged
expenses as personal spending; the Taxes page lists every default it used. Yearly brackets and limits
live in `engine/tax_tables.py`.

## Settings & Data

- `GET /api/settings` — Get settings
- `GET /api/categories` — List categories
- `GET /api/export` — Download all data as JSON
- `POST /api/import` — Restore from JSON
- `GET /api/backups` — Backup setup and restore points
- `POST /api/backups` — Back up now
- `POST /api/backups/<name>/restore` — Restore a restore point (backs up current data first)
- `POST /api/data/clear` — Back up to Google Cloud, then delete all data


## Devices and AI endpoints

- `GET /api/capabilities` — Which optional features work for the device asking, which AI endpoints are set up, and who is signed in (shown on **Settings → This device**)
- `POST /api/ai/runner/poll`, `POST /api/ai/runner/result` — Used by `home_runner.py` to collect AI work and send answers back (only with `AI_HOME_RUNNER=1`)
- `GET /healthz` — `{"ok": true}` when the app is up; not behind `ALLOWED_LOGINS`
