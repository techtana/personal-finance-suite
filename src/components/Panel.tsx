interface PanelProps {
  title?: string
  action?: React.ReactNode
  children: React.ReactNode
  className?: string
  padded?: boolean
}

export function Panel({ title, action, children, className = '', padded = false }: PanelProps) {
  return (
    <div className={`bg-white border border-[#d1d5db] rounded-xl overflow-hidden ${className}`}>
      {title && (
        <div className="px-5 py-4 border-b border-[#d1d5db] flex items-center justify-between">
          <span className="text-sm font-bold">{title}</span>
          {action}
        </div>
      )}
      <div className={padded ? 'p-5' : ''}>{children}</div>
    </div>
  )
}
