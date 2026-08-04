import { useState, useEffect, useMemo } from 'react'
import { Row, Col, Card, Spin, message, Button, Empty } from 'antd'
import {
  FireOutlined, FileTextOutlined, VideoCameraOutlined, TeamOutlined,
  RocketOutlined, BulbOutlined, StockOutlined,
  RobotOutlined, ApartmentOutlined, ArrowRightOutlined,
  LikeOutlined, UserAddOutlined, CalendarOutlined,
} from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import { dashboardApi } from '../../api'
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
  if (n >= 8 && n < 20) return 'high' // 兼容 1-10 分制
  if (n >= 7 && n < 8) return 'mid'
  return 'low'
}

function Panel({ title, icon, mark, extra, children, className = '' }) {
  return (
    <Card
      className={`dash-panel ${className}`.trim()}
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
  const navigate = useNavigate()

  useEffect(() => {
    dashboardApi.get().then(d => { setData(d); setLoading(false) })
      .catch(() => { message.error('加载仪表盘失败'); setLoading(false) })
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
  } = data

  const topics = recentTopics || []
  const scripts = recentScripts || []
  const customers = recentCustomers || []
  const knowledge = recentKnowledge || []

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
      <section className="dash-hero">
        <div className="dash-hero-glow" aria-hidden />
        <div className="dash-hero-inner">
          <div className="dash-hero-copy">
            <div className="dash-kicker">
              <span className="dash-pulse" />
              {APP_NAME} · 总览
            </div>
            <h1>{greeting()}</h1>
            <p className="dash-hero-sub">
              内容、客户与发布数据一览。待办和提醒在右上角铃铛里。
            </p>
          </div>
          <div className="dash-hero-meta">
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
                  <ArrowRightOutlined className="dash-chip-arrow" />
                </button>
              ))}
            </div>
          </div>
        </div>
      </section>

      <div className="dash-metrics">
        {metrics.map((s, i) => (
          <button
            key={s.title}
            type="button"
            className="dash-metric"
            style={{ '--accent': s.accent, animationDelay: `${i * 45}ms` }}
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
        {shortcuts.map((s, i) => (
          <button
            key={s.title}
            type="button"
            className={`dash-shortcut tone-${s.tone}`}
            style={{ animationDelay: `${80 + i * 40}ms` }}
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

      <section className="dash-stream">
        {platformDist?.length > 0 && (
          <div className="dash-platform">
            <div className="dash-platform-head">
              <div>
                <div className="dash-platform-title">热点平台分布</div>
                <div className="dash-platform-sub">共 {platformTotal} 条热点 · 按来源统计</div>
              </div>
              <Button type="link" size="small" onClick={() => navigate('/hot-topics')}>
                查看情报 <ArrowRightOutlined />
              </Button>
            </div>
            <div className="dash-platform-grid">
              {platformDist.map((p, i) => {
                const tone = platformTone(p.platform)
                const pct = Math.round((p.count / platformMax) * 100)
                return (
                  <button
                    key={p.platform}
                    type="button"
                    className={`dash-plat tone-${tone}`}
                    style={{ animationDelay: `${i * 50}ms` }}
                    onClick={() => navigate('/hot-topics')}
                  >
                    <div className="dash-plat-top">
                      <span className="dash-plat-name">{platformLabel(p.platform)}</span>
                      <span className="dash-plat-count">{p.count}</span>
                    </div>
                    <div className="dash-plat-track">
                      <div className="dash-plat-fill" style={{ width: `${Math.max(8, pct)}%` }} />
                    </div>
                    <div className="dash-plat-pct">{pct}% 相对最高</div>
                  </button>
                )
              })}
            </div>
          </div>
        )}

        <Row gutter={[16, 16]} className="dash-lists">
          {topics.length > 0 && (
            <Col xs={24} lg={12}>
              <Panel
                title="最新热点"
                icon={<FireOutlined />}
                mark="#e11d48"
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
              <Panel
                title="最新文案"
                icon={<FileTextOutlined />}
                mark="#2563eb"
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
              <Panel
                title="新增客户"
                icon={<UserAddOutlined />}
                mark="#059669"
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
              <Panel
                title="最新知识"
                icon={<BulbOutlined />}
                mark="#0d9488"
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
      </section>
    </div>
  )
}
