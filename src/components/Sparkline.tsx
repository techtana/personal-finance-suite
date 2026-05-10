interface Point {
  value: number
}

interface SparklineProps {
  points: Point[]
  color?: string
  height?: number
  width?: number
  dashed?: boolean
}

export function Sparkline({
  points,
  color = '#3b82f6',
  height = 36,
  width = 160,
  dashed = false,
}: SparklineProps) {
  if (points.length < 2) return null

  const values = points.map((p) => p.value)
  const min = Math.min(...values)
  const max = Math.max(...values)
  const range = max - min || 1

  const toX = (i: number) => (i / (points.length - 1)) * width
  const toY = (v: number) => height - ((v - min) / range) * height * 0.9 - height * 0.05

  const pts = points.map((p, i) => `${toX(i).toFixed(1)},${toY(p.value).toFixed(1)}`).join(' ')
  const last = points[points.length - 1]
  const lx = toX(points.length - 1)
  const ly = toY(last.value)

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      width="100%"
      height={height}
      preserveAspectRatio="none"
      aria-hidden
    >
      <polyline
        points={pts}
        fill="none"
        stroke={color}
        strokeWidth="1.8"
        strokeDasharray={dashed ? '4 3' : undefined}
      />
      <circle cx={lx} cy={ly} r="3" fill={color} />
    </svg>
  )
}
