import { useDataStore } from '../store/dataStore'
import { formatCents, formatDate, formatShares, todayISO } from '../lib/format'
import { Badge } from '../components/Badge'
import type { RsuGrant, EsppPlan, PurchasePeriod } from '../types'

export function Equity() {
  const { rsuGrants, esppPlans } = useDataStore()
  const today = todayISO()

  const totalVestedShares = rsuGrants.reduce((s, g) => {
    const vested = g.vestSchedule.filter((v) => v.date <= today).reduce((a, v) => a + v.shares, 0)
    return s + vested
  }, 0)

  return (
    <>
      <div className="flex items-start justify-between mb-8">
        <div>
          <h1 className="text-2xl font-extrabold tracking-tight" style={{ color: '#0f172a' }}>Equity</h1>
          <p className="text-sm mt-1" style={{ color: '#5c6473' }}>RSU grants · ESPP plans · vesting schedule</p>
        </div>
        <button
          className="px-4 py-2 rounded-lg text-sm font-medium text-white"
          style={{ background: '#3b5fc0' }}
        >
          + Add Grant
        </button>
      </div>

      {/* RSU section */}
      {rsuGrants.length > 0 && (
        <>
          <p className="text-[11px] font-bold uppercase tracking-widest mb-3" style={{ color: '#5c6473' }}>
            RSU Grants
          </p>
          <div className="grid grid-cols-3 gap-4 mb-8">
            {rsuGrants.map((grant) => (
              <RsuCard key={grant.id} grant={grant} today={today} />
            ))}
          </div>

          {/* Vest schedule table */}
          <div className="bg-white border border-[#d1d5db] rounded-xl overflow-hidden mb-8">
            <div className="px-5 py-4 border-b border-[#d1d5db] flex items-center justify-between">
              <span className="text-sm font-bold" style={{ color: '#0f172a' }}>Upcoming Vests</span>
              <span className="text-xs" style={{ color: '#5c6473' }}>Next 24 months</span>
            </div>
            {rsuGrants.flatMap((g) =>
              g.vestSchedule
                .filter((v) => v.date > today)
                .slice(0, 4)
                .map((v) => ({ grant: g, vest: v })),
            )
              .sort((a, b) => a.vest.date.localeCompare(b.vest.date))
              .slice(0, 10)
              .map(({ grant, vest }, i) => (
                <div
                  key={`${grant.id}-${vest.date}`}
                  className="flex items-center gap-4 px-5 py-3.5 border-b border-[#d1d5db] last:border-0"
                >
                  <div className="w-2.5 h-2.5 rounded-full bg-[#1d4ed8] flex-shrink-0" />
                  <div className="flex-1">
                    <div className="text-sm font-semibold" style={{ color: '#0f172a' }}>{grant.label}</div>
                    <div className="text-xs" style={{ color: '#5c6473' }}>{formatDate(vest.date)}</div>
                  </div>
                  <Badge variant="rsu">{grant.ticker}</Badge>
                  <div className="text-sm font-bold w-20 text-right" style={{ color: '#0f172a' }}>
                    {formatShares(vest.shares)} sh
                  </div>
                  <div className="text-sm font-bold w-28 text-right text-[#166534]">
                    +{formatCents(Math.round((vest.shares / 1000) * grant.priceAtGrant * (1 - grant.withholdingRate / 10000)))}
                  </div>
                </div>
              ))}
          </div>
        </>
      )}

      {/* ESPP section */}
      {esppPlans.length > 0 && (
        <>
          <p className="text-[11px] font-bold uppercase tracking-widest mb-3" style={{ color: '#5c6473' }}>
            ESPP Plans
          </p>
          {esppPlans.map((plan) => (
            <EsppCard key={plan.id} plan={plan} today={today} />
          ))}
        </>
      )}

      {rsuGrants.length === 0 && esppPlans.length === 0 && (
        <div className="text-center py-20 text-sm" style={{ color: '#5c6473' }}>
          No equity data yet. Add an RSU grant or ESPP plan to get started.
        </div>
      )}
    </>
  )
}

function RsuCard({ grant, today }: { grant: RsuGrant; today: string }) {
  const vested = grant.vestSchedule.filter((v) => v.date <= today).reduce((s, v) => s + v.shares, 0)
  const pct = Math.round((vested / grant.totalShares) * 100)
  const nextVest = grant.vestSchedule.find((v) => v.date > today)
  const netValue = Math.round(
    (grant.totalShares / 1000) * grant.priceAtGrant * (1 - grant.withholdingRate / 10000),
  )

  return (
    <div className="bg-white border border-[#d1d5db] rounded-xl p-5">
      <div className="flex justify-between items-start mb-3.5">
        <div>
          <div className="text-sm font-bold" style={{ color: '#0f172a' }}>{grant.label}</div>
          <div className="text-xs mt-0.5" style={{ color: '#5c6473' }}>Grant date {formatDate(grant.grantDate)}</div>
        </div>
        <Badge variant="rsu">{grant.ticker}</Badge>
      </div>

      <div className="w-full h-2 rounded-full bg-[#e2e5ea] mb-1.5">
        <div className="h-2 rounded-full bg-[#3b5fc0]" style={{ width: `${pct}%` }} />
      </div>
      <div className="flex justify-between text-[11px] mb-4" style={{ color: '#5c6473' }}>
        <span>{pct}% vested</span>
        <span>{formatShares(vested)} / {formatShares(grant.totalShares)} sh</span>
      </div>

      <div className="text-xs mb-1" style={{ color: '#5c6473' }}>Est. net value (at grant price)</div>
      <div className="text-2xl font-extrabold tracking-tight mb-3" style={{ color: '#0f172a' }}>
        {formatCents(netValue)}
      </div>

      {nextVest && (
        <div className="pt-2.5 border-t border-[#d1d5db] text-xs" style={{ color: '#5c6473' }}>
          Next vest: {formatShares(nextVest.shares)} sh on {formatDate(nextVest.date)}
        </div>
      )}
    </div>
  )
}

function EsppCard({ plan, today }: { plan: EsppPlan; today: string }) {
  const currentPeriod = plan.purchasePeriods.find((p) => p.status === 'current')
  const completed = plan.purchasePeriods.filter((p) => p.status === 'completed')

  return (
    <div className="bg-white border border-[#d1d5db] rounded-xl overflow-hidden mb-5">
      <div className="px-5 py-4 border-b border-[#d1d5db] flex items-center justify-between">
        <div>
          <span className="text-sm font-bold" style={{ color: '#0f172a' }}>{plan.label}</span>
          <span className="ml-3 text-xs" style={{ color: '#5c6473' }}>
            {plan.discountRate / 100}% discount{plan.hasLookback ? ' · lookback' : ''}
          </span>
        </div>
        <Badge variant="espp">{plan.ticker}</Badge>
      </div>

      <div className="divide-y divide-[#d1d5db]">
        {plan.purchasePeriods.map((period) => (
          <PeriodRow key={period.id} period={period} today={today} />
        ))}
      </div>
    </div>
  )
}

function PeriodRow({ period, today }: { period: PurchasePeriod; today: string }) {
  const statusColors = {
    completed: { dot: 'bg-[#166534]', badge: 'ok' as const },
    current:   { dot: 'bg-[#3b5fc0]', badge: 'blue' as const },
    future:    { dot: 'bg-[#e2e5ea]', badge: 'neutral' as const },
  }
  const { dot, badge } = statusColors[period.status]

  return (
    <div className="flex items-center gap-4 px-5 py-3.5">
      <div className={`w-2 h-2 rounded-full flex-shrink-0 ${dot}`} />
      <div className="flex-1">
        <div className="text-sm font-medium" style={{ color: '#0f172a' }}>
          {formatDate(period.startDate)} – {formatDate(period.endDate)}
        </div>
        {period.purchaseDatePrice && (
          <div className="text-xs" style={{ color: '#5c6473' }}>
            Purchase price {formatCents(period.purchasePrice)} · FMV {formatCents(period.purchaseDatePrice)}
          </div>
        )}
      </div>
      <Badge variant={badge}>{period.status}</Badge>
      <div className="text-sm font-bold text-right w-28" style={{ color: '#0f172a' }}>
        {period.sharesEstimated} sh
      </div>
      <div className="text-sm font-bold text-right w-28 text-[#166534]">
        {formatCents(period.estimatedPurchaseAmount)}
      </div>
    </div>
  )
}
