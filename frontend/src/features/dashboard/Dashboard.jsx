import { useState, useEffect, useMemo } from 'react'
import { Row, Col, Card, Spin, message, Button, Empty, Tag } from 'antd'
import {
  FireOutlined, FileTextOutlined, VideoCameraOutlined, TeamOutlined,
  RocketOutlined, BulbOutlined, StockOutlined,
  RobotOutlined, ApartmentOutlined, ArrowRightOutlined,
  LikeOutlined, UserAddOutlined, CalendarOutlined,
  CheckCircleOutlined, WarningOutlined, BellOutlined,
  SettingOutlined, ThunderboltOutlined, DashboardOutlined,
} from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import { dashboardApi, settingsApi } from '../../api'
import { APP_NAME } from '../../config'
import './Dashboard.css'

const intentionLabels = { high: '高意向', medium: '中意向', low: '低意向' }

const PLATFORM_META = {
  xiaohongshu: { label: '小红书', tone: 'rose' },
  toutiao_hot: { label: '今日头条', tone: 'red' },
  weibo_hot: { label: '微博热搜', tone: 'orange' },
  baidu_hot: { label: '百度热榜', tone: 'blue' },
  zhihu_hot: { label: '知乎热榜', tone: 'sky' },
  douyin: { label: '抖音', tone: 'ink' },
  bilibili: { label: 'B站', tone: 'pink' },
}

const SCRIPT_STATUS = {
  draft: { label: '草稿', cls: 'neutral' },
  reviewing: { label: '草稿', cls: 'neutral' },
  approved: { label: '草稿', cls: 'neutral' },
  used: { label: '已出片', cls: 'green' },
}

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

function platformTone(key) {
  return PLATFORM_META[key]?.tone || 'blue'
}

function scoreClass(s) {
  const n = Number(s)
  if (n >= 90) return 'high'
  if (n >= 80) return 'mid'
  if (n >= 8 && n < 20) return 'high'
  if (n >= 7 && n < 8) return 'mid'
  return 'low'
}

function SectionFrame({ kicker, title, icon, sub, extra, children, variant = 'screen' }) {
  return (
    <section className={`dash-block dash-block-${variant}`}>
      <div className="dash-block-head">
        <div className="dash-block-head-main">
          <div className="dash-block-kicker">
            <span className="dash-block-icon">{icon}</span>
            {kicker}
          </div>
          <h2 className="dash-block-title">{title}</h2>
          {sub ? <p className="dash-block-sub">{sub}</p> : null}
        </div>
        {extra ? <div className="dash-block-extra">{extra}</div> : null}
      </div>
      <div className="dash-block-body">{children}</div>
    </section>
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
  const [readiness, setReadiness] = useState(null)
  const navigate = useNavigate()

  useEffect(() => {
    dashboardApi.get().then(d => { setData(d); setLoading(false) })
      .catch(() => { message.error('加载仪表盘失败'); setLoading(false) })
    settingsApi.check().then(setReadiness).catch(() => setReadiness(null))
  }, [])

  const platformMax = useMemo(() => {
    if (!data?.platformDist?.length) return 1
    return Math.max(...data.platformDist.map(p => p.count || 0), 1)
  }, [data])

  const platformTotal = useMemo(() => {
    if (!data?.platformDist?.length) return 0
    return data.platformDist.reduce((sum, p) => sum + (p.count || 0), 0)
  }, [data])

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
    recentCustomers, platformDist, recentKnowledge,
    todayWorkbench,
  } = data

  const topics = recentTopics || []
  const scripts = recentScripts || []
  const customers = recentCustomers || []
  const knowledge = recentKnowledge || []
  const wb = todayWorkbench || { counts: {} }
  const wbCounts = wb.counts || {}

  const workItems = [
    {
      key: 'scripts',
      title: '待出片文案',
      count: wbCounts.scripts || 0,
      hint: '草稿待出片',
      icon: <FileTextOutlined />,
      tone: 'blue',
      path: '/scripts?status=draft',
      items: (wb.scripts || []).slice(0, 3),
      itemLabel: (x) => x.title || `文案 #${x.id}`,
      itemPath: (x) => `/scripts?status=draft&focus=${x.id}`,
    },
    {
      key: 'videos',
      title: '待做 / 失败视频',
      count: wbCounts.videos || 0,
      hint: wbCounts.failedVideos ? `${wbCounts.failedVideos} 条失败待重试` : '未完成导出',
      icon: <VideoCameraOutlined />,
      tone: 'violet',
      path: '/videos?pending=1',
      items: (wb.videos || []).slice(0, 3),
      itemLabel: (x) => x.title || `视频 #${x.id}`,
      itemPath: (x) => `/videos?focus=${x.id}`,
    },
    {
      key: 'publish',
      title: '待发布',
      count: wbCounts.publish || 0,
      hint: '待发或待确认',
      icon: <RocketOutlined />,
      tone: 'amber',
      path: '/publish?status=pending',
      items: (wb.publish || []).slice(0, 3),
      itemLabel: (x) => x.video_title || x.title || `发布 #${x.id}`,
      itemPath: (x) => `/publish?focus=${x.id}`,
    },
    {
      key: 'reminders',
      title: '逾期 / 今日提醒',
      count: wbCounts.reminders || 0,
      hint: wbCounts.overdueReminders ? `${wbCounts.overdueReminders} 条已逾期` : '客户日程',
      icon: <BellOutlined />,
      tone: 'rose',
      path: '/customers?tab=reminders',
      items: (wb.reminders || []).slice(0, 3),
      itemLabel: (x) => x.title || x.customer_name || `提醒 #${x.id}`,
      itemPath: () => '/customers?tab=reminders',
    },
    {
      key: 'follow',
      title: '待跟进客户',
      count: wbCounts.follow || 0,
      hint: '高/中意向久未跟进',
      icon: <TeamOutlined />,
      tone: 'teal',
      path: '/customers',
      items: (wb.followCustomers || []).slice(0, 3),
      itemLabel: (x) => x.nickname || `客户 #${x.id}`,
      itemPath: (x) => `/customers?focus=${x.id}`,
    },
  ].filter((w) => w.count > 0 || (w.items && w.items.length > 0))

  const readyList = readiness?.summary || []
  const notReady = readyList.filter((r) => !r.ready && !r.optional)
  const optionalWarn = readyList.filter((r) => !r.ready && r.optional)
  const todoTotal = (wbCounts.scripts || 0) + (wbCounts.videos || 0)
    + (wbCounts.publish || 0) + (wbCounts.reminders || 0) + (wbCounts.follow || 0)

  const metrics = [
    { title: '热点', value: stats.hotTopics, sub: `今日 +${stats.hotTopicsToday}`, icon: <FireOutlined />, accent: '#e11d48', path: '/hot-topics' },
    { title: '文案', value: stats.scripts, sub: `草稿 ${stats.scriptsDraft}`, icon: <FileTextOutlined />, accent: '#2563eb', path: '/scripts' },
    { title: '视频', value: stats.videosPending + stats.videosDone, sub: `完成 ${stats.videosDone}`, icon: <VideoCameraOutlined />, accent: '#4f46e5', path: '/videos' },
    { title: '客户', value: stats.customers, sub: `今日 +${stats.customersNew}`, icon: <TeamOutlined />, accent: '#059669', path: '/customers' },
    { title: '待发布', value: stats.publishPending, sub: `已发 ${stats.publishDone}`, icon: <RocketOutlined />, accent: '#d97706', path: '/publish' },
  ]

  const shortcuts = [
    { title: '知识库', value: stats.knowledgeItems, hint: `今日 +${stats.knowledgeToday}`, icon: <BulbOutlined />, path: '/knowledge', tone: 'teal' },
    { title: '自选股', value: stats.stockCount, hint: `持仓 ${stats.stockHolding}`, icon: <StockOutlined />, path: '/stocks', tone: 'rose' },
    { title: 'Agents', value: stats.agents, hint: `活跃 ${stats.agentsActive}`, icon: <RobotOutlined />, path: '/agents', tone: 'indigo' },
    { title: 'AI助手', value: '工作流', hint: '客户 / 运营 / 发布', icon: <ApartmentOutlined />, path: '/workflows', tone: 'amber' },
  ]

  const link = (path) => () => navigate(path)

  return (
    <div className="dash">
      <header className="dash-topbar">
        <div className="dash-topbar-left">
          <div className="dash-topbar-kicker">
            <span className="dash-pulse" />
            {APP_NAME}
          </div>
          <h1 className="dash-topbar-title">{greeting()}</h1>
        </div>
        <div className="dash-topbar-right">
          <div className="dash-date">
            <CalendarOutlined />
            {formatDate()}
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

      {/* —— 1. 数据大屏 —— */}
      <SectionFrame
        variant="screen"
        kicker="Dashboard"
        title="数据大屏"
        icon={<DashboardOutlined />}
        sub="运营数据一览：指标、模块入口与最新动态"
        extra={(
          <div className="dash-screen-stat">
            <span>热点 {stats.hotTopics}</span>
            <span className="sep" />
            <span>客户 {stats.customers}</span>
            <span className="sep" />
            <span>已发 {stats.publishDone}</span>
          </div>
        )}
      >
        <div className="dash-metrics">
          {metrics.map((s, i) => (
            <button
              key={s.title}
              type="button"
              className="dash-metric"
              style={{ '--accent': s.accent, animationDelay: `${i * 40}ms` }}
              onClick={() => navigate(s.path)}
            >
              <div className="dash-metric-top">
                <span className="dash-metric-label">{s.title}</span>
                <span className="dash-metric-icon">{s.icon}</span>
              </div>
              <div className="dash-metric-value">{s.value}</div>
              <div className="dash-metric-sub">{s.sub}</div>
            </button>
          ))}
        </div>

        <div className="dash-shortcuts">
          {shortcuts.map((s) => (
            <button
              key={s.title}
              type="button"
              className={`dash-shortcut tone-${s.tone}`}
              onClick={() => navigate(s.path)}
            >
              <span className="dash-shortcut-icon">{s.icon}</span>
              <span className="dash-shortcut-body">
                <span className="dash-shortcut-title">{s.title}</span>
                <span className="dash-shortcut-value">{s.value}</span>
                <span className="dash-shortcut-hint">{s.hint}</span>
              </span>
            </button>
          ))}
        </div>

        {platformDist?.length > 0 && (
          <div className="dash-platform">
            <div className="dash-platform-head">
              <div>
                <div className="dash-platform-title">热点平台分布</div>
                <div className="dash-platform-sub">共 {platformTotal} 条 · 按来源</div>
              </div>
              <Button type="link" size="small" onClick={() => navigate('/hot-topics')}>
                查看情报 <ArrowRightOutlined />
              </Button>
            </div>
            <div className="dash-platform-grid">
              {platformDist.map((p) => {
                const tone = platformTone(p.platform)
                const pct = Math.round((p.count / platformMax) * 100)
                return (
                  <button
                    key={p.platform}
                    type="button"
                    className={`dash-plat tone-${tone}`}
                    onClick={() => navigate('/hot-topics')}
                  >
                    <div className="dash-plat-top">
                      <span className="dash-plat-name">{platformLabel(p.platform)}</span>
                      <span className="dash-plat-count">{p.count}</span>
                    </div>
                    <div className="dash-plat-track">
                      <div className="dash-plat-fill" style={{ width: `${Math.max(8, pct)}%` }} />
                    </div>
                  </button>
                )
              })}
            </div>
          </div>
        )}

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
      </SectionFrame>

      {/* —— 2. 今日工作台 —— */}
      <SectionFrame
        variant="work"
        kicker="Workbench"
        title="今日工作台"
        icon={<ThunderboltOutlined />}
        sub="先处理积压，点进去就能继续干"
        extra={(
          <div className="dash-work-badge">
            {todoTotal > 0 ? (
              <>
                <span className="num">{todoTotal}</span>
                <span className="lbl">项待办</span>
              </>
            ) : (
              <span className="lbl ok">暂无积压</span>
            )}
          </div>
        )}
      >
        {workItems.length === 0 ? (
          <div className="dash-workbench-empty">
            <CheckCircleOutlined />
            <div>
              <strong>今天没有积压待办</strong>
              <p>可以去内容情报找选题，或在文案中心开「今日计划并出片」。</p>
            </div>
            <Button type="primary" onClick={() => navigate('/hot-topics')}>去找选题</Button>
          </div>
        ) : (
          <div className="dash-workbench-grid">
            {workItems.map((w) => (
              <div key={w.key} className={`dash-wb-card tone-${w.tone}`}>
                <button type="button" className="dash-wb-top" onClick={() => navigate(w.path)}>
                  <span className="dash-wb-icon">{w.icon}</span>
                  <span className="dash-wb-meta">
                    <span className="dash-wb-name">{w.title}</span>
                    <span className="dash-wb-hint">{w.hint}</span>
                  </span>
                  <span className="dash-wb-count">{w.count}</span>
                </button>
                <div className="dash-wb-list">
                  {(w.items || []).length === 0 ? (
                    <div className="dash-wb-none">暂无明细</div>
                  ) : (
                    w.items.map((it) => (
                      <button
                        key={`${w.key}-${it.id}`}
                        type="button"
                        className="dash-wb-item"
                        onClick={() => navigate(w.itemPath(it))}
                      >
                        <span className="dash-wb-item-title">{w.itemLabel(it)}</span>
                        <ArrowRightOutlined />
                      </button>
                    ))
                  )}
                </div>
              </div>
            ))}
          </div>
        )}

        {readyList.length > 0 && (
          <div className="dash-ready">
            <div className="dash-ready-head">
              <div className="dash-ready-title">
                <SettingOutlined /> 配置就绪
              </div>
              <Button type="link" size="small" onClick={() => navigate('/settings/ai')}>去设置</Button>
            </div>
            <div className="dash-ready-grid">
              {readyList.map((r) => (
                <button
                  key={r.key}
                  type="button"
                  className={`dash-ready-chip ${r.ready ? 'ok' : r.optional ? 'warn' : 'bad'}`}
                  onClick={() => navigate(r.path || '/settings/ai')}
                  title={r.message}
                >
                  {r.ready ? <CheckCircleOutlined /> : <WarningOutlined />}
                  <span>{r.label}</span>
                  <Tag color={r.ready ? 'success' : r.optional ? 'warning' : 'error'}>
                    {r.ready ? '就绪' : r.optional ? '建议' : '未就绪'}
                  </Tag>
                </button>
              ))}
            </div>
            {(notReady.length > 0 || optionalWarn.length > 0) && (
              <div className="dash-ready-tip">
                {notReady.length > 0
                  ? `还有 ${notReady.map((x) => x.label).join('、')} 未就绪。`
                  : `可选：${optionalWarn.map((x) => x.label).join('、')} 未安装。`}
              </div>
            )}
          </div>
        )}
      </SectionFrame>
    </div>
  )
}
