import { useDataStore } from '../store/dataStore'
import { formatCents, formatDate, formatPercent } from '../lib/format'
import { Panel } from '../components/Panel'
import type { Loan } from '../types'

export function Loans() {
  const { loans, accounts } = useDataStore()

  const linkedAccount = (id: string) => accounts.find((a) => a.id === id)

  return (
    <>
      <div className="flex items-start justify-between mb-8">
        <div>
          <h1 className="text-2xl font-extrabold tracking-tight" style={{ color: '#0f172a' }}>Loans</h1>
          <p className="text-sm mt-1" style={{ color: '#5c6473' }}>Mortgage · amortization · payoff schedule</p>
        </div>
        <button
          className="px-4 py-2 rounded-lg text-sm font-medium text-white"
          style={{ background: '#3b5fc0' }}
        >
          + Add Loan
        </button>
      </div>

      {loans.length === 0 ? (
        <div className="text-center py-20 text-sm" style={{ color: '#5c6473' }}>
          No loans tracked. Add a mortgage or other loan to model payoff progress.
        </div>
      ) : (
        loans.map((loan) => <LoanCard key={loan.id} loan={loan} assetLabel={linkedAccount(loan.linkedAccountId)?.label} />)
      )}
    </>
  )
}

function LoanCard({ loan, assetLabel }: { loan: Loan; assetLabel?: string }) {
  const principalPaid = loan.originalPrincipal - loan.currentBalance
  const paidPct = Math.round((principalPaid / loan.originalPrincipal) * 100)
  const ratePct = loan.interestRateBps / 10000        // basis points × 10 → percent
  const monthsRemaining = Math.round(loan.currentBalance / loan.monthlyPayment)

  return (
    <div className="bg-white border border-[#d1d5db] rounded-xl overflow-hidden mb-5">
      <div className="px-5 py-4 border-b border-[#d1d5db] flex items-center justify-between"
           style={{ borderTop: '3px solid #991b1b' }}>
        <div>
          <div className="text-sm font-bold" style={{ color: '#0f172a' }}>{loan.label}</div>
          <div className="text-xs mt-0.5" style={{ color: '#5c6473' }}>
            {assetLabel ? `Linked to ${assetLabel}` : loan.linkedAccountId}
          </div>
        </div>
        <div className="text-right">
          <div className="text-xl font-extrabold text-[#991b1b]">
            {formatCents(loan.currentBalance)}
          </div>
          <div className="text-xs" style={{ color: '#5c6473' }}>outstanding balance</div>
        </div>
      </div>

      <div className="px-5 py-4">
        {/* Stat row */}
        <div className="grid grid-cols-4 gap-4 mb-5">
          <LoanStat label="Original Principal" value={formatCents(loan.originalPrincipal)} />
          <LoanStat label="Interest Rate" value={`${ratePct.toFixed(3)}%`} />
          <LoanStat label="Monthly Payment" value={formatCents(loan.monthlyPayment)} />
          <LoanStat label="Start Date" value={formatDate(loan.startDate)} />
        </div>

        {/* Payoff progress */}
        <div className="mb-1 flex justify-between text-xs" style={{ color: '#5c6473' }}>
          <span>Principal paid</span>
          <span className="font-semibold">{paidPct}% · {formatCents(principalPaid)} paid</span>
        </div>
        <div className="w-full h-3 rounded-full bg-[#e2e5ea] mb-1">
          <div className="h-3 rounded-full bg-[#991b1b]" style={{ width: `${paidPct}%` }} />
        </div>
        <div className="flex justify-between text-xs mt-1" style={{ color: '#5c6473' }}>
          <span>{formatCents(loan.currentBalance)} remaining</span>
          <span>~{monthsRemaining} mo to payoff</span>
        </div>

        {/* Amortization note */}
        <div className="mt-4 pt-4 border-t border-[#d1d5db] text-xs" style={{ color: '#5c6473' }}>
          {loan.note ?? `${loan.termMonths / 12}-yr fixed · Payoff ~${new Date(loan.startDate).getFullYear() + loan.termMonths / 12}`}
        </div>
      </div>
    </div>
  )
}

function LoanStat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-[11px] font-bold uppercase tracking-wide mb-1" style={{ color: '#5c6473' }}>{label}</div>
      <div className="text-sm font-bold" style={{ color: '#0f172a' }}>{value}</div>
    </div>
  )
}
