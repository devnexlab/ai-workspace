import { useState, useEffect, useMemo } from 'react'
import { Spin, message, Empty } from 'antd'
import {
  FireOutlined, FileTextOutlined, VideoCameraOutlined, TeamOutlined,
  RocketOutlined, BulbOutlined, UserAddOutlined, UserOutlined,
  RiseOutlined, BookOutlined,
} from '@ant-design/icons'
import {
  ResponsiveContainer, AreaChart, Area, XAxis, YAxis, CartesianGrid,
  Tooltip, PieChart, Pie, Cell,
} from 'recharts'
import { useNavigate } from 'react-router-dom'
import { dashboardApi } from '../../api'
import './Dashboard.css'

const intentionLabels = { high: '高意向', medium: '中意向', low: '低意向', closed: '已成交' }

const PLATFORM_META = {
  xiaohongshu: { label: '小红书', color: '#00b884' },
  toutiao_hot: { label: '今日头条', color: '#ff3b5c' },
  weibo_hot: { label: '微博热搜', color: '#ff9500' },
  baidu_hot: { label: '百度热榜', color: '#3b82f6' },
  zhihu_hot: { label: '知乎热榜', color: '#00bbf9' },
  douyin: { label: '抖音', color: '#5b5bd6' },
  bilibili: { label: 'B站', color: '#f15bb5' },
}

const SCRIPT_STATUS_META = {
  draft: { label: '草稿', color: '#5b5bd6' },
  reviewing: { label: '审核中', color: '#ff9500' },
  approved: { label: '已通过', color: '#9b5de5' },
  used: { label: '已发布', color: '#00b884' },
  rejected: { label: '已退回', color: '#ff3b5c' },
}

const SCRIPT_TAG = {
  draft: { label: '草稿', cls: 'pending' },
  reviewing: { label: '待审核', cls: 'pending' },
  approved: { label: '已通过', cls: 'published' },
  used: { label: '已发布', cls: 'published' },
  rejected: { label: '已退回', cls: 'hot' },
}

const INTENTION_META = {
  high: { label: '高意向', color: '#ff3b5c' },
  medium: { label: '中意向', color: '#ff9500' },
  low: { label: '低意向', color: '#9b9bb0' },
  closed: { label: '已成交', color: '#00b884' },
}

const PIPELINE_COLORS = [
  'linear-gradient(90deg,#5b5bd6,#7d7dff)',
  'linear-gradient(90deg,#9b5de5,#b388ff)',
  'linear-gradient(90deg,#ff9500,#ffb74d)',
  'linear-gradient(90deg,#00b884,#4dd0a8)',
]

const TREND_COLORS = {
  hotTopics: '#5b5bd6',
  scripts: '#00b884',
}

const PLATFORM_FALLBACK = ['#5b5bd6', '#00b884', '#ff9500', '#3b82f6', '#ff3b5c', '#9b5de5', '#00bbf9', '#f15bb5']

const SPARK_PATHS = [
  'M0,20 L10,18 L20,14 L30,16 L40,10 L50,8 L60,4',
  'M0,18 L10,15 L20,20 L30,14 L40,10 L50,12 L60,6',
  'M0,22 L10,20 L20,16 L30,18 L40,10 L50,8 L60,4',
  'M0,16 L10,18 L20,14 L30,16 L40,12 L50,14 L60,10',
  'M0,8 L10,10 L20,6 L30,12 L40,14 L50,16 L60,18',
]

function greeting() {
  const h = new Date().getHours()
  if (h < 6) return '夜深了'
  if (h < 12) return '早上好'
  if (h < 18) return '下午好'
  return '晚上好'
}

function formatDate() {
  return new Intl.DateTimeFormat('zh-CN', {
    weekday: 'long',
    year: 'numeric',
    month: 'long',
    day: 'numeric',
  }).format(new Date())
}

function platformLabel(key) {
  return PLATFORM_META[key]?.label || key || '未知'
}

function platformColor(key, i = 0) {
  return PLATFORM_META[key]?.color || PLATFORM_FALLBACK[i % PLATFORM_FALLBACK.length]
}

/** 最大余数法：保证各占比整数之和为 100 */
function allocatePercentages(values, total) {
  if (!total || total <= 0) return values.map(() => 0)
  const raw = values.map((v) => ((Number(v) || 0) / total) * 100)
  const floors = raw.map((n) => Math.floor(n))
  let remain = 100 - floors.reduce((a, b) => a + b, 0)
  const order = raw
    .map((n, i) => ({ i, frac: n - floors[i] }))
    .sort((a, b) => b.frac - a.frac)
  const result = [...floors]
  for (let k = 0; k < order.length && remain > 0; k += 1) {
    result[order[k].i] += 1
    remain -= 1
  }
  return result
}

function ChartEmpty({ tip }) {
  return (
    <div className="dash-chart-empty">
      <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={tip || '暂无数据'} />
    </div>
  )
}

function ChartTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null
  return (
    <div className="dash-tooltip">
      {label ? <div className="dash-tooltip-label">{label}</div> : null}
      {payload.map((p) => (
        <div key={p.dataKey || p.name} className="dash-tooltip-row">
          <span className="dot" style={{ background: p.color || p.fill }} />
          <span>{p.name}</span>
          <strong>{p.value}</strong>
        </div>
      ))}
    </div>
  )
}

function Sparkline({ color, path, id }) {
  return (
    <svg className="dash-kpi-spark" viewBox="0 0 60 28" aria-hidden>
      <defs>
        <linearGradient id={id} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.3" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={`${path} L60,28 L0,28 Z`} fill={`url(#${id})`} />
      <path d={path} fill="none" stroke={color} strokeWidth="1.5" strokeLinejoin="round" />
    </svg>
  )
}

function DashCard({ title, icon, extra, children, bodyClassName = '' }) {
  return (
    <div className="dash-card">
      <div className="dash-card-head">
        <div className="dash-card-title">
          {icon}
          <span>{title}</span>
        </div>
        {extra}
      </div>
      <div className={`dash-card-body ${bodyClassName}`}>{children}</div>
    </div>
  )
}

function ListRow({ icon, iconTone, title, meta, tag, tagCls, onClick }) {
  return (
    <button type="button" className="dash-list-item" onClick={onClick}>
      <span className={`dash-list-icon ${iconTone || ''}`}>{icon}</span>
      <span className="dash-list-content">
        <span className="dash-list-title">{title}</span>
        {meta ? <span className="dash-list-meta">{meta}</span> : null}
      </span>
      {tag ? <span className={`dash-list-tag ${tagCls || ''}`}>{tag}</span> : null}
    </button>
  )
}

export default function Dashboard() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const navigate = useNavigate()

  const loadDashboard = (quiet = false) => {
    if (!quiet) setLoading(true)
    return dashboardApi.get()
      .then(d => setData(d))
      .catch(() => { if (!quiet) message.error('加载仪表盘失败') })
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    loadDashboard()
    const timer = setInterval(() => loadDashboard(true), 5000)
    return () => clearInterval(timer)
  }, [])

  const platformData = useMemo(() => {
    if (!data?.platformDist?.length) return []
    const rows = data.platformDist.map((p, i) => ({
      name: platformLabel(p.platform),
      value: p.count || 0,
      color: platformColor(p.platform, i),
      platform: p.platform,
    })).filter((d) => d.value > 0)
    const total = rows.reduce((s, d) => s + d.value, 0)
    const pcts = allocatePercentages(rows.map((d) => d.value), total)
    return rows.map((d, i) => ({ ...d, pct: pcts[i] }))
  }, [data])

  const platformTotal = useMemo(
    () => platformData.reduce((s, d) => s + d.value, 0),
    [platformData],
  )

  const pipelineData = useMemo(() => {
    const src = data?.pipeline
    if (src?.length) {
      return src.map((p) => ({
        ...p,
        label: ({ scriptsDraft: '草稿', videosPending: '视频制作', publishPending: '待发布', publishDone: '已发布' })[p.key] || p.label,
      }))
    }
    if (!data?.stats) return []
    const s = data.stats
    return [
      { key: 'scriptsDraft', label: '草稿', value: s.scriptsDraft || 0 },
      { key: 'videosPending', label: '视频制作', value: s.videosPending || 0 },
      { key: 'publishPending', label: '待发布', value: s.publishPending || 0 },
      { key: 'publishDone', label: '已发布', value: s.publishDone || 0 },
    ]
  }, [data])

  const pipelineMax = useMemo(
    () => Math.max(...pipelineData.map((p) => p.value || 0), 1),
    [pipelineData],
  )

  const scriptStatusData = useMemo(() => {
    const map = {}
    ;(data?.scriptStatusDist || []).forEach((r) => {
      map[r.status] = r.count || 0
    })
    return [
      { key: 'draft', label: '草稿', value: map.draft || 0, color: SCRIPT_STATUS_META.draft.color },
      { key: 'reviewing', label: '审核中', value: map.reviewing || 0, color: SCRIPT_STATUS_META.reviewing.color },
      { key: 'approved', label: '已通过', value: map.approved || 0, color: SCRIPT_STATUS_META.approved.color },
      { key: 'used', label: '已发布', value: map.used || 0, color: SCRIPT_STATUS_META.used.color },
      { key: 'rejected', label: '已退回', value: map.rejected || 0, color: SCRIPT_STATUS_META.rejected.color },
    ]
  }, [data])

  const scriptBarMax = useMemo(
    () => Math.max(...scriptStatusData.map((d) => d.value || 0), 1),
    [scriptStatusData],
  )

  const intentionData = useMemo(() => {
    const map = {}
    ;(data?.customerIntentionDist || []).forEach((r) => {
      map[r.intention] = r.count || 0
    })
    const rows = ['high', 'medium', 'low', 'closed'].map((key) => {
      const meta = INTENTION_META[key]
      return {
        key,
        label: meta.label,
        color: meta.color,
        value: map[key] || 0,
      }
    })
    const total = rows.reduce((a, b) => a + b.value, 0) || data?.stats?.customers || 0
    const pcts = allocatePercentages(rows.map((d) => d.value), total)
    return rows.map((d, i) => ({
      ...d,
      total: total || 1,
      pct: pcts[i],
    }))
  }, [data])

  const trends = data?.trends || []
  const hasTrendSignal = trends.some(
    (t) => (t.hotTopics || 0) + (t.scripts || 0) > 0,
  )

  const kpiTrends = useMemo(() => {
    if (trends.length < 2) return {}
    const cur = trends[trends.length - 1] || {}
    const prev = trends[trends.length - 2] || {}
    const rate = (a, b) => {
      if (!b) return a ? 100 : 0
      return Math.round(((a - b) / b) * 1000) / 10
    }
    return {
      hotTopics: rate(cur.hotTopics || 0, prev.hotTopics || 0),
      scripts: rate(cur.scripts || 0, prev.scripts || 0),
      customers: rate(cur.customers || 0, prev.customers || 0),
      publishDone: rate(cur.publishDone || 0, prev.publishDone || 0),
    }
  }, [trends])

  if (loading) {
    return (
      <div style={{ textAlign: 'center', padding: 80 }}>
        <Spin size="large" />
      </div>
    )
  }
  if (!data) return <Empty description="暂无数据" />

  const {
    stats, recentTopics, recentScripts,
    recentCustomers, recentKnowledge,
  } = data

  const topics = recentTopics || []
  const scripts = recentScripts || []
  const customers = recentCustomers || []
  const knowledge = recentKnowledge || []

  const fmtTrend = (n) => {
    if (n == null || Number.isNaN(n)) return null
    const sign = n > 0 ? '+' : ''
    return `${sign}${n}%`
  }

  const kpis = [
    {
      title: '今日热点',
      value: stats.hotTopicsToday || stats.hotTopics,
      unit: '条',
      trend: fmtTrend(kpiTrends.hotTopics),
      trendUp: (kpiTrends.hotTopics || 0) >= 0,
      trendLabel: '环比昨日',
      sub: `累计 ${stats.hotTopics}`,
      icon: <FireOutlined />,
      accent: '#5b5bd6',
      path: '/hot-topics',
    },
    {
      title: '文案产出',
      value: stats.scripts,
      unit: '篇',
      trend: fmtTrend(kpiTrends.scripts),
      trendUp: (kpiTrends.scripts || 0) >= 0,
      trendLabel: '近7日',
      sub: `草稿 ${stats.scriptsDraft}`,
      icon: <FileTextOutlined />,
      accent: '#00b884',
      path: '/scripts',
    },
    {
      title: '视频生产',
      value: (stats.videosPending || 0) + (stats.videosDone || 0),
      unit: '个',
      trend: null,
      trendUp: true,
      trendLabel: '',
      sub: `完成 ${stats.videosDone}`,
      icon: <VideoCameraOutlined />,
      accent: '#ff9500',
      path: '/videos',
    },
    {
      title: '客户跟进',
      value: stats.customers,
      unit: '位',
      trend: fmtTrend(kpiTrends.customers),
      trendUp: (kpiTrends.customers || 0) >= 0,
      trendLabel: '近7日',
      sub: `今日 +${stats.customersNew}`,
      icon: <TeamOutlined />,
      accent: '#3b82f6',
      path: '/customers',
    },
    {
      title: '待发布',
      value: stats.publishPending,
      unit: '条',
      trend: null,
      trendUp: true,
      trendLabel: '',
      sub: `已发 ${stats.publishDone}`,
      icon: <RocketOutlined />,
      accent: '#ff3b5c',
      path: '/publish',
    },
  ]

  const pipelinePaths = {
    scriptsDraft: '/scripts?status=draft',
    videosPending: '/videos?pending=1',
    publishPending: '/publish?status=pending',
    publishDone: '/publish',
  }

  const go = (path) => () => navigate(path)

  const topicTag = (t, i) => {
    if (Number(t.ai_score) >= 90 || i === 0) return { label: '爆', cls: 'hot' }
    if (Number(t.ai_score) >= 80 || i < 3) return { label: '热', cls: 'hot' }
    return { label: '新', cls: 'new' }
  }

  const welcomeParts = []
  if ((stats.hotTopicsToday || 0) > 0) welcomeParts.push(`今日新增热点 ${stats.hotTopicsToday} 条`)
  if ((stats.customersNew || 0) > 0) welcomeParts.push(`新增客户 ${stats.customersNew} 位`)
  if ((stats.knowledgeToday || 0) > 0) welcomeParts.push(`知识库新增 ${stats.knowledgeToday} 条`)
  if (!welcomeParts.length) welcomeParts.push('今日暂无新增数据')

  const todoBits = []
  if ((stats.scriptsDraft || 0) > 0) todoBits.push(`${stats.scriptsDraft} 条文案待处理`)
  if ((stats.videosPending || 0) > 0) todoBits.push(`${stats.videosPending} 个视频待制作`)
  if ((stats.publishPending || 0) > 0) todoBits.push(`${stats.publishPending} 条待发布`)
  if ((stats.pendingReminders || 0) > 0) todoBits.push(`${stats.pendingReminders} 条客户提醒`)
  const todoTotal = (stats.scriptsDraft || 0)
    + (stats.videosPending || 0)
    + (stats.publishPending || 0)
    + (stats.pendingReminders || 0)

  let welcomeSummary = `今天是 ${formatDate()} · ${welcomeParts.join('，')}`
  if (todoTotal > 0) {
    welcomeSummary += ` · 待办合计 ${todoTotal} 项`
    if (todoBits.length) welcomeSummary += `（${todoBits.join('，')}）`
  } else {
    welcomeSummary += ' · 暂无待办'
  }

  return (
    <div className="dash">
      <header className="dash-welcome">
        <div className="dash-welcome-text">
          <h1>{greeting()} 👋</h1>
          <p>{welcomeSummary}</p>
        </div>
      </header>

      <div className="dash-kpi-row">
        {kpis.map((s, i) => (
          <button
            key={s.title}
            type="button"
            className="dash-kpi"
            style={{ '--accent': s.accent, animationDelay: `${0.05 * (i + 1)}s` }}
            onClick={() => navigate(s.path)}
          >
            <div className="dash-kpi-header">
              <span className="dash-kpi-label">{s.title}</span>
              <span className="dash-kpi-icon">{s.icon}</span>
            </div>
            <div className="dash-kpi-value">
              {s.value}
              <span className="unit">{s.unit}</span>
            </div>
            <div className="dash-kpi-footer">
              {s.trend ? (
                <span className={`dash-kpi-trend ${s.trendUp ? 'up' : 'down'}`}>
                  {s.trend}
                  <span className="dash-kpi-trend-label">{s.trendLabel}</span>
                </span>
              ) : (
                <span className="dash-kpi-sub">{s.sub}</span>
              )}
              <Sparkline color={s.accent} path={SPARK_PATHS[i % SPARK_PATHS.length]} id={`spark-${i}`} />
            </div>
          </button>
        ))}
      </div>

      <div className="dash-charts-3">
        <DashCard
          title="内容流水线"
          icon={<RiseOutlined />}
          extra={<button type="button" className="dash-card-link" onClick={go('/scripts')}>查看详情</button>}
        >
          {pipelineData.every((p) => !p.value) ? (
            <ChartEmpty tip="暂无流水线数据" />
          ) : (
            <div className="dash-funnel">
              {pipelineData.map((p, i) => {
                const pct = Math.round(((p.value || 0) / pipelineMax) * 100)
                return (
                  <button
                    key={p.key}
                    type="button"
                    className="dash-funnel-row"
                    onClick={() => navigate(pipelinePaths[p.key] || '/')}
                  >
                    <span className="dash-funnel-label">{p.label}</span>
                    <span className="dash-funnel-track">
                      <span
                        className="dash-funnel-fill"
                        style={{
                          width: `${Math.max(p.value ? 12 : 0, pct)}%`,
                          background: PIPELINE_COLORS[i % PIPELINE_COLORS.length],
                        }}
                      >
                        {p.value > 0 ? p.value : ''}
                      </span>
                    </span>
                    <span className="dash-funnel-value">{p.value}</span>
                  </button>
                )
              })}
            </div>
          )}
        </DashCard>

        <DashCard
          title="热点平台分布"
          icon={<FireOutlined />}
          extra={<button type="button" className="dash-card-link" onClick={go('/hot-topics')}>查看详情</button>}
        >
          {!platformData.length ? (
            <ChartEmpty tip="暂无平台分布" />
          ) : (
            <div className="dash-donut-wrap">
              <div className="dash-donut-chart">
                <ResponsiveContainer width="100%" height={140}>
                  <PieChart>
                    <Pie
                      data={platformData}
                      dataKey="value"
                      nameKey="name"
                      cx="50%"
                      cy="50%"
                      innerRadius={42}
                      outerRadius={58}
                      paddingAngle={2}
                      stroke="none"
                    >
                      {platformData.map((d) => (
                        <Cell key={d.platform} fill={d.color} />
                      ))}
                    </Pie>
                    <Tooltip content={<ChartTooltip />} />
                  </PieChart>
                </ResponsiveContainer>
                <div className="dash-donut-center">
                  <strong>{platformTotal}</strong>
                  <span>热点总数</span>
                </div>
              </div>
              <div className="dash-donut-legend">
                {platformData.map((d) => (
                  <button
                    key={d.platform}
                    type="button"
                    className="dash-legend-item"
                    onClick={() => navigate('/hot-topics')}
                  >
                    <span className="swatch" style={{ background: d.color }} />
                    <span className="name">{d.name}</span>
                    <span className="val">{d.value}条 · {d.pct}%</span>
                  </button>
                ))}
              </div>
            </div>
          )}
        </DashCard>

        <DashCard
          title="7日热点趋势"
          icon={<RiseOutlined />}
          extra={<button type="button" className="dash-card-link" onClick={go('/hot-topics')}>查看详情</button>}
        >
          {!hasTrendSignal ? (
            <ChartEmpty tip="近 7 日暂无新增" />
          ) : (
            <ResponsiveContainer width="100%" height={180}>
              <AreaChart data={trends} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                <defs>
                  <linearGradient id="grad-hotTopics" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor={TREND_COLORS.hotTopics} stopOpacity={0.22} />
                    <stop offset="100%" stopColor={TREND_COLORS.hotTopics} stopOpacity={0} />
                  </linearGradient>
                  <linearGradient id="grad-scripts" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor={TREND_COLORS.scripts} stopOpacity={0.18} />
                    <stop offset="100%" stopColor={TREND_COLORS.scripts} stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#f3f3f6" vertical={false} />
                <XAxis dataKey="label" tick={{ fill: '#9b9bb0', fontSize: 11 }} axisLine={false} tickLine={false} />
                <YAxis allowDecimals={false} tick={{ fill: '#9b9bb0', fontSize: 11 }} axisLine={false} tickLine={false} width={28} />
                <Tooltip content={<ChartTooltip />} />
                <Area type="monotone" dataKey="hotTopics" name="热点数量" stroke={TREND_COLORS.hotTopics} fill="url(#grad-hotTopics)" strokeWidth={2} />
                <Area type="monotone" dataKey="scripts" name="文案产出" stroke={TREND_COLORS.scripts} fill="url(#grad-scripts)" strokeWidth={2} />
              </AreaChart>
            </ResponsiveContainer>
          )}
        </DashCard>
      </div>

      <div className="dash-charts-2">
        <DashCard
          title="文案状态分布"
          icon={<FileTextOutlined />}
          extra={<button type="button" className="dash-card-link" onClick={go('/scripts')}>查看详情</button>}
        >
          {scriptStatusData.every((d) => !d.value) ? (
            <ChartEmpty tip="暂无文案" />
          ) : (
            <div className="dash-bars">
              {scriptStatusData.map((d) => (
                <div key={d.key} className="dash-bar-group">
                  <div className="dash-bar-value">{d.value}</div>
                  <div className="dash-bar-stack">
                    <div
                      className="dash-bar-segment"
                      style={{
                        height: `${Math.max(d.value ? 8 : 0, Math.round((d.value / scriptBarMax) * 100))}px`,
                        background: d.color,
                      }}
                    />
                  </div>
                  <div className="dash-bar-label">{d.label}</div>
                </div>
              ))}
            </div>
          )}
        </DashCard>

        <DashCard
          title="客户意向分布"
          icon={<TeamOutlined />}
          extra={<button type="button" className="dash-card-link" onClick={go('/customers')}>查看详情</button>}
        >
          {intentionData.every((d) => !d.value) ? (
            <ChartEmpty tip="暂无客户" />
          ) : (
            <div className="dash-intent-list">
              {intentionData.map((d) => (
                <div key={d.key} className="dash-intent-item">
                  <div className="dash-intent-header">
                    <div className="dash-intent-name">
                      <span className="dash-intent-dot" style={{ background: d.color }} />
                      {d.label}
                    </div>
                    <div className="dash-intent-count">
                      <strong>{d.value}</strong>
                      {' / '}
                      {d.total}
                      位
                    </div>
                  </div>
                  <div className="dash-intent-track">
                    <div
                      className="dash-intent-bar"
                      style={{ width: `${d.pct}%`, background: d.color }}
                    />
                  </div>
                </div>
              ))}
            </div>
          )}
        </DashCard>
      </div>

      <div className="dash-lists-grid">
        <DashCard
          title="最新热点"
          icon={<FireOutlined />}
          extra={<button type="button" className="dash-card-link" onClick={go('/hot-topics')}>全部热点</button>}
          bodyClassName="dash-card-body--flush"
        >
          {!topics.length ? (
            <ChartEmpty tip="暂无热点" />
          ) : topics.slice(0, 5).map((t, i) => {
            const tag = topicTag(t, i)
            return (
              <ListRow
                key={t.id}
                icon={<RiseOutlined />}
                iconTone={i < 2 ? 'hot' : i < 4 ? 'warn' : 'primary'}
                title={t.title}
                meta={`${platformLabel(t.platform)} · 热度 ${t.likes?.toLocaleString?.() ?? t.likes ?? 0}`}
                tag={tag.label}
                tagCls={tag.cls}
                onClick={go('/hot-topics')}
              />
            )
          })}
        </DashCard>

        <DashCard
          title="最新文案"
          icon={<FileTextOutlined />}
          extra={<button type="button" className="dash-card-link" onClick={go('/scripts')}>全部文案</button>}
          bodyClassName="dash-card-body--flush"
        >
          {!scripts.length ? (
            <ChartEmpty tip="暂无文案" />
          ) : scripts.slice(0, 5).map((s) => {
            const tag = SCRIPT_TAG[s.status] || { label: s.status || '草稿', cls: 'pending' }
            return (
              <ListRow
                key={s.id}
                icon={<FileTextOutlined />}
                iconTone="primary"
                title={s.title}
                meta={`版本 v${s.version || 1}`}
                tag={tag.label}
                tagCls={tag.cls}
                onClick={go('/scripts')}
              />
            )
          })}
        </DashCard>

        <DashCard
          title="最新客户"
          icon={<UserAddOutlined />}
          extra={<button type="button" className="dash-card-link" onClick={go('/customers')}>全部客户</button>}
          bodyClassName="dash-card-body--flush"
        >
          {!customers.length ? (
            <ChartEmpty tip="暂无新增客户" />
          ) : customers.slice(0, 5).map((c) => (
            <ListRow
              key={c.id}
              icon={<UserOutlined />}
              iconTone={c.intention === 'high' ? 'hot' : 'warn'}
              title={c.nickname || `客户 #${c.id}`}
              meta={`来源：${c.source_video || c.source_channel || '未标注'}`}
              tag={intentionLabels[c.intention] || '意向未知'}
              tagCls={c.intention === 'high' ? 'high' : 'medium'}
              onClick={go('/customers')}
            />
          ))}
        </DashCard>

        <DashCard
          title="知识库动态"
          icon={<BookOutlined />}
          extra={<button type="button" className="dash-card-link" onClick={go('/knowledge')}>全部知识</button>}
          bodyClassName="dash-card-body--flush"
        >
          {!knowledge.length ? (
            <ChartEmpty tip="暂无知识条目" />
          ) : knowledge.slice(0, 5).map((k) => (
            <ListRow
              key={k.id}
              icon={<BulbOutlined />}
              iconTone="success"
              title={k.title}
              meta={k.category || '未分类'}
              tag={k.category || '知识'}
              tagCls="new"
              onClick={go('/knowledge')}
            />
          ))}
        </DashCard>
      </div>
    </div>
  )
}
