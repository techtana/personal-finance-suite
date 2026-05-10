type Variant = 'ok' | 'warn' | 'neutral' | 'income' | 'rsu' | 'espp' | 'blue'

const styles: Record<Variant, string> = {
  ok:      'bg-[#bbf7d0] text-[#166534]',
  warn:    'bg-[#fed7aa] text-[#9a3412]',
  neutral: 'bg-[#e2e5ea] text-[#5c6473]',
  income:  'bg-[#bbf7d0] text-[#166534]',
  rsu:     'bg-[#dbeafe] text-[#1d4ed8]',
  espp:    'bg-[#ede9fe] text-[#6d28d9]',
  blue:    'bg-[#dbeafe] text-[#1d4ed8]',
}

interface BadgeProps {
  variant?: Variant
  children: React.ReactNode
  className?: string
}

export function Badge({ variant = 'neutral', children, className = '' }: BadgeProps) {
  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-semibold ${styles[variant]} ${className}`}
    >
      {children}
    </span>
  )
}
