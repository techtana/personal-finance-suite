import { useMemo, useState } from 'react'
import { useDataStore } from '../store/dataStore'
import { buildProjection, runningBalances } from '../lib/projection'
import { formatCents, formatDateShort, todayISO, addMonthsISO } from '../lib/format'
import type { CashFlowEvent } from '../types'

type Range = '3m' | '6m' | '12m' | '24m'
const RANGE_MONTHS: Record<Range, number> = { '3m': 3, '6m': 6, '12m': 12, '24m': 24 }

export function Timeline() {
  const { accounts, recurring, oneTime, blanketExpenses, rsuGrants, esppPlans } = useDataStore()
  const [range, setRange] = useState<Range>('12m')
  const [filterAccount, setFilterAccount] = useState<string>('all')

  const today = todayISO()
  const to = addMonthsISO(today, RANGE_MONTHS[range])

  const events = useMemo(
    () =>
      buildProjection({
        recurring,
        oneTime,
        blanket: blanketExpenses,
        rsuGrants,
        esppPlans,
        from: today,
        to,
      }),
    [recurring, oneTime, blanketExpenses, rsuGrants, esppPlans, today, to],
  )

  const seedBalances = useMemo(
    () => Object.fromEntries(accounts.map((a) => [a.id, a.currentBalance])),
    [accounts],
  )

  const balances = useMemo(
    () => runningBalances(events, seedBalances),
    [events, seedBalances],
  )

  const visibleEvents = filterAccount === 'all'
    ? events
    : events.filter((e) => e.accountId === filterAccount)

  // Group by month
  const grouped = useMemo(() => {
    const map = new Map<string, CashFlowEvent[]>()
    for (const ev of visibleEvents) {
      const month = ev.date.slice(0, 7)
      if (!map.has(month)) map.set(month, [])
      map.get(month)!.push(ev)
    }
    return map
  }, [visibleEvents])

  const monthEntries = [...grouped.entries()]

  const totalIncome = visibleEvents.filter((e) => e.type === 'income').reduce((s, e) => s + e.amount, 0)
  const totalExpenses = visibleEvents.filter((e) => e.type === 'expense').reduce((s, e) => s + e.amount, 0)

  return (
    <>
      <div className="flex items-start justify-between mb-8">
        <div>
          <h1 className="text-2xl font-extrabold tracking-tight" style={{ color: '#0f172a' }}>Timeline</h1>
          <p className="text-sm mt-1" style={{ color: '#5c6473' }}>Cash flow projection · all sources combined</p>
        </div>
      </div>

      {/* Controls */}
      <div className="flex items-center gap-3 mb-6">
        {/* Range picker */}
        <div className="flex border border-[#d1d5db] rounded-lg overflow-hidden">
          {(Object.keys(RANGE_MONTHS) as Range[]).map((r) => (
            <button
              key={r}
              onClick={() => setRange(r)}
              className="px-3 py-2 text-sm"
              style={{
                background: range === r ? '#3b5fc0' : '#fff',
                color: range === r ? '#fff' : '#0f172a',
                fontWeight: range === r ? 600 : 400,
              }}
            >
              {r}
            </button>
          ))}
        </div>

        {/* Account filter */}
        <select
          value={filterAccount}
          onChange={(e) => setFilterAccount(e.target.value)}
          className="px-3 py-2 border border-[#d1d5db] rounded-lg text-sm bg-white"
          style={{ color: '#0f172a' }}
        >
          <option value="all">All accounts</option>
          {accounts.map((a) => (
            <option key={a.id} value={a.id}>{a.label}</option>
          ))}
        </select>

        {/* Summary */}
        <div className="ml-auto flex gap-6 text-sm">
          <span>
            <span className="font-bold text-[#166534]">+{formatCents(totalIncome)}</span>
            <span className="ml-1" style={{ color: '#5c6473' }}>income</span>
          </span>
          <span>
            <span className="font-bold text-[#991b1b]">−{formatCents(totalExpenses)}</span>
            <span className="ml-1" style={{ color: '#5c6473' }}>expenses</span>
          </span>
          <span>
            <span className={`font-bold ${totalIncome - totalExpenses >= 0 ? 'text-[#166534]' : 'text-[#991b1b]'}`}>
              {totalIncome - totalExpenses >= 0 ? '+' : '−'}{formatCents(Math.abs(totalIncome - totalExpenses))}
            </span>
            <span className="ml-1" style={{ color: '#5c6473' }}>net</span>
          </span>
        </div>
      </div>

      {/* Monthly groups */}
      {monthEntries.length === 0 ? (
        <div className="text-center py-20 text-sm" style={{ color: '#5c6473' }}>
          No projected events in this range. Add recurring transactions to populate the timeline.
        </div>
      ) : (
        monthEntries.map(([month, evs]) => {
          const income = evs.filter((e) => e.type === 'income').reduce((s, e) => s + e.amount, 0)
          const expenses = evs.filter((e) => e.type === 'expense').reduce((s, e) => s + e.amount, 0)
          const net = income - expenses
          const [y, m] = month.split('-')
          const monthLabel = new Date(Date.UTC(+y, +m - 1, 1)).toLocaleDateString('en-US', {
            month: 'long', year: 'numeric', timeZone: 'UTC',
          })

          return (
            <div key={month} className="mb-6">
              {/* Month header */}
              <div
                className="flex justify-between items-center mb-2 pb-2"
                style={{ borderBottom: '2px solid #b5bac3' }}
              >
                <span className="text-[11px] font-bold uppercase tracking-widest" style={{ color: '#5c6473' }}>
                  {monthLabel}
                </span>
                <div className="flex gap-4 text-xs font-semibold">
                  <span className="text-[#166534]">+{formatCents(income)}</span>
                  <span className="text-[#991b1b]">−{formatCents(expenses)}</span>
                  <span className={net >= 0 ? 'text-[#166534]' : 'text-[#991b1b]'}>
                    {net >= 0 ? '+' : '−'}{formatCents(Math.abs(net))}
                  </span>
                </div>
              </div>

              {/* Events */}
              <div className="bg-white border border-[#d1d5db] rounded-xl overflow-hidden">
                {evs.map((ev, i) => (
                  <div
                    key={`${ev.sourceId}-${ev.date}-${i}`}
                    className="flex items-center gap-3.5 px-5 py-3 border-b border-[#d1d5db] last:border-0"
                  >
                    <div
                      className={`w-2 h-2 rounded-full flex-shrink-0 ${ev.type === 'income' ? 'bg-[#166534]' : 'bg-[#991b1b]'}`}
                    />
                    <div className="flex-1 min-w-0">
                      <div className="text-sm font-medium truncate" style={{ color: '#0f172a' }}>{ev.label}</div>
                    </div>
                    <div className="text-xs w-24 text-right" style={{ color: '#5c6473' }}>
                      {formatDateShort(ev.date)}
                    </div>
                    <div className={`text-sm font-bold w-28 text-right ${ev.type === 'income' ? 'text-[#166534]' : 'text-[#991b1b]'}`}>
                      {ev.type === 'income' ? '+' : '−'}{formatCents(ev.amount)}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )
        })
      )}
    </>
  )
}
