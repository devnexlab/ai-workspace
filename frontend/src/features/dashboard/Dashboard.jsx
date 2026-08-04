import { useState, useEffect, useMemo } from 'react'
import { Row, Col, Card, Spin, message, Button, Empty } from 'antd'
import {
  FireOutlined, FileTextOutlined, VideoCameraOutlined, TeamOutlined,
  RocketOutlined, BulbOutlined, LikeOutlined, UserAddOutlined,
  CalendarOutlined, DashboardOutlined, ArrowRightOutlined,
} from '@ant-design/icons'
import {
  ResponsiveContainer, AreaChart, Area, XAxis, YAxis, CartesianGrid,
  Tooltip, Legend, PieChart, Pie, Cell, BarChart, Bar,
} from 'recharts'
import { useNavigate } from 'react-router-dom'
import { dashboardApi, publishApi } from '../../api'
import { APP_NAME } from '../../config'
import './Dashboard.css'

const intentionLabels = { high: '高意向', medium: '中意向', low: '低意向' }

const PLATFORM_META = {
  xiaohongshu: { label: '小红书', color: '#e11d48' },
  toutiao_hot: { label: '今日头条', color: '#dc2626' },
  weibo_hot: { label: '微博热搜', color: '#ea580c' },
  baidu_hot: { label: '百度热榜', color: '#2563eb' },
  zhihu_hot: { label: '知乎热榜', color: '#0284c7' },
  douyin: { label: '抖音', color: '#0f172a' },
  bilibili: { label: 'B站', color: '#db2777' },
}

const SCRIPT_STATUS_META = {
  draft: { label: '草稿', color: '#94a3b8' },
  reviewing: { label: '审阅中', color: '#f59e0b' },
  approved: { label: '已通过', color: '#3b82f6' },
  used: { label: '已出片', color: '#10b981' },
}

const SCRIPT_STATUS = {
  draft: { label: '草稿', cls: 'neutral' },
  reviewing: { label: '草稿', cls: 'neutral' },
  approved: { label: '草稿', cls: 'neutral' },
  used: { label: '已出片', cls: 'green' },
}

const INTENTION_META = {
  high: { label: '高意向', color: '#e11d48' },
  medium: { label: '中意向', color: '#d97706' },
  low: { label: '低意向', color: '#059669' },
}

const PIPELINE_COLORS = ['#fb923c', '#6366f1', '#f59e0b', '#10b981']
const TREND_COLORS = {
  hotTopics: '#e11d48',
  scripts: '#2563eb',
  customers: '#059669',
  publishDone: '#d97706',
}

const PLATFORM_FALLBACK = ['#e11d48', '#dc2626', '#ea580c', '#2563eb', '#0284c7', '#0f172a', '#db2777', '#7c3aed']

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

function scoreClass(s) {
  const n = Number(s)
  if (n >= 90) return 'high'
  if (n >= 80) return 'mid'
  if (n >= 8 && n < 20) return 'high'
  if (n >= 7 && n < 8) return 'mid'
  return 'low'
}

function ChartCard({ title, sub, extra, children, className = '' }) {
  return (
    <div className={`dash-chart-card ${className}`}>
      <div className="dash-chart-card-head">
        <div>
          <div className="dash-chart-card-title">{title}</div>
          {sub ? <div className="dash-chart-card-sub">{sub}</div> : null}
        </div>
        {extra}
      </div>
      <div className="dash-chart-card-body">{children}</div>
    </div>
  )
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

function Panel({ title, icon, mark, extra, children }) {
  return (
    <Card
      className="dash-panel"
      size="small"
      title={(
        <span className="dash-panel-title" style={{ '--mark': mark }}>
          <span className="mark">{icon}</span>
          {title}
        </span>
      )}
      extra={extra}
    >
      {children}
    </Card>
  )
}

function Feed({ children, empty }) {
  const list = Array.isArray(children) ? children.filter(Boolean) : children
  if (!list || (Array.isArray(list) && list.length === 0)) {
    return (
      <div className="dash-empty">
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={empty || '暂无数据'} />
      </div>
    )
  }
  return <div className="dash-feed">{list}</div>
}

function FeedRow({ index, title, meta, side, onClick, accent }) {
  return (
    <button type="button" className="dash-row" onClick={onClick} style={accent ? { '--row-accent': accent } : undefined}>
      {index != null ? <span className={`dash-row-idx${index <= 3 ? ' top' : ''}`}>{index}</span> : null}
      <span className="dash-row-main">
        <span className="dash-row-title">{title}</span>
        {meta ? <span className="dash-row-meta">{meta}</span> : null}
      </span>
      {side ? <span className="dash-row-side">{side}</span> : null}
    </button>
  )
}

export default function Dashboard() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [weekReview, setWeekReview] = useState(null)
  const navigate = useNavigate()

  useEffect(() => {
    dashboardApi.get().then(d => { setData(d); setLoading(false) })
      .catch(() => { message.error('加载仪表盘失败'); setLoading(false) })
    publishApi.analytics({ range: 'week' }).then(setWeekReview).catch(() => setWeekReview(null))
  }, [])

  const platformData = useMemo(() => {
    if (!data?.platformDist?.length) return []
    return data.platformDist.map((p, i) => ({
      name: platformLabel(p.platform),
      value: p.count || 0,
      color: platformColor(p.platform, i),
      platform: p.platform,
    })).filter((d) => d.value > 0)
  }, [data])

  const platformTotal = useMemo(
    () => platformData.reduce((s, d) => s + d.value, 0),
    [platformData],
  )

  const pipelineData = useMemo(() => {
    const src = data?.pipeline
    if (src?.length) return src
    if (!data?.stats) return []
    const s = data.stats
    return [
      { key: 'scriptsDraft', label: '草稿文案', value: s.scriptsDraft || 0 },
      { key: 'videosPending', label: '待做视频', value: s.videosPending || 0 },
      { key: 'publishPending', label: '待发布', value: s.publishPending || 0 },
      { key: 'publishDone', label: '已发布', value: s.publishDone || 0 },
    ]
  }, [data])

  const pipelineMax = useMemo(
    () => Math.max(...pipelineData.map((p) => p.value || 0), 1),
    [pipelineData],
  )

  const scriptStatusData = useMemo(() => {
    if (!data?.scriptStatusDist?.length) return []
    return data.scriptStatusDist.map((r) => {
      const meta = SCRIPT_STATUS_META[r.status] || { label: r.status || '未知', color: '#94a3b8' }
      return { name: meta.label, value: r.count || 0, color: meta.color, status: r.status }
    }).filter((d) => d.value > 0)
  }, [data])

  const intentionData = useMemo(() => {
    if (!data?.customerIntentionDist?.length) return []
    return data.customerIntentionDist.map((r) => {
      const meta = INTENTION_META[r.intention] || { label: r.intention || '未知', color: '#94a3b8' }
      return { name: meta.label, value: r.count || 0, color: meta.color }
    }).filter((d) => d.value > 0)
  }, [data])

  const trends = data?.trends || []
  const hasTrendSignal = trends.some(
    (t) => (t.hotTopics || 0) + (t.scripts || 0) + (t.customers || 0) + (t.publishDone || 0) > 0,
  )

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

  const kpis = [
    { title: '热点', value: stats.hotTopics, sub: `今日 +${stats.hotTopicsToday}`, icon: <FireOutlined />, accent: '#e11d48', path: '/hot-topics' },
    { title: '文案', value: stats.scripts, sub: `草稿 ${stats.scriptsDraft}`, icon: <FileTextOutlined />, accent: '#2563eb', path: '/scripts' },
    { title: '视频', value: (stats.videosPending || 0) + (stats.videosDone || 0), sub: `完成 ${stats.videosDone}`, icon: <VideoCameraOutlined />, accent: '#4f46e5', path: '/videos' },
    { title: '客户', value: stats.customers, sub: `今日 +${stats.customersNew}`, icon: <TeamOutlined />, accent: '#059669', path: '/customers' },
    { title: '待发布', value: stats.publishPending, sub: `已发 ${stats.publishDone}`, icon: <RocketOutlined />, accent: '#d97706', path: '/publish' },
  ]

  const link = (path) => () => navigate(path)
  const pipelinePaths = {
    scriptsDraft: '/scripts?status=draft',
    videosPending: '/videos?pending=1',
    publishPending: '/publish?status=pending',
    publishDone: '/publish',
  }

  return (
    <div className="dash dash-v2 dash-charts">
      <header className="dash-topbar">
        <div className="dash-topbar-left">
          <div className="dash-topbar-kicker">
            <span className="dash-pulse" />
            {APP_NAME}
          </div>
          <h1 className="dash-topbar-title">{greeting()}</h1>
        </div>
        <div className="dash-topbar-right">
          <div className="dash-topbar-meta">
            <div className="dash-date">
              <CalendarOutlined />
              {formatDate()}
            </div>
          </div>
          <div className="dash-quick">
            {[
              { label: '热点', path: '/hot-topics' },
              { label: '文案', path: '/scripts' },
              { label: '视频', path: '/videos' },
              { label: '发布', path: '/publish' },
            ].map(q => (
              <button key={q.path} type="button" className="dash-chip" onClick={() => navigate(q.path)}>
                {q.label}
              </button>
            ))}
          </div>
        </div>
      </header>

      <section className="dash-block dash-block-screen">
        <div className="dash-block-head">
          <div className="dash-block-head-main">
            <div className="dash-block-kicker">
              <span className="dash-block-icon"><DashboardOutlined /></span>
              Dashboard
            </div>
            <h2 className="dash-block-title">数据大屏</h2>
            <p className="dash-block-sub">流水线、平台分布与近 7 日走势</p>
          </div>
          <div className="dash-block-extra">
            <div className="dash-screen-stat">
              <span>热点 {stats.hotTopics}</span>
              <span className="sep" />
              <span>客户 {stats.customers}</span>
              <span className="sep" />
              <span>已发 {stats.publishDone}</span>
            </div>
          </div>
        </div>

        <div className="dash-block-body">
          <div className="dash-kpi-row">
            {kpis.map((s) => (
              <button
                key={s.title}
                type="button"
                className="dash-kpi"
                style={{ '--accent': s.accent }}
                onClick={() => navigate(s.path)}
              >
                <span className="dash-kpi-icon">{s.icon}</span>
                <span className="dash-kpi-body">
                  <span className="dash-kpi-label">{s.title}</span>
                  <span className="dash-kpi-value">{s.value}</span>
                  <span className="dash-kpi-sub">{s.sub}</span>
                </span>
              </button>
            ))}
          </div>

          {weekReview && (
            <button type="button" className="dash-review-strip" onClick={() => navigate('/publish')}>
              <span className="dash-review-title">本周复盘</span>
              <span>已发 <strong>{weekReview.published || 0}</strong></span>
              <span className="sep" />
              <span>有咨询 <strong>{weekReview.consult || 0}</strong></span>
              <span className="sep" />
              <span>咨询率 <strong>{Math.round((weekReview.consult_rate || 0) * 100)}%</strong></span>
              {(weekReview.by_content_type || []).map((x) => (
                <span key={x.key} className="dash-review-chip">{x.label} {x.count}</span>
              ))}
            </button>
          )}

          <Row gutter={[12, 12]}>
            <Col xs={24} lg={12}>
              <ChartCard title="内容流水线" sub="草稿 → 视频 → 待发 → 已发">
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
                                width: `${Math.max(p.value ? 8 : 0, pct)}%`,
                                background: PIPELINE_COLORS[i % PIPELINE_COLORS.length],
                              }}
                            />
                          </span>
                          <span className="dash-funnel-value">{p.value}</span>
                        </button>
                      )
                    })}
                  </div>
                )}
              </ChartCard>
            </Col>

            <Col xs={24} lg={12}>
              <ChartCard
                title="热点平台分布"
                sub={platformTotal ? `共 ${platformTotal} 条` : '按来源'}
                extra={(
                  <Button type="link" size="small" onClick={() => navigate('/hot-topics')}>
                    情报 <ArrowRightOutlined />
                  </Button>
                )}
              >
                {!platformData.length ? (
                  <ChartEmpty tip="暂无平台分布" />
                ) : (
                  <div className="dash-donut-wrap">
                    <ResponsiveContainer width="100%" height={220}>
                      <PieChart>
                        <Pie
                          data={platformData}
                          dataKey="value"
                          nameKey="name"
                          cx="50%"
                          cy="50%"
                          innerRadius={58}
                          outerRadius={82}
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
                          <span className="val">{d.value}</span>
                        </button>
                      ))}
                    </div>
                  </div>
                )}
              </ChartCard>
            </Col>

            <Col span={24}>
              <ChartCard title="近 7 日趋势" sub="热点 / 文案 / 客户 / 已发布">
                {!hasTrendSignal ? (
                  <ChartEmpty tip="近 7 日暂无新增" />
                ) : (
                  <ResponsiveContainer width="100%" height={260}>
                    <AreaChart data={trends} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
                      <defs>
                        {Object.entries(TREND_COLORS).map(([k, c]) => (
                          <linearGradient key={k} id={`grad-${k}`} x1="0" y1="0" x2="0" y2="1">
                            <stop offset="0%" stopColor={c} stopOpacity={0.28} />
                            <stop offset="100%" stopColor={c} stopOpacity={0.02} />
                          </linearGradient>
                        ))}
                      </defs>
                      <CartesianGrid strokeDasharray="3 3" stroke="rgba(15,23,42,0.06)" vertical={false} />
                      <XAxis dataKey="label" tick={{ fill: '#94a3b8', fontSize: 12 }} axisLine={false} tickLine={false} />
                      <YAxis allowDecimals={false} tick={{ fill: '#94a3b8', fontSize: 12 }} axisLine={false} tickLine={false} width={32} />
                      <Tooltip content={<ChartTooltip />} />
                      <Legend wrapperStyle={{ fontSize: 12, paddingTop: 8 }} />
                      <Area type="monotone" dataKey="hotTopics" name="热点" stroke={TREND_COLORS.hotTopics} fill={`url(#grad-hotTopics)`} strokeWidth={2} />
                      <Area type="monotone" dataKey="scripts" name="文案" stroke={TREND_COLORS.scripts} fill={`url(#grad-scripts)`} strokeWidth={2} />
                      <Area type="monotone" dataKey="customers" name="客户" stroke={TREND_COLORS.customers} fill={`url(#grad-customers)`} strokeWidth={2} />
                      <Area type="monotone" dataKey="publishDone" name="已发" stroke={TREND_COLORS.publishDone} fill={`url(#grad-publishDone)`} strokeWidth={2} />
                    </AreaChart>
                  </ResponsiveContainer>
                )}
              </ChartCard>
            </Col>

            <Col xs={24} lg={12}>
              <ChartCard title="文案状态" sub="按 status 分布" extra={(
                <Button type="link" size="small" onClick={() => navigate('/scripts')}>全部</Button>
              )}>
                {!scriptStatusData.length ? (
                  <ChartEmpty tip="暂无文案" />
                ) : (
                  <ResponsiveContainer width="100%" height={220}>
                    <BarChart data={scriptStatusData} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="rgba(15,23,42,0.06)" vertical={false} />
                      <XAxis dataKey="name" tick={{ fill: '#94a3b8', fontSize: 12 }} axisLine={false} tickLine={false} />
                      <YAxis allowDecimals={false} tick={{ fill: '#94a3b8', fontSize: 12 }} axisLine={false} tickLine={false} width={28} />
                      <Tooltip content={<ChartTooltip />} />
                      <Bar dataKey="value" name="数量" radius={[6, 6, 0, 0]} maxBarSize={48}>
                        {scriptStatusData.map((d) => (
                          <Cell key={d.status || d.name} fill={d.color} />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                )}
              </ChartCard>
            </Col>

            <Col xs={24} lg={12}>
              <ChartCard title="客户意向" sub="高 / 中 / 低" extra={(
                <Button type="link" size="small" onClick={() => navigate('/customers')}>全部</Button>
              )}>
                {!intentionData.length ? (
                  <ChartEmpty tip="暂无客户" />
                ) : (
                  <div className="dash-donut-wrap compact">
                    <ResponsiveContainer width="100%" height={220}>
                      <PieChart>
                        <Pie
                          data={intentionData}
                          dataKey="value"
                          nameKey="name"
                          cx="42%"
                          cy="50%"
                          outerRadius={78}
                          paddingAngle={2}
                          stroke="none"
                        >
                          {intentionData.map((d) => (
                            <Cell key={d.name} fill={d.color} />
                          ))}
                        </Pie>
                        <Tooltip content={<ChartTooltip />} />
                      </PieChart>
                    </ResponsiveContainer>
                    <div className="dash-donut-legend">
                      {intentionData.map((d) => (
                        <div key={d.name} className="dash-legend-item static">
                          <span className="swatch" style={{ background: d.color }} />
                          <span className="name">{d.name}</span>
                          <span className="val">{d.value}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </ChartCard>
            </Col>
          </Row>

          <Row gutter={[14, 14]} className="dash-lists">
            {topics.length > 0 && (
              <Col xs={24} lg={12}>
                <Panel title="最新热点" icon={<FireOutlined />} mark="#e11d48"
                  extra={<Button type="link" size="small" onClick={link('/hot-topics')}>全部</Button>}
                >
                  <Feed empty="暂无热点">
                    {topics.map((t, i) => (
                      <FeedRow
                        key={t.id}
                        index={i + 1}
                        accent="#e11d48"
                        title={t.title}
                        onClick={link('/hot-topics')}
                        meta={(
                          <>
                            <span className="dash-tag soft">{platformLabel(t.platform)}</span>
                            <span><LikeOutlined /> {(t.likes?.toLocaleString?.() ?? t.likes ?? 0)}</span>
                          </>
                        )}
                        side={<span className={`dash-score ${scoreClass(t.ai_score)}`}>{t.ai_score ?? '-'}</span>}
                      />
                    ))}
                  </Feed>
                </Panel>
              </Col>
            )}

            {scripts.length > 0 && (
              <Col xs={24} lg={topics.length ? 12 : 24}>
                <Panel title="最新文案" icon={<FileTextOutlined />} mark="#2563eb"
                  extra={<Button type="link" size="small" onClick={link('/scripts')}>全部</Button>}
                >
                  <Feed empty="暂无文案">
                    {scripts.map((s, i) => {
                      const st = SCRIPT_STATUS[s.status] || { label: s.status, cls: 'neutral' }
                      return (
                        <FeedRow
                          key={s.id}
                          index={i + 1}
                          accent="#2563eb"
                          title={s.title}
                          onClick={link('/scripts')}
                          meta={<span>版本 v{s.version}</span>}
                          side={<span className={`dash-badge ${st.cls}`}>{st.label}</span>}
                        />
                      )
                    })}
                  </Feed>
                </Panel>
              </Col>
            )}

            {customers.length > 0 && (
              <Col xs={24} lg={12}>
                <Panel title="新增客户" icon={<UserAddOutlined />} mark="#059669"
                  extra={<Button type="link" size="small" onClick={link('/customers')}>全部</Button>}
                >
                  <Feed empty="暂无新增客户">
                    {customers.map((c, i) => (
                      <FeedRow
                        key={c.id}
                        index={i + 1}
                        accent="#059669"
                        title={c.nickname || `客户 #${c.id}`}
                        onClick={link('/customers')}
                        meta={<span>{c.source_video || c.source_channel || '未标注来源'}</span>}
                        side={(
                          <span className={`dash-badge intent-${c.intention || 'low'}`}>
                            {intentionLabels[c.intention] || '意向未知'}
                          </span>
                        )}
                      />
                    ))}
                  </Feed>
                </Panel>
              </Col>
            )}

            {knowledge.length > 0 && (
              <Col xs={24} lg={customers.length ? 12 : 24}>
                <Panel title="最新知识" icon={<BulbOutlined />} mark="#0d9488"
                  extra={<Button type="link" size="small" onClick={link('/knowledge')}>全部</Button>}
                >
                  <Feed empty="暂无知识条目">
                    {knowledge.map((k, i) => (
                      <FeedRow
                        key={k.id}
                        index={i + 1}
                        accent="#0d9488"
                        title={k.title}
                        onClick={link('/knowledge')}
                        meta={(
                          <>
                            <span>{k.category || '未分类'}</span>
                            {k.source_type ? <span>· {k.source_type}</span> : null}
                          </>
                        )}
                        side={k.category ? <span className="dash-badge cyan">{k.category}</span> : null}
                      />
                    ))}
                  </Feed>
                </Panel>
              </Col>
            )}
          </Row>
        </div>
      </section>
    </div>
  )
}
