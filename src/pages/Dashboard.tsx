import { useMemo } from 'react'
import { useDataStore } from '../store/dataStore'
import { buildProjection } from '../lib/projection'
import { formatCents, formatDateShort, todayISO, addMonthsISO, relativeDays } from '../lib/format'
import { Badge } from '../components/Badge'
import { Panel } from '../components/Panel'

export function Dashboard() {
  const { accounts, recurring, oneTime, blanketExpenses, rsuGrants, esppPlans } = useDataStore()

  const today = todayISO()
  const sixMonthsOut = addMonthsISO(today, 6)

  const events = useMemo(
    () =>
      buildProjection({
        recurring,
        oneTime,
        blanket: blanketExpenses,
        rsuGrants,
        esppPlans,
        from: today,
        to: sixMonthsOut,
      }),
    [recurring, oneTime, blanketExpenses, rsuGrants, esppPlans, today, sixMonthsOut],
  )

  const netWorth = accounts.reduce((s, a) => s + a.currentBalance, 0)

  const assets = accounts.filter((a) => a.currentBalance >= 0)
  const liabilities = accounts.filter((a) => a.currentBalance < 0)

  const upcomingEvents = events.slice(0, 8)

  const monthlyIncome = recurring
    .filter((r) => r.type === 'income')
    .reduce((s, r) => s + (r.frequency === 'biweekly' ? r.amount * 26 / 12 : r.amount), 0)

  const monthlyExpenses = recurring
    .filter((r) => r.type === 'expense')
    .reduce((s, r) => s + (r.frequency === 'biweekly' ? r.amount * 26 / 12 : r.amount), 0)

  return (
    <>
      {/* Page header */}
      <div className="flex items-start justify-between mb-8">
        <div>
          <h1 className="text-2xl font-extrabold tracking-tight" style={{ color: '#0f172a' }}>
            Dashboard
          </h1>
          <p className="text-sm mt-1" style={{ color: '#5c6473' }}>
            Net worth overview · {formatDateShort(today)}
          </p>
        </div>
      </div>

      {/* Hero */}
      <div className="mb-8">
        <p className="text-[11px] font-bold uppercase tracking-widest mb-2" style={{ color: '#5c6473' }}>
          Net Worth
        </p>
        <div className="text-[56px] font-extrabold leading-none tracking-tight" style={{ color: '#0f172a' }}>
          {formatCents(netWorth)}
        </div>
      </div>

      {/* Stat row */}
      <div className="flex border border-[#d1d5db] rounded-xl bg-white overflow-hidden mb-8">
        <Stat label="Total Assets" value={formatCents(assets.reduce((s, a) => s + a.currentBalance, 0))} />
        <Stat label="Total Liabilities" value={formatCents(Math.abs(liabilities.reduce((s, a) => s + a.currentBalance, 0)))} valueClass="text-[#991b1b]" />
        <Stat label="Monthly Income" value={formatCents(monthlyIncome)} valueClass="text-[#166534]" />
        <Stat label="Monthly Expenses" value={formatCents(monthlyExpenses)} />
        <Stat label="Monthly Net" value={formatCents(monthlyIncome - monthlyExpenses)} valueClass={monthlyIncome >= monthlyExpenses ? 'text-[#166534]' : 'text-[#991b1b]'} last />
      </div>

      {/* Two-column layout */}
      <div className="grid grid-cols-[2fr_1fr] gap-5 mb-8">
        {/* Upcoming events feed */}
        <Panel title="Upcoming Cash Flow" action={<span className="text-xs" style={{ color: '#5c6473' }}>Next 6 months</span>}>
          {upcomingEvents.length === 0 ? (
            <p className="px-5 py-8 text-sm text-center" style={{ color: '#5c6473' }}>
              No upcoming events — add recurring transactions to get started.
            </p>
          ) : (
            upcomingEvents.map((ev) => (
              <div
                key={`${ev.sourceId}-${ev.date}`}
                className="flex items-center gap-3 px-5 py-3.5 border-b border-[#d1d5db] last:border-0"
              >
                <div
                  className={`w-2.5 h-2.5 rounded-full flex-shrink-0 ${
                    ev.type === 'income' ? 'bg-[#166534]' : 'bg-[#991b1b]'
                  }`}
                />
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-semibold truncate" style={{ color: '#0f172a' }}>
                    {ev.label}
                  </div>
                  <div className="text-xs" style={{ color: '#5c6473' }}>
                    {formatDateShort(ev.date)} · {(() => {
                      const d = relativeDays(ev.date)
                      return d === 0 ? 'today' : d === 1 ? 'tomorrow' : `in ${d} days`
                    })()}
                  </div>
                </div>
                <div
                  className={`text-sm font-bold ${ev.type === 'income' ? 'text-[#166534]' : 'text-[#991b1b]'}`}
                >
                  {ev.type === 'income' ? '+' : '−'}{formatCents(ev.amount)}
                </div>
              </div>
            ))
          )}
        </Panel>

        {/* Account summary */}
        <Panel title="Accounts">
          {accounts.length === 0 ? (
            <p className="px-5 py-8 text-sm text-center" style={{ color: '#5c6473' }}>
              No accounts yet.
            </p>
          ) : (
            accounts.slice(0, 7).map((acct) => (
              <div
                key={acct.id}
                className="flex items-center justify-between px-5 py-3 border-b border-[#d1d5db] last:border-0"
              >
                <span className="text-sm font-medium truncate" style={{ color: '#0f172a' }}>
                  {acct.label}
                </span>
                <span
                  className={`text-sm font-bold ml-3 flex-shrink-0 ${acct.currentBalance < 0 ? 'text-[#991b1b]' : ''}`}
                >
                  {formatCents(acct.currentBalance)}
                </span>
              </div>
            ))
          )}
        </Panel>
      </div>

      {/* RSU / ESPP summary */}
      {(rsuGrants.length > 0 || esppPlans.length > 0) && (
        <div className="mb-8">
          <p className="text-[11px] font-bold uppercase tracking-widest mb-3" style={{ color: '#5c6473' }}>
            Equity Snapshot
          </p>
          <div className="grid grid-cols-3 gap-4">
            {rsuGrants.map((grant) => {
              const vested = grant.vestSchedule.filter((v) => v.date <= today).reduce((s, v) => s + v.shares, 0)
              const pct = Math.round((vested / grant.totalShares) * 100)
              return (
                <div
                  key={grant.id}
                  className="bg-white border border-[#d1d5db] rounded-xl p-5"
                >
                  <div className="flex justify-between items-start mb-3">
                    <div>
                      <div className="text-sm font-bold" style={{ color: '#0f172a' }}>{grant.label}</div>
                      <div className="text-xs mt-0.5" style={{ color: '#5c6473' }}>{grant.grantDate.slice(0, 4)}</div>
                    </div>
                    <Badge variant="rsu">{grant.ticker}</Badge>
                  </div>
                  <div className="w-full h-2 rounded-full bg-[#e2e5ea] mb-1.5">
                    <div className="h-2 rounded-full bg-[#3b5fc0]" style={{ width: `${pct}%` }} />
                  </div>
                  <div className="flex justify-between text-[11px]" style={{ color: '#5c6473' }}>
                    <span>{pct}% vested</span>
                    <span>{(vested / 1000).toFixed(0)} / {(grant.totalShares / 1000).toFixed(0)} sh</span>
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      )}
    </>
  )
}

function Stat({
  label,
  value,
  valueClass = '',
  last = false,
}: {
  label: string
  value: string
  valueClass?: string
  last?: boolean
}) {
  return (
    <div className={`flex-1 px-6 py-[18px] ${last ? '' : 'border-r border-[#d1d5db]'}`}>
      <div className="text-[11px] font-bold uppercase tracking-wide mb-1.5" style={{ color: '#5c6473' }}>
        {label}
      </div>
      <div className={`text-[22px] font-bold tracking-tight ${valueClass}`} style={{ color: valueClass ? undefined : '#0f172a' }}>
        {value}
      </div>
    </div>
  )
}
