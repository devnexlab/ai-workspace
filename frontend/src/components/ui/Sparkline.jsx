/**
 * 轻量 Sparkline（SVG 面积折线），用于 KPI 卡趋势。
 */
const W = 72
const H = 28
const PAD = 3

function buildPath(values, width = W, height = H, pad = PAD) {
  const nums = (values || []).map((v) => Number(v) || 0)
  if (nums.length < 2) {
    const y = height - pad
    return `M0,${y} L${width},${y}`
  }
  const min = Math.min(...nums)
  const max = Math.max(...nums)
  const span = max - min
  const yOf = (v) => (span <= 0 ? height - pad : pad + (1 - (v - min) / span) * (height - pad * 2))
  const step = width / (nums.length - 1)
  return nums
    .map((v, i) => `${i === 0 ? 'M' : 'L'}${(i * step).toFixed(1)},${yOf(v).toFixed(1)}`)
    .join(' ')
}

export default function Sparkline({ color = '#5b5bd6', values, id }) {
  const path = buildPath(values)
  const hasSignal = (values || []).some((v) => Number(v) > 0)
  return (
    <svg className="ui-spark" viewBox={`0 0 ${W} ${H}`} aria-hidden width="72" height="28">
      <defs>
        <linearGradient id={id} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity={hasSignal ? 0.3 : 0.08} />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={`${path} L${W},${H} L0,${H} Z`} fill={`url(#${id})`} />
      <path
        d={path}
        fill="none"
        stroke={color}
        strokeWidth="1.5"
        strokeLinejoin="round"
        strokeLinecap="round"
        opacity={hasSignal ? 1 : 0.35}
      />
    </svg>
  )
}
