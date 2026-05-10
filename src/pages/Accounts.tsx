import { useState, useMemo } from 'react'
import { useDataStore } from '../store/dataStore'
import { useAuthStore } from '../store/authStore'
import { formatCents, formatDate, todayISO } from '../lib/format'
import { Badge } from '../components/Badge'
import { Sparkline } from '../components/Sparkline'
import type { Account, AccountType, Snapshot } from '../types'

const TYPE_GROUPS: { label: string; types: AccountType[] }[] = [
  { label: 'Banking',     types: ['checking', 'savings'] },
  { label: 'Investments', types: ['brokerage', '401k', 'ira'] },
  { label: 'Property',    types: ['property'] },
  { label: 'Liabilities', types: ['loan'] },
]

const TOP_BORDER: Partial<Record<AccountType, string>> = {
  checking: '#3b82f6',
  savings:  '#3b82f6',
  brokerage:'#1d4ed8',
  '401k':   '#166534',
  ira:      '#6d28d9',
  property: '#f97316',
  loan:     '#991b1b',
}

export function Accounts() {
  const { accounts, snapshots, saveAccounts, saveSnapshots } = useDataStore()
  const { driveClient } = useAuthStore()
  const [showAdd, setShowAdd] = useState(false)
  const [reconTarget, setReconTarget] = useState<Account | null>(null)
  const [newBalance, setNewBalance] = useState('')
  const [reconNote, setReconNote] = useState('')

  const netWorth = accounts.reduce((s, a) => s + a.currentBalance, 0)

  const snapshotsByAccount = useMemo(() => {
    const m: Record<string, Snapshot[]> = {}
    for (const s of snapshots) {
      if (!m[s.accountId]) m[s.accountId] = []
      m[s.accountId].push(s)
    }
    // sort ascending by date
    for (const id of Object.keys(m)) {
      m[id].sort((a, b) => a.date.localeCompare(b.date))
    }
    return m
  }, [snapshots])

  async function handleReconcile() {
    if (!reconTarget || !driveClient) return
    const cents = Math.round(parseFloat(newBalance) * 100)
    if (isNaN(cents)) return

    const today = todayISO()
    const snap: Snapshot = {
      id: `snap_${reconTarget.id}_${today}`,
      accountId: reconTarget.id,
      date: today,
      balance: cents,
      note: reconNote || undefined,
      createdAt: today,
    }

    const updatedAccounts = accounts.map((a) =>
      a.id === reconTarget.id ? { ...a, currentBalance: cents, updatedAt: today } : a,
    )
    const updatedSnapshots = [...snapshots, snap]

    await saveAccounts(driveClient, updatedAccounts)
    await saveSnapshots(driveClient, updatedSnapshots)

    setReconTarget(null)
    setNewBalance('')
    setReconNote('')
  }

  return (
    <>
      <div className="flex items-start justify-between mb-8">
        <div>
          <h1 className="text-2xl font-extrabold tracking-tight" style={{ color: '#0f172a' }}>Accounts</h1>
          <p className="text-sm mt-1" style={{ color: '#5c6473' }}>Assets · balances · reconciliation</p>
        </div>
        <button
          onClick={() => setShowAdd(true)}
          className="flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-medium text-white"
          style={{ background: '#3b5fc0' }}
        >
          + Add Account
        </button>
      </div>

      {/* Net worth hero */}
      <div className="mb-8">
        <p className="text-[11px] font-bold uppercase tracking-widest mb-2" style={{ color: '#5c6473' }}>Net Worth</p>
        <div className="text-[56px] font-extrabold leading-none tracking-tight" style={{ color: '#0f172a' }}>
          {formatCents(netWorth)}
        </div>
      </div>

      {/* Account groups */}
      {TYPE_GROUPS.map(({ label, types }) => {
        const group = accounts.filter((a) => types.includes(a.type))
        if (group.length === 0) return null

        const groupTotal = group.reduce((s, a) => s + a.currentBalance, 0)
        const cols = group.length >= 3 ? 3 : group.length

        return (
          <div key={label} className="mb-8">
            {/* Section header */}
            <div
              className="flex justify-between items-center mb-3 pb-2.5"
              style={{ borderBottom: '2px solid #b5bac3' }}
            >
              <span className="text-[11px] font-bold uppercase tracking-widest" style={{ color: '#5c6473' }}>
                {label}
              </span>
              <span
                className={`text-base font-bold ${groupTotal < 0 ? 'text-[#991b1b]' : ''}`}
                style={{ color: groupTotal < 0 ? undefined : '#0f172a' }}
              >
                {groupTotal < 0 ? '−' : ''}{formatCents(Math.abs(groupTotal))}
              </span>
            </div>

            {/* Cards */}
            <div
              className="grid gap-4"
              style={{ gridTemplateColumns: `repeat(${cols}, 1fr)` }}
            >
              {group.map((acct) => {
                const snaps = snapshotsByAccount[acct.id] ?? []
                const sparkPoints = snaps.slice(-8).map((s) => ({ value: s.balance }))
                const borderColor = TOP_BORDER[acct.type] ?? '#6b7280'

                return (
                  <div
                    key={acct.id}
                    className="bg-white border border-[#d1d5db] rounded-xl p-[18px] flex flex-col"
                    style={{ borderTop: `3px solid ${borderColor}` }}
                  >
                    {/* Header */}
                    <div className="flex justify-between items-start mb-3">
                      <div>
                        <div className="text-sm font-bold" style={{ color: '#0f172a' }}>{acct.label}</div>
                        <div className="text-[11px] mt-0.5" style={{ color: '#5c6473' }}>
                          {acct.type} · {acct.institution}
                        </div>
                      </div>
                      <Badge variant="neutral">
                        {formatDate(acct.updatedAt)}
                      </Badge>
                    </div>

                    {/* Sparkline */}
                    {sparkPoints.length >= 2 && (
                      <div className="mb-1">
                        <Sparkline points={sparkPoints} color={borderColor} height={36} />
                      </div>
                    )}

                    {/* Balance */}
                    <div
                      className={`text-2xl font-extrabold tracking-tight mt-1.5 mb-0.5 ${acct.currentBalance < 0 ? 'text-[#991b1b]' : ''}`}
                      style={{ color: acct.currentBalance < 0 ? undefined : '#0f172a' }}
                    >
                      {formatCents(acct.currentBalance)}
                    </div>
                    <div className="text-[11px] mb-3" style={{ color: '#5c6473' }}>
                      Updated {formatDate(acct.updatedAt)}
                    </div>

                    {/* Actions */}
                    <div className="flex gap-2 mt-auto pt-3.5 border-t border-[#d1d5db]">
                      <button
                        onClick={() => { setReconTarget(acct); setNewBalance('') }}
                        className="flex-1 px-3 py-2 rounded-lg text-xs font-semibold border border-[#d1d5db] bg-white hover:bg-[#f4f6f9] transition-colors"
                        style={{ color: '#0f172a' }}
                      >
                        {acct.type === 'property' ? 'Update Value' : 'Reconcile'}
                      </button>
                      <button
                        className="px-3 py-2 rounded-lg text-xs font-semibold border border-[#d1d5db] bg-white hover:bg-[#f4f6f9] transition-colors"
                        style={{ color: '#5c6473' }}
                      >
                        ···
                      </button>
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        )
      })}

      {accounts.length === 0 && (
        <div className="text-center py-20 text-sm" style={{ color: '#5c6473' }}>
          No accounts yet. Add your first account to get started.
        </div>
      )}

      {/* Reconcile modal */}
      {reconTarget && (
        <Modal title={`Reconcile · ${reconTarget.label}`} onClose={() => setReconTarget(null)}>
          <div className="mb-4 p-4 rounded-lg" style={{ background: '#f4f6f9' }}>
            <div className="text-xs font-bold uppercase tracking-wide mb-1" style={{ color: '#5c6473' }}>
              Current Balance
            </div>
            <div className="text-xl font-bold" style={{ color: '#0f172a' }}>
              {formatCents(reconTarget.currentBalance)}
            </div>
          </div>
          <FormField label="Actual Balance ($)">
            <input
              type="number"
              step="0.01"
              value={newBalance}
              onChange={(e) => setNewBalance(e.target.value)}
              className="w-full px-3 py-2 border border-[#d1d5db] rounded-lg text-sm"
              placeholder="0.00"
              autoFocus
            />
          </FormField>
          <FormField label="Note (optional)">
            <input
              value={reconNote}
              onChange={(e) => setReconNote(e.target.value)}
              className="w-full px-3 py-2 border border-[#d1d5db] rounded-lg text-sm"
              placeholder="e.g. Market correction, manual adjustment"
            />
          </FormField>
          <div className="flex gap-2 justify-end mt-6 pt-4 border-t border-[#d1d5db]">
            <button
              onClick={() => setReconTarget(null)}
              className="px-4 py-2 rounded-lg text-sm border border-[#d1d5db] bg-white"
            >
              Cancel
            </button>
            <button
              onClick={handleReconcile}
              className="px-4 py-2 rounded-lg text-sm text-white font-semibold"
              style={{ background: '#3b5fc0' }}
            >
              Save
            </button>
          </div>
        </Modal>
      )}

      {/* Add account modal (simplified) */}
      {showAdd && (
        <Modal title="Add Account" onClose={() => setShowAdd(false)}>
          <p className="text-sm mb-4" style={{ color: '#5c6473' }}>
            Account creation coming soon — for now edit your <code>accounts.json</code> in Drive.
          </p>
          <div className="flex justify-end">
            <button onClick={() => setShowAdd(false)} className="px-4 py-2 rounded-lg text-sm border border-[#d1d5db]">
              Close
            </button>
          </div>
        </Modal>
      )}
    </>
  )
}

function Modal({ title, onClose, children }: { title: string; onClose: () => void; children: React.ReactNode }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center" style={{ background: 'rgba(0,0,0,.4)' }}>
      <div className="bg-white rounded-2xl shadow-2xl p-7 w-full max-w-md">
        <div className="flex justify-between items-center mb-5 pb-3.5 border-b border-[#d1d5db]">
          <span className="text-base font-bold" style={{ color: '#0f172a' }}>{title}</span>
          <button onClick={onClose} className="text-xl leading-none" style={{ color: '#5c6473' }}>✕</button>
        </div>
        {children}
      </div>
    </div>
  )
}

function FormField({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="mb-4">
      <label className="block text-[11px] font-semibold uppercase tracking-wide mb-1.5" style={{ color: '#5c6473' }}>
        {label}
      </label>
      {children}
    </div>
  )
}
