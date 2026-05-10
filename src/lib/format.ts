// Formatting utilities — all money values are integer cents.

export function formatCents(
  cents: number,
  opts: { showSign?: boolean; compact?: boolean; currency?: string; locale?: string } = {},
): string {
  const { showSign = false, compact = false, currency = 'USD', locale = 'en-US' } = opts
  const value = cents / 100
  const formatted = new Intl.NumberFormat(locale, {
    style: 'currency',
    currency,
    notation: compact ? 'compact' : 'standard',
    maximumFractionDigits: compact ? 1 : 2,
  }).format(Math.abs(value))

  if (showSign && cents !== 0) return (cents > 0 ? '+' : '−') + formatted
  if (cents < 0) return '−' + formatted
  return formatted
}

export function formatShares(milliShares: number): string {
  const shares = milliShares / 1000
  return shares % 1 === 0 ? `${shares}` : shares.toFixed(3)
}

export function formatPercent(
  hundredths: number,
  opts: { showSign?: boolean } = {},
): string {
  const value = hundredths / 100
  const s = value.toFixed(2) + '%'
  if (opts.showSign && hundredths > 0) return '+' + s
  return s
}

export function formatDate(iso: string, locale = 'en-US'): string {
  const [y, m, d] = iso.split('-').map(Number)
  return new Date(Date.UTC(y, m - 1, d)).toLocaleDateString(locale, {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    timeZone: 'UTC',
  })
}

export function formatDateShort(iso: string, locale = 'en-US'): string {
  const [y, m, d] = iso.split('-').map(Number)
  return new Date(Date.UTC(y, m - 1, d)).toLocaleDateString(locale, {
    month: 'short',
    day: 'numeric',
    timeZone: 'UTC',
  })
}

export function todayISO(): string {
  return new Date().toISOString().slice(0, 10)
}

export function addMonthsISO(iso: string, n: number): string {
  const [y, m, d] = iso.split('-').map(Number)
  const date = new Date(Date.UTC(y, m - 1 + n, d))
  return date.toISOString().slice(0, 10)
}

export function relativeDays(iso: string): number {
  const target = new Date(iso).getTime()
  const now = new Date().setHours(0, 0, 0, 0)
  return Math.round((target - now) / 86_400_000)
}
