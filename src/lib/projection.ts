// Pure cash-flow projection engine.
// Expands recurring transactions + one-time events + equity events
// into a flat list of CashFlowEvent[], sorted by date.

import type {
  RecurringTransaction,
  OneTimeTransaction,
  RsuGrant,
  EsppPlan,
  BlanketExpense,
  CashFlowEvent,
  Frequency,
} from '../types'

// ── Date helpers ─────────────────────────────────────────────────────────────

function toDate(s: string): Date {
  const [y, m, d] = s.split('-').map(Number)
  return new Date(Date.UTC(y, m - 1, d))
}

function toISO(d: Date): string {
  return d.toISOString().slice(0, 10)
}

function addDays(d: Date, n: number): Date {
  const r = new Date(d)
  r.setUTCDate(r.getUTCDate() + n)
  return r
}

function addMonths(d: Date, n: number): Date {
  const r = new Date(d)
  r.setUTCMonth(r.getUTCMonth() + n)
  return r
}

// ── Frequency expansion ───────────────────────────────────────────────────────

function* expand(
  start: Date,
  end: Date,
  from: Date,
  to: Date,
  freq: Frequency,
): Generator<Date> {
  let cursor = new Date(start)
  while (cursor <= end && cursor <= to) {
    if (cursor >= from) yield new Date(cursor)
    switch (freq) {
      case 'daily':      cursor = addDays(cursor, 1);    break
      case 'weekly':     cursor = addDays(cursor, 7);    break
      case 'biweekly':   cursor = addDays(cursor, 14);   break
      case 'monthly':    cursor = addMonths(cursor, 1);  break
      case 'quarterly':  cursor = addMonths(cursor, 3);  break
      case 'annual':     cursor = addMonths(cursor, 12); break
    }
  }
}

// ── RSU net proceeds per vest ─────────────────────────────────────────────────

function rsuNetCents(
  sharesMillis: number,
  currentPriceCents: number,
  withholdingRate: number,
): number {
  const shares = sharesMillis / 1000
  const gross = shares * currentPriceCents
  return Math.round(gross * (1 - withholdingRate / 10000))
}

// ── Main projection function ──────────────────────────────────────────────────

export interface ProjectionInput {
  recurring: RecurringTransaction[]
  oneTime: OneTimeTransaction[]
  blanket: BlanketExpense[]
  rsuGrants: RsuGrant[]
  esppPlans: EsppPlan[]
  from: string          // ISO date
  to: string            // ISO date
  /** Map of ticker → current price in cents (for RSU net calculation) */
  tickerPrices?: Record<string, number>
}

export function buildProjection({
  recurring,
  oneTime,
  blanket,
  rsuGrants,
  esppPlans,
  from,
  to,
  tickerPrices = {},
}: ProjectionInput): CashFlowEvent[] {
  const events: CashFlowEvent[] = []
  const fromDate = toDate(from)
  const toDate_ = toDate(to)

  // ── Recurring transactions ────────────────────────────────────────────────
  for (const r of recurring) {
    const start = toDate(r.startDate)
    const end = r.endDate ? toDate(r.endDate) : toDate_

    for (const d of expand(start, end, fromDate, toDate_, r.frequency)) {
      events.push({
        date: toISO(d),
        label: r.label,
        type: r.type,
        amount: r.amount,
        category: r.category,
        accountId: r.accountId,
        sourceId: r.id,
        sourceType: 'recurring',
      })
    }
  }

  // ── Blanket expenses (monthly) ────────────────────────────────────────────
  for (const b of blanket) {
    const start = fromDate
    let cursor = new Date(Date.UTC(start.getUTCFullYear(), start.getUTCMonth(), 1))
    while (cursor <= toDate_) {
      events.push({
        date: toISO(cursor),
        label: b.label,
        type: 'expense',
        amount: b.amount,
        category: 'blanket',
        accountId: b.accountId,
        sourceId: b.id,
        sourceType: 'blanket',
      })
      cursor = addMonths(cursor, 1)
    }
  }

  // ── One-time transactions ─────────────────────────────────────────────────
  for (const t of oneTime) {
    const d = toDate(t.date)
    if (d >= fromDate && d <= toDate_) {
      events.push({
        date: t.date,
        label: t.label,
        type: t.type,
        amount: t.amount,
        category: t.category,
        accountId: t.accountId,
        sourceId: t.id,
        sourceType: 'one-time',
      })
    }
  }

  // ── RSU vests ────────────────────────────────────────────────────────────
  for (const grant of rsuGrants) {
    const price = tickerPrices[grant.ticker] ?? grant.priceAtGrant
    for (const vest of grant.vestSchedule) {
      const d = toDate(vest.date)
      if (d >= fromDate && d <= toDate_) {
        const net = rsuNetCents(vest.shares, price, grant.withholdingRate)
        events.push({
          date: vest.date,
          label: `RSU Vest — ${grant.label}`,
          type: 'income',
          amount: net,
          category: 'rsu-vest',
          accountId: grant.accountId,
          sourceId: grant.id,
          sourceType: 'rsu-vest',
        })
      }
    }
  }

  // ── ESPP purchase periods ─────────────────────────────────────────────────
  for (const plan of esppPlans) {
    for (const period of plan.purchasePeriods) {
      if (period.status === 'future' && !period.estimatedPurchaseAmount) continue
      const d = toDate(period.endDate)
      if (d >= fromDate && d <= toDate_) {
        events.push({
          date: period.endDate,
          label: `ESPP Purchase — ${plan.label}`,
          type: 'income',
          amount: period.estimatedPurchaseAmount,
          category: 'espp-purchase',
          accountId: plan.accountId,
          sourceId: plan.id,
          sourceType: 'espp-purchase',
        })
      }
    }
  }

  events.sort((a, b) => a.date.localeCompare(b.date))
  return events
}

// ── Running balance per account ───────────────────────────────────────────────

export function runningBalances(
  events: CashFlowEvent[],
  seedBalances: Record<string, number>,   // accountId → current balance in cents
): Record<string, { date: string; balance: number }[]> {
  const result: Record<string, { date: string; balance: number }[]> = {}
  const balances = { ...seedBalances }

  for (const ev of events) {
    const prev = balances[ev.accountId] ?? 0
    const delta = ev.type === 'income' ? ev.amount : -ev.amount
    balances[ev.accountId] = prev + delta

    if (!result[ev.accountId]) result[ev.accountId] = []
    result[ev.accountId].push({ date: ev.date, balance: balances[ev.accountId] })
  }

  return result
}
