# Software Requirements Document
## Personal Finance Suite

**Version:** 0.1  
**Date:** 2026-05-09  
**Status:** Draft

---

## 1. System Overview

Personal Finance Suite is a **client-side single-page application (SPA)**. There is no application server. All business logic runs in the browser. Persistence is handled by the **Google Drive API**, which the browser calls directly via OAuth 2.0 user credentials.

```
┌──────────────────────────────────────────────────────┐
│                    Browser (SPA)                     │
│                                                      │
│  ┌────────────┐   ┌──────────────┐  ┌────────────┐  │
│  │ React UI   │ → │ State Store  │→ │ Drive Sync │  │
│  │ (Vite)    │   │ (Zustand)    │  │ (gapi)     │  │
│  └────────────┘   └──────────────┘  └────────────┘  │
│                                             │        │
└─────────────────────────────────────────────│────────┘
                                              ▼
                                   Google Drive REST API
                                   (user's own account)
```

---

## 2. Technology Stack

| Layer | Choice | Rationale |
|-------|--------|-----------|
| Framework | React 18 + TypeScript | Ecosystem size, component model, good for first JS project |
| Build tool | Vite | Fast dev server, simple config, good TS support |
| State management | Zustand | Minimal boilerplate, no context/provider pyramid |
| Routing | React Router v6 | Industry standard for SPAs |
| Styling | Tailwind CSS | Utility-first, no CSS file sprawl |
| Charts | Recharts | React-native, declarative, good for financial line charts |
| Date math | date-fns | Lightweight, tree-shakeable, no global side effects |
| Forms | React Hook Form | Low re-render overhead, good validation integration |
| Validation | Zod | Schema-first; share type definitions between runtime validation and TS types |
| Google API | gapi-script + google-auth-library | Drive REST v3 |
| Testing | Vitest + React Testing Library | Same config as Vite, fast |

No backend. No database. No Docker. Deploy target: GitHub Pages or any static host (Netlify, Vercel, Cloudflare Pages).

---

## 3. Data Architecture

### 3.1 Storage Layout (Google Drive)

```
Personal Finance Suite/          ← app root folder (created on first run)
├── meta.json                    ← workspace metadata, schema version
├── accounts.json                ← Account[] + Loan[]
├── transactions.json            ← OneTimeTransaction[] + RecurringTransaction[]
├── blanket-expenses.json        ← BlanketExpense[]
├── equity.json                  ← RSUGrant[] + ESPPPlan[]
├── snapshots.json               ← AccountSnapshot[] (reconciliation history)
└── settings.json                ← UserSettings
```

Each file is a standalone JSON document. Files are read once on app load and written individually on change (only the file containing the mutated collection is re-written).

### 3.2 Schema Version

`meta.json` carries a `schemaVersion: number` field. On load, if the stored version is older than the app's current version, a migration function runs in-memory and re-saves all files. Migrations are append-only numbered functions.

---

## 4. Data Models

All monetary amounts are stored as **integers in the minor unit of the user's currency** (cents for USD). The UI layer converts for display.

All dates are **ISO 8601 date strings** (`"YYYY-MM-DD"`). No timestamps; the app works at day granularity.

### 4.1 Common Fields

Every object has:
```typescript
id: string          // nanoid(), 21 chars
createdAt: string   // ISO date
updatedAt: string   // ISO date
note?: string       // free-text annotation
```

### 4.2 OneTimeTransaction

```typescript
interface OneTimeTransaction {
  id: string
  type: 'income' | 'expense'
  amount: number            // minor units, always positive
  date: string              // when it occurs / occurred
  category: string          // user-defined category slug
  accountId: string         // destination/source account
  note?: string
  createdAt: string
  updatedAt: string
}
```

### 4.3 RecurringTransaction

```typescript
type Frequency = 'daily' | 'weekly' | 'biweekly' | 'monthly' | 'quarterly' | 'annually'

interface RecurringTransaction {
  id: string
  type: 'income' | 'expense'
  amount: number
  frequency: Frequency
  startDate: string
  endDate?: string          // null = indefinite
  category: string
  accountId: string
  note?: string
  createdAt: string
  updatedAt: string
}
```

### 4.4 BlanketExpense

```typescript
interface BlanketExpense {
  id: string
  label: string             // e.g., "Misc Spending", "Cash / Small purchases"
  amount: number            // per-period amount
  frequency: Frequency      // typically 'monthly'
  startDate: string
  endDate?: string
  category: string
  note?: string
  createdAt: string
  updatedAt: string
}
```

### 4.5 RSUGrant

```typescript
interface VestEvent {
  date: string
  shares: number            // fractional shares stored as integer × 1000 (milliShares)
}

interface RSUGrant {
  id: string
  label: string             // e.g., "2024 Annual Refresh"
  grantDate: string
  totalShares: number       // milliShares
  ticker: string            // e.g., "GOOG"
  priceAtGrant?: number     // minor units, optional reference
  vestSchedule: VestEvent[] // generated by builder, stored explicitly
  withholdingRate: number   // percentage × 100, e.g., 2200 = 22.00%
  accountId: string         // which brokerage receives vested shares
  note?: string
  createdAt: string
  updatedAt: string
}
```

**Vest schedule builder inputs (not stored — used only during creation/edit):**
```typescript
interface VestScheduleBuilder {
  cliffMonths: number
  cliffPercent: number          // percentage × 100
  subsequentFrequency: Frequency
  subsequentPercent: number     // percentage × 100 per period
}
```

The builder validates that cliff + subsequent periods sum to 100%. It generates and stores the explicit `VestEvent[]` array, so future changes to builder logic don't silently alter existing grants.

### 4.6 ESPPPlan

```typescript
interface ESPPPurchasePeriod {
  startDate: string
  endDate: string           // purchase date
  estimatedPurchaseAmount: number  // computed at plan creation, minor units
}

interface ESPPPlan {
  id: string
  label: string             // e.g., "2024 ESPP Offering"
  offeringStartDate: string
  offeringEndDate: string
  contributionMode: 'percent' | 'fixed'
  contributionValue: number  // percent × 100, or minor units
  baseSalary?: number        // minor units/yr; required if contributionMode = 'percent'
  discountRate: number       // percentage × 100, default 1500 = 15%
  hasLookback: boolean
  purchasePeriods: ESPPPurchasePeriod[]  // generated from offering period
  accountId: string
  note?: string
  createdAt: string
  updatedAt: string
}
```

### 4.7 Account

```typescript
type AccountType =
  | 'checking'
  | 'savings'
  | 'brokerage'
  | 'retirement_401k'
  | 'retirement_ira'
  | 'retirement_roth'
  | 'hsa'
  | 'crypto'
  | 'property'
  | 'other_asset'

interface Account {
  id: string
  name: string
  type: AccountType
  institution: string       // free text
  currency: string          // ISO 4217, default from settings
  currentBalance: number    // minor units; updated manually
  lastUpdatedDate: string   // date of last manual update
  linkedLoanId?: string     // for property → mortgage linkage
  isActive: boolean
  note?: string
  createdAt: string
  updatedAt: string
}
```

### 4.8 Loan

```typescript
type LoanType = 'mortgage' | 'auto' | 'student' | 'personal' | 'heloc' | 'other'

interface Loan {
  id: string
  name: string
  type: LoanType
  institution: string
  originalBalance: number   // minor units
  currentBalance: number    // minor units; updated manually
  interestRate: number      // annual rate × 10000, e.g., 6.5% = 65000
  monthlyPayment: number    // minor units (principal + interest)
  startDate: string
  payoffDate: string        // computed or user-entered
  lastUpdatedDate: string
  linkedAccountId?: string  // property account this loan finances
  note?: string
  createdAt: string
  updatedAt: string
}
```

### 4.9 AccountSnapshot (Reconciliation Record)

```typescript
interface AccountSnapshot {
  id: string
  accountId: string
  date: string
  actualBalance: number     // minor units; what user entered
  predictedBalance: number  // minor units; computed at snapshot time
  delta: number             // actual - predicted
  resolution: 'accepted' | 'adjusted' | 'ignored'
  adjustmentTransactionId?: string  // if resolution = 'adjusted'
  note?: string
  createdAt: string
}
```

### 4.10 UserSettings

```typescript
interface UserSettings {
  currency: string          // ISO 4217
  locale: string            // BCP 47, e.g., "en-US"
  fiscalYearStartMonth: number  // 1–12
  defaultWithholdingRate: number  // percentage × 100
  divergenceThresholds: {
    [key in AccountType]?: number  // percentage × 100; alert if |delta| exceeds this
  }
  categories: Category[]
}

interface Category {
  slug: string              // kebab-case, used as foreign key
  label: string             // display name
  type: 'income' | 'expense' | 'both'
  color: string             // hex color for UI
}
```

---

## 5. Projection Engine

The projection engine is a **pure function** with no side effects. It is the computational heart of the application.

```typescript
function project(
  inputs: ProjectionInputs,
  fromDate: string,
  toDate: string
): ProjectionResult
```

### 5.1 ProjectionInputs

```typescript
interface ProjectionInputs {
  transactions: (OneTimeTransaction | RecurringTransaction)[]
  blanketExpenses: BlanketExpense[]
  rsuGrants: RSUGrant[]
  esppPlans: ESPPPlan[]
  accounts: Account[]
  loans: Loan[]
  stockPrices: Record<string, number>  // ticker → minor units per share
}
```

### 5.2 Algorithm

1. **Expand all recurring objects** into a flat list of `CashFlowEvent[]` over the date range:
   - `RecurringTransaction`: one event per occurrence
   - `BlanketExpense`: one event per period
   - `RSUGrant`: one event per VestEvent (gross and net-of-withholding variants)
   - `ESPPPlan`: one event per purchase period
   - `Loan`: one event per monthly payment
2. **Sort events by date.**
3. **Bucket by month.** For each calendar month, sum income events and expense events.
4. **Carry-forward balance.** Starting from the sum of all `Account.currentBalance` minus all `Loan.currentBalance`, add each month's net cash flow to produce projected net worth.
5. **Return** a `MonthlyBucket[]` for the timeline view and a `CashFlowEvent[]` for drill-down.

```typescript
interface CashFlowEvent {
  date: string
  sourceId: string          // id of originating object
  sourceType: 'transaction' | 'recurring' | 'blanket' | 'rsu' | 'espp' | 'loan_payment'
  type: 'income' | 'expense'
  amount: number
  label: string
  category: string
}

interface MonthlyBucket {
  month: string             // "YYYY-MM"
  income: number
  expenses: number
  netCashFlow: number
  cumulativeNetWorth: number  // predicted
  actualNetWorth?: number     // present only if a snapshot exists for this month
  events: CashFlowEvent[]
}
```

### 5.3 Scenario Mode

Scenario mode passes a `disabledIds: Set<string>` to the projection function. Events from disabled objects are filtered out before bucketing. The UI overlays the scenario projection on the baseline in a different color.

---

## 6. Google Drive Integration

### 6.1 Authentication

- OAuth 2.0 with PKCE flow (no client secret needed for SPA)
- Scopes: `https://www.googleapis.com/auth/drive.file` (access only files created by this app)
- Token stored in `sessionStorage` only (cleared on tab close)
- On expiry, silent refresh via refresh token in memory; if unavailable, prompt re-login

### 6.2 File Operations

```
Read:  GET  /drive/v3/files/:fileId?alt=media
Write: PATCH /upload/drive/v3/files/:fileId (multipart, replaces content)
Create: POST /upload/drive/v3/files (multipart, with metadata)
List:  GET /drive/v3/files?q='<folderId>' in parents
```

### 6.3 Sync Strategy

- **On load:** read all files from Drive into Zustand store
- **On change:** debounced write (2 s) of the affected JSON file only
- **Conflict detection:** store `modifiedTime` from Drive metadata. Before each write, re-fetch metadata; if `modifiedTime` has advanced beyond what the app last wrote, display a conflict banner with "Reload from Drive" / "Overwrite Drive" options
- **Offline:** changes accumulate in store; a sync queue flushes when connectivity resumes (navigator.onLine + online event)

### 6.4 File Initialization

On first run (folder not found):
1. Create folder `Personal Finance Suite` in Drive root
2. Create all JSON files with empty arrays / default settings
3. Write `meta.json` with `schemaVersion: 1`

---

## 7. Component Architecture

```
App
├── AuthGate                    ← handles Google sign-in / loading state
├── Layout
│   ├── Sidebar (nav)
│   └── Outlet
│       ├── Dashboard           ← F1
│       ├── Transactions
│       │   ├── TransactionList
│       │   ├── AddOneTime (modal/drawer)
│       │   └── AddRecurring (modal/drawer)
│       ├── Equity
│       │   ├── RSUGrantList
│       │   ├── RSUGrantForm    ← vest schedule builder
│       │   ├── ESPPPlanList
│       │   └── ESPPPlanForm
│       ├── Accounts
│       │   ├── AccountList
│       │   ├── AccountForm
│       │   ├── LoanList
│       │   ├── LoanForm
│       │   └── ReconcileModal
│       ├── Timeline            ← F5 — projection table + chart
│       └── Settings
```

---

## 8. State Management

Zustand store slices:

```typescript
// One slice per data file
useTransactionStore     → transactions[], blanketExpenses[]
useEquityStore          → rsuGrants[], esppPlans[]
useAccountStore         → accounts[], loans[], snapshots[]
useSettingsStore        → settings
useSyncStore            → syncStatus, lastSyncedAt, pendingWrites, conflicts[]

// Derived (computed, not persisted)
useProjectionStore      → memoized output of project(), refreshed when inputs change
```

The projection store subscribes to all data slices and re-runs the projection engine on any change, gated by a 200 ms debounce to avoid thrashing on bulk imports.

---

## 9. Calculation Rules

### 9.1 RSU Net Value

```
grossValue    = shares × stockPricePerShare
taxWithheld   = grossValue × (withholdingRate / 10000)
netProceeds   = grossValue - taxWithheld
```

The UI shows both gross and net. Net proceeds flow into projected cash flow for the linked account.

### 9.2 ESPP Purchase Price

```
priceAtPeriodStart  = user-entered estimate
priceAtPurchase     = user-entered estimate
basePrice           = hasLookback
                        ? min(priceAtPeriodStart, priceAtPurchase)
                        : priceAtPurchase
purchasePrice       = basePrice × (1 − discountRate / 10000)
contributionAmount  = contributionMode === 'percent'
                        ? (baseSalary / 12) × periodsInOffering × (contributionValue / 10000)
                        : contributionValue × periodsInOffering
sharesPurchased     = contributionAmount / purchasePrice   (display only; stored as milliShares)
immediateGain       = contributionAmount × (discountRate / 10000)
```

### 9.3 Loan Payment Allocation (for payoff date computation)

Standard amortization:
```
monthlyRate = interestRate / 10000 / 12
payment     = balance × monthlyRate / (1 − (1 + monthlyRate)^−remainingMonths)
```

If `payoffDate` is provided by user, it is stored as-is. If not, it is computed from the amortization.

### 9.4 Recurring Transaction Occurrence Dates

Given `startDate`, `endDate` (optional), `frequency`:
- `daily`: every calendar day
- `weekly`: same weekday as startDate
- `biweekly`: every 14 days from startDate
- `monthly`: same day-of-month as startDate (clamped to last day of month)
- `quarterly`: 3-month intervals
- `annually`: same month+day each year

All occurrence dates within the projection window are returned as an array.

---

## 10. Security Requirements

| Requirement | Implementation |
|-------------|---------------|
| No data on app servers | Pure SPA; no API backend; no telemetry |
| OAuth least-privilege | `drive.file` scope (only files this app created) |
| Token storage | Access token in memory only; refresh token in memory |
| No third-party analytics | No GA, Segment, Sentry, or equivalent in v1 |
| XSS prevention | React's default escaping; no `dangerouslySetInnerHTML` |
| Content Security Policy | Strict CSP header on static host: no inline scripts |
| Dependency audit | `npm audit` run in CI; no known high/critical CVEs |

---

## 11. Performance Requirements

| Scenario | Target |
|----------|--------|
| Initial data load from Drive | < 3 s on typical broadband |
| Projection re-compute (5-yr horizon, ~500 events) | < 100 ms |
| Dashboard render (cold, data already in store) | < 200 ms |
| Bundle size (gzipped, initial chunk) | < 250 KB |

The projection engine must run on the main thread without a Web Worker in v1; introduce a Worker only if benchmarks show > 100 ms on a 10-year horizon.

---

## 12. Error Handling

| Error Type | Behavior |
|------------|----------|
| Drive API 401 | Clear tokens, redirect to sign-in |
| Drive API 429 | Exponential backoff, max 3 retries, then toast error |
| Drive API 5xx | Retry once after 2 s, then surface error banner |
| File parse error | Show "data file corrupted" error, offer download of raw JSON |
| Offline | Queue writes locally, sync on reconnect; read-only banner while offline |
| Schema migration failure | Abort load, display migration error with raw JSON download |

---

## 13. Testing Requirements

| Layer | Tool | Coverage target |
|-------|------|-----------------|
| Projection engine (pure functions) | Vitest | 90% branch coverage |
| Vest schedule builder | Vitest | 100% (finite rule set) |
| ESPP calculation | Vitest | 100% |
| Amortization | Vitest | 90% |
| Component smoke tests | React Testing Library | Key flows: add transaction, add RSU, reconcile |
| Drive sync module | Vitest + msw (mock Drive API) | Happy path + conflict + offline |

---

## 14. Deployment

- Build: `vite build` → `dist/` (static assets only)
- Host: GitHub Pages (initial), any static CDN acceptable
- Environment variables (baked at build time via Vite):
  - `VITE_GOOGLE_CLIENT_ID` — OAuth client ID from Google Cloud Console
  - `VITE_APP_VERSION` — semver, used for schema migration checks
- No server-side rendering required
- CI: GitHub Actions — lint → typecheck → test → build on every PR

---

## 15. Future Considerations (Not in v1 Scope)

- Plaid integration for automated transaction import
- Stock price feed (e.g., Yahoo Finance scrape or free tier API)
- PWA / offline-first with IndexedDB cache
- Multi-workspace (one Drive folder per family member)
- CSV import for bulk historical data entry
- Read-only share link via Google Drive sharing
- 401k contribution limit tracking and warnings
