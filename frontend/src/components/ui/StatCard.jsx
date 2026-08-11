import './ui.css'
import Sparkline from './Sparkline'

/**
 * 统一统计卡（KPI）。点击可跳转/联动。
 * props: label, value, unit, trend(字符串如 "+12%"), trendUp(bool),
 *        trendLabel, icon, accent(色值), sub(无趋势时的副文案), spark(数组), onClick
 */
export default function StatCard({
  label,
  value,
  unit,
  trend,
  trendUp = true,
  trendLabel,
  icon,
  accent = '#5b5bd6',
  sub,
  spark,
  onClick,
  style,
}) {
  return (
    <button
      type="button"
      className="ui-kpi"
      style={{ '--kpi-accent': accent, ...style }}
      onClick={onClick}
      disabled={!onClick}
      aria-label={label}
    >
      <div className="ui-kpi-top">
        <span className="ui-kpi-label">{label}</span>
        {icon ? <span className="ui-kpi-icon">{icon}</span> : null}
      </div>
      <div className="ui-kpi-value">
        {value}
        {unit ? <span className="unit">{unit}</span> : null}
      </div>
      <div className="ui-kpi-foot">
        {trend != null ? (
          <span className={`ui-kpi-trend ${trendUp ? 'up' : 'down'}`}>
            {trend}
            {trendLabel ? <span className="lbl">{trendLabel}</span> : null}
          </span>
        ) : sub ? (
          <span className="ui-kpi-sub">{sub}</span>
        ) : (
          <span />
        )}
        {spark ? <Sparkline color={accent} values={spark} id={`kpi-spark-${label}`} /> : null}
      </div>
    </button>
  )
}
