import { useState } from 'react'
import { useDataStore } from '../store/dataStore'
import { formatCents, formatDate } from '../lib/format'
import { Badge } from '../components/Badge'
import type { RecurringTransaction, OneTimeTransaction, TransactionType, Frequency } from '../types'

type Tab = 'recurring' | 'one-time'

const FREQ_LABEL: Record<Frequency, string> = {
  daily: 'Daily',
  weekly: 'Weekly',
  biweekly: 'Biweekly',
  monthly: 'Monthly',
  quarterly: 'Quarterly',
  annual: 'Annual',
}

export function Transactions() {
  const { recurring, oneTime, accounts } = useDataStore()
  const [tab, setTab] = useState<Tab>('recurring')
  const [filter, setFilter] = useState<TransactionType | 'all'>('all')

  const accountLabel = (id: string) => accounts.find((a) => a.id === id)?.label ?? id

  const filteredRecurring = recurring.filter(
    (r) => filter === 'all' || r.type === filter,
  )
  const filteredOneTime = [...oneTime]
    .filter((t) => filter === 'all' || t.type === filter)
    .sort((a, b) => b.date.localeCompare(a.date))

  return (
    <>
      <div className="flex items-start justify-between mb-8">
        <div>
          <h1 className="text-2xl font-extrabold tracking-tight" style={{ color: '#0f172a' }}>Transactions</h1>
          <p className="text-sm mt-1" style={{ color: '#5c6473' }}>Recurring income · expenses · one-time events</p>
        </div>
        <button
          className="px-4 py-2 rounded-lg text-sm font-medium text-white"
          style={{ background: '#3b5fc0' }}
        >
          + Add
        </button>
      </div>

      {/* Tabs + filter */}
      <div className="flex items-center gap-4 mb-5">
        <div className="flex border border-[#d1d5db] rounded-lg overflow-hidden">
          {(['recurring', 'one-time'] as Tab[]).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`px-4 py-2 text-sm font-medium capitalize ${tab === t ? 'text-white' : ''}`}
              style={{
                background: tab === t ? '#3b5fc0' : '#fff',
                color: tab === t ? '#fff' : '#0f172a',
              }}
            >
              {t === 'recurring' ? 'Recurring' : 'One-time'}
            </button>
          ))}
        </div>
        <div className="flex border border-[#d1d5db] rounded-lg overflow-hidden ml-auto">
          {(['all', 'income', 'expense'] as const).map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className="px-3 py-2 text-sm capitalize"
              style={{
                background: filter === f ? '#eef1fb' : '#fff',
                color: filter === f ? '#3b5fc0' : '#0f172a',
                fontWeight: filter === f ? 600 : 400,
              }}
            >
              {f}
            </button>
          ))}
        </div>
      </div>

      {/* Recurring list */}
      {tab === 'recurring' && (
        <div className="bg-white border border-[#d1d5db] rounded-xl overflow-hidden">
          {filteredRecurring.length === 0 ? (
            <p className="px-5 py-10 text-sm text-center" style={{ color: '#5c6473' }}>No recurring transactions.</p>
          ) : (
            filteredRecurring.map((r) => (
              <RecurringRow key={r.id} r={r} accountLabel={accountLabel(r.accountId)} />
            ))
          )}
        </div>
      )}

      {/* One-time list */}
      {tab === 'one-time' && (
        <div className="bg-white border border-[#d1d5db] rounded-xl overflow-hidden">
          {filteredOneTime.length === 0 ? (
            <p className="px-5 py-10 text-sm text-center" style={{ color: '#5c6473' }}>No one-time transactions.</p>
          ) : (
            filteredOneTime.map((t) => (
              <OneTimeRow key={t.id} t={t} accountLabel={accountLabel(t.accountId)} />
            ))
          )}
        </div>
      )}
    </>
  )
}

function RecurringRow({ r, accountLabel }: { r: RecurringTransaction; accountLabel: string }) {
  return (
    <div className="flex items-center gap-3.5 px-5 py-3.5 border-b border-[#d1d5db] last:border-0">
      <div
        className={`w-2.5 h-2.5 rounded-full flex-shrink-0 ${r.type === 'income' ? 'bg-[#166534]' : 'bg-[#991b1b]'}`}
      />
      <div className="flex-1 min-w-0">
        <div className="text-sm font-semibold" style={{ color: '#0f172a' }}>{r.label}</div>
        <div className="text-xs mt-0.5" style={{ color: '#5c6473' }}>{r.category} · {accountLabel}</div>
      </div>
      <div className="text-xs w-20 text-right" style={{ color: '#5c6473' }}>
        {FREQ_LABEL[r.frequency]}
      </div>
      <div className={`text-sm font-bold w-24 text-right ${r.type === 'income' ? 'text-[#166534]' : 'text-[#991b1b]'}`}>
        {r.type === 'income' ? '+' : '−'}{formatCents(r.amount)}
      </div>
    </div>
  )
}

function OneTimeRow({ t, accountLabel }: { t: OneTimeTransaction; accountLabel: string }) {
  return (
    <div className="flex items-center gap-3.5 px-5 py-3.5 border-b border-[#d1d5db] last:border-0">
      <div
        className={`w-2.5 h-2.5 rounded-full flex-shrink-0 ${t.type === 'income' ? 'bg-[#166534]' : 'bg-[#991b1b]'}`}
      />
      <div className="flex-1 min-w-0">
        <div className="text-sm font-semibold" style={{ color: '#0f172a' }}>{t.label}</div>
        <div className="text-xs mt-0.5" style={{ color: '#5c6473' }}>{t.category} · {accountLabel}</div>
      </div>
      <div className="text-xs w-28 text-right" style={{ color: '#5c6473' }}>{formatDate(t.date)}</div>
      <div className={`text-sm font-bold w-24 text-right ${t.type === 'income' ? 'text-[#166534]' : 'text-[#991b1b]'}`}>
        {t.type === 'income' ? '+' : '−'}{formatCents(t.amount)}
      </div>
    </div>
  )
}
