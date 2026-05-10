# Product Requirements Document
## Personal Finance Suite

**Version:** 0.1  
**Date:** 2026-05-09  
**Status:** Draft

---

## 1. Overview

Personal Finance Suite is a self-hosted, client-side web application that replaces complex Excel-based financial planners with a modern, performant UI. Unlike bank-connected apps (Mint, CreditKarma), it focuses on **scheduled and planned** financial events rather than exact transaction capture. Users maintain a high-level picture of their finances by entering what they know — salaries, RSU vests, ESPP purchases, recurring bills, mortgages — and periodically reconciling against actual account balances.

All data is stored in the user's own Google Drive. There is no application server, no database, and no third-party data broker.

---

## 2. Goals

| # | Goal |
|---|------|
| G1 | Replace an Excel-based planner that is slow and hard to share |
| G2 | Let users model their full financial picture from known, scheduled events |
| G3 | Detect divergence between predicted and actual balances without automated bank pulls |
| G4 | Support equity compensation (RSU, ESPP) as first-class plan objects |
| G5 | Keep personal financial data entirely within the user's Google account |
| G6 | Be approachable for non-technical friends and family |

---

## 3. Non-Goals

- No automatic bank/brokerage data pulls (no Plaid integration in v1)
- No receipt scanning or exact-to-the-penny tracking
- No tax filing or tax calculation engine
- No multi-user collaboration or shared budgets
- No mobile native app (responsive web only)

---

## 4. User Personas

### Primary — "The Planner"
Mid-career professional with a salary, equity comp (RSU/ESPP), a mortgage, and investment accounts. Spends 30–60 min/month on finances. Currently uses a large Excel model.

### Secondary — "The Curious Beginner"
A friend or family member who wants to start tracking finances but finds budgeting apps overwhelming. Needs simple entry points and a clear dashboard.

---

## 5. Core Concepts

### 5.1 Financial Objects

The app models finances as a set of **objects** that each project values forward in time. Every object emits a stream of dated cash-flow events that the timeline view consumes.

| Object | What it models |
|--------|---------------|
| **OneTimeTransaction** | A single past or future income/expense |
| **RecurringTransaction** | A repeating income/expense at a fixed cadence |
| **BlanketExpense** | A catch-all monthly/weekly amount for uncategorized spending |
| **RSUGrant** | An equity grant with a vesting schedule; one entry per grant |
| **ESPPPlan** | An ESPP offering period with contribution and discount parameters |
| **Account** | A snapshot-updated container: bank, brokerage, retirement, property |
| **Loan** | A liability with balance, rate, and payment schedule |

### 5.2 Scheduled vs. Actual

Each object carries a **predicted value** (derived from its schedule) and an **actual value** (last user-confirmed snapshot). The app computes the delta and flags divergence beyond a configurable threshold.

### 5.3 Data Storage

All data is stored as JSON files in a dedicated folder in the user's Google Drive (`Personal Finance Suite/`). The app reads and writes these files via the Google Drive API after the user authenticates with OAuth 2.0. No data ever touches an application server.

---

## 6. Features

### F1 — Dashboard

- Net worth summary card (assets minus liabilities, actual vs. predicted)
- Monthly cash-flow summary (income vs. expenses, this month)
- Divergence alerts: accounts where actual vs. predicted delta exceeds threshold
- Upcoming scheduled events (next 30 days)
- Net worth trend chart (12-month rolling, predicted + actuals overlaid)

### F2 — Transactions

- **Add one-time transaction:** amount, date, category, account, note
- **Add recurring transaction:** amount, start date, end date (optional), frequency (daily/weekly/biweekly/monthly/quarterly/annually), category, account
- **Add blanket expense:** a single monthly "catch-all" amount per category (e.g., "Misc Spending $500/mo")
- Transaction list with search, filter by date range, category, account
- Edit and delete any transaction

### F3 — Equity Compensation

#### RSU Grant
- Grant date, total shares awarded, vesting schedule template:
  - Cliff: months until first vest, percentage at cliff
  - Subsequent vests: frequency (monthly/quarterly), percentage per vest
- Ticker symbol (user-supplied) for approximate value
- Manual stock price override or "use today's price" prompt
- System generates all vest events automatically from one entry
- Gross/net toggle: apply estimated withholding rate to compute after-tax proceeds

#### ESPP Plan
- Offering period start and end date
- Purchase periods within the offering (e.g., 6-month offering, 2 purchase periods)
- Contribution rate (% of salary or fixed dollar amount per period)
- Discount rate (default 15%)
- Lookback provision: yes/no; if yes, base price = lower of offering-start or purchase-date price
- Estimated purchase calculation displayed at plan creation
- One plan entry covers all purchase periods within the offering

### F4 — Accounts & Net Worth

- **Add account:** name, type (checking, savings, brokerage, 401k/IRA, crypto, property, other), institution (free text), current balance/value
- **Add loan:** name, type (mortgage, auto, student, personal, HELOC), balance, interest rate, monthly payment, payoff date
- **Update snapshot:** user enters current balance; system records timestamp, calculates delta from predicted
- **Divergence view:** side-by-side of predicted vs. actual for each account, with % difference
- Property: enter current estimated value and linked mortgage loan

### F5 — Timeline & Projections

- Month-by-month projection table (configurable horizon: 1, 3, 5, 10 years)
- Columns: month, income, expenses, net cash flow, cumulative net worth (predicted)
- Actual overlay: months with snapshots show actual net worth vs. predicted
- Drill-down: click any month to see the contributing events
- Scenario mode: temporarily toggle items on/off to model "what if" (e.g., what if I stop contributing to ESPP?)

### F6 — Reconciliation

- Triggered by user manually (or prompted after divergence alert)
- Shows predicted balance vs. user-entered actual balance per account
- Options on divergence: (a) accept actual and adjust projection forward, (b) note the difference as a one-time adjustment transaction, (c) ignore / dismiss
- Reconciliation history log per account

### F7 — Google Drive Integration

- Sign in with Google (OAuth 2.0, Drive scope)
- First-run: create `Personal Finance Suite/` folder and initialize data files
- Auto-save on every change (debounced 2 s write)
- Manual "Sync now" button
- Conflict detection: if file was modified externally (another device/browser), prompt user to reload
- Export: download all data as a single JSON file for backup

### F8 — Settings

- Default currency and locale
- Divergence alert threshold (%) per account type
- Estimated tax withholding rate (for RSU/ESPP net calculations)
- Categories: add, rename, delete custom categories
- Fiscal year start month (for annual summaries)

---

## 7. User Stories (Priority Order)

| ID | As a… | I want to… | So that… | Priority |
|----|-------|-----------|---------|----------|
| US-01 | Planner | Enter a recurring monthly expense | My projections account for fixed costs | P0 |
| US-02 | Planner | Enter my RSU grant once | All future vest events appear automatically | P0 |
| US-03 | Planner | See my projected net worth over 12 months | I can plan major purchases | P0 |
| US-04 | Planner | Update my brokerage account balance | The app knows my actual vs. predicted position | P0 |
| US-05 | Planner | Enter an ESPP plan | My purchase proceeds appear in projections | P1 |
| US-06 | Planner | Add a blanket spending category | I don't need to itemize every small purchase | P0 |
| US-07 | Beginner | See a summary of this month's income vs. spending | I can understand where I stand quickly | P0 |
| US-08 | Planner | See which accounts are diverging from predictions | I know where I need to investigate | P1 |
| US-09 | Planner | Run a "what if" scenario | I can model job change or large expense impact | P2 |
| US-10 | Planner | Export my data | I have a local backup that isn't on someone's server | P1 |

---

## 8. Out-of-Scope for v1

- Budgeting / envelope system
- Bill reminders / notifications
- Multi-currency portfolios (single currency per workspace)
- Shared/joint accounts with another user
- Stock price API feeds (user enters or updates manually)
- Tax optimization recommendations

---

## 9. Success Metrics

| Metric | Target |
|--------|--------|
| Time to enter a full RSU grant | < 3 minutes |
| Time to enter a monthly recurring bill | < 60 seconds |
| Time to reconcile all accounts in a monthly review | < 10 minutes |
| Data load time from Google Drive on app open | < 3 seconds |
| User can understand dashboard without documentation | Usability test pass rate ≥ 80% |

---

## 10. Open Questions

1. Should RSU vesting automatically suggest a sell transaction on vest date, or leave it to the user?
2. For ESPP, should the app track shares held after purchase, or treat each purchase as immediate cash proceeds?
3. Should the app support multiple workspaces (e.g., one per family member)?
4. Is a "read-only share" link (pointing to a read-only copy of the Google Drive data) useful for sharing with a financial advisor?
