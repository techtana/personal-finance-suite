// ─── Encoding conventions ─────────────────────────────────────────────────
// Money        → integer cents (minor units)    $12.40 = 1240
// Shares       → integer milliShares (×1000)    25.0 sh = 25000
// Rates        → integer percent × 100          22% = 2200, 6.875% = 68750
// Dates        → ISO 8601 string "YYYY-MM-DD"

// ─── Accounts ─────────────────────────────────────────────────────────────

export type AccountType =
  | 'checking'
  | 'savings'
  | 'brokerage'
  | '401k'
  | 'ira'
  | 'property'
  | 'loan'
  | 'other'

export interface Account {
  id: string
  label: string
  type: AccountType
  institution: string
  currentBalance: number          // cents (negative for liabilities)
  alertThresholdPct?: number      // percent × 100 (e.g. 500 = 5%). Uses settings default if absent
  linkedLoanId?: string           // for property accounts
  linkedAccountId?: string        // for loan accounts
  note?: string
  createdAt: string
  updatedAt: string
}

// ─── Transactions ──────────────────────────────────────────────────────────

export type TransactionType = 'income' | 'expense'
export type Frequency = 'daily' | 'weekly' | 'biweekly' | 'monthly' | 'quarterly' | 'annual'

export interface RecurringTransaction {
  id: string
  label: string
  type: TransactionType
  amount: number                  // cents
  frequency: Frequency
  startDate: string
  endDate: string | null
  category: string
  accountId: string
  note?: string
  createdAt: string
  updatedAt: string
}

export interface OneTimeTransaction {
  id: string
  label: string
  type: TransactionType
  amount: number                  // cents
  date: string
  category: string
  accountId: string
  note?: string
  createdAt: string
  updatedAt: string
}

export interface TransactionsFile {
  recurring: RecurringTransaction[]
  oneTime: OneTimeTransaction[]
}

// ─── Blanket expenses ──────────────────────────────────────────────────────

export interface BlanketExpense {
  id: string
  label: string
  amount: number                  // cents per month
  accountId: string
  note?: string
  createdAt: string
  updatedAt: string
}

// ─── Equity — RSU ─────────────────────────────────────────────────────────

export interface VestEvent {
  date: string
  shares: number                  // milliShares
}

export interface RsuGrant {
  id: string
  label: string
  grantDate: string
  totalShares: number             // milliShares
  ticker: string
  priceAtGrant: number            // cents per share
  withholdingRate: number         // percent × 100
  accountId: string
  vestSchedule: VestEvent[]
  note?: string
  createdAt: string
  updatedAt: string
}

// ─── Equity — ESPP ────────────────────────────────────────────────────────

export type PurchasePeriodStatus = 'completed' | 'current' | 'future'

export interface PurchasePeriod {
  id: string
  startDate: string
  endDate: string
  offeringStartPrice: number      // cents
  purchaseDatePrice: number | null // cents, null if future
  purchasePrice: number           // cents (the actual discounted price)
  sharesEstimated: number         // whole shares
  estimatedPurchaseAmount: number // cents (FMV at purchase date)
  status: PurchasePeriodStatus
  note?: string
}

export type ContributionMode = 'fixed' | 'percent'

export interface EsppPlan {
  id: string
  label: string
  ticker: string
  offeringStartDate: string
  offeringEndDate: string
  contributionMode: ContributionMode
  contributionValue: number       // cents (fixed) or percent × 100
  discountRate: number            // percent × 100 (e.g. 1500 = 15%)
  hasLookback: boolean
  accountId: string
  purchasePeriods: PurchasePeriod[]
  note?: string
  createdAt: string
  updatedAt: string
}

export interface EquityFile {
  rsuGrants: RsuGrant[]
  esppPlans: EsppPlan[]
}

// ─── Snapshots ─────────────────────────────────────────────────────────────

export interface Snapshot {
  id: string
  accountId: string
  date: string
  balance: number                 // cents
  note?: string
  createdAt: string
}

// ─── Loans ─────────────────────────────────────────────────────────────────

export interface Loan {
  id: string
  label: string
  linkedAccountId: string
  originalPrincipal: number       // cents
  currentBalance: number          // cents (outstanding)
  interestRateBps: number         // basis points × 10 (e.g. 68750 = 6.875%)
  termMonths: number
  startDate: string
  monthlyPayment: number          // cents
  note?: string
  createdAt: string
  updatedAt: string
}

// ─── Settings ─────────────────────────────────────────────────────────────

export type Theme = 'light' | 'dark' | 'system'
export type SidebarStyle = 'icon-label' | 'icon-only' | 'full'
export type Density = 'comfortable' | 'compact'

export interface AppSettings {
  currency: string                // ISO 4217 e.g. "USD"
  locale: string                  // BCP 47 e.g. "en-US"
  theme: Theme
  accentColor: string             // hex
  sidebarStyle: SidebarStyle
  density: Density
  fontSize: 'sm' | 'md' | 'lg'
  divergenceAlertPct: number      // percent × 100 (default 500 = 5%)
  startOfWeek: 0 | 1              // 0=Sunday, 1=Monday
}

// ─── Meta ──────────────────────────────────────────────────────────────────

export interface DriveFileMeta {
  fileId: string
  name: string
}

export interface AppMeta {
  version: string
  folderId: string
  files: Record<string, DriveFileMeta>
  createdAt: string
  updatedAt: string
}

// ─── Projection ────────────────────────────────────────────────────────────

export interface CashFlowEvent {
  date: string
  label: string
  type: TransactionType
  amount: number                  // cents
  category: string
  accountId: string
  sourceId: string
  sourceType: 'recurring' | 'one-time' | 'rsu-vest' | 'espp-purchase' | 'blanket'
}

export interface AccountProjection {
  accountId: string
  date: string
  predictedBalance: number        // cents
}
