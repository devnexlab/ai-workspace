import { useState, useEffect, useMemo } from 'react'
import { Row, Col, Card, Spin, message, Button, Empty } from 'antd'
import {
  FireOutlined, FileTextOutlined, VideoCameraOutlined, TeamOutlined,
  RocketOutlined, BulbOutlined, StockOutlined,
  RobotOutlined, ApartmentOutlined, ThunderboltOutlined,
  LikeOutlined, UserAddOutlined,
} from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import { dashboardApi } from '../../api'
import { APP_NAME } from '../../config'
import './Dashboard.css'

const intentionLabels = { high: '高意向', medium: '中意向', low: '低意向' }

const AVATAR_PALETTE = ['#f43f5e', '#3b82f6', '#10b981', '#f59e0b', '#6366f1', '#14b8a6', '#ec4899']

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

function colorOf(seed) {
  const s = String(seed || '')
  let hash = 0
  for (let i = 0; i < s.length; i += 1) hash = (hash + s.charCodeAt(i) * (i + 1)) % AVATAR_PALETTE.length
  return AVATAR_PALETTE[hash]
}

function scoreClass(s) {
  return s >= 8 ? 'high' : s >= 7 ? 'mid' : 'low'
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
  if (!children || (Array.isArray(children) && children.length === 0)) {
    return (
      <div className="dash-empty">
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={empty || '暂无数据'} />
      </div>
    )
  }
  return <div className="dash-feed">{children}</div>
}

function FeedItem({ avatar, soft, title, meta, side, onClick, avatarStyle }) {
  return (
    <div className="dash-item" onClick={onClick} role={onClick ? 'button' : undefined}>
      <div className={`dash-item-avatar${soft ? ' soft' : ''}`} style={avatarStyle}>
        {avatar}
      </div>
      <div className="dash-item-main">
        <div className="dash-item-title">{title}</div>
        {meta ? <div className="dash-item-meta">{meta}</div> : null}
      </div>
      {side ? <div className="dash-item-side">{side}</div> : null}
    </div>
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

  const metrics = [
    { title: '热点总数', value: stats.hotTopics, sub: `今日新增 ${stats.hotTopicsToday}`, icon: <FireOutlined />, accent: '#f43f5e' },
    { title: '文案数量', value: stats.scripts, sub: `草稿 ${stats.scriptsDraft}`, icon: <FileTextOutlined />, accent: '#3b82f6' },
    { title: '视频任务', value: stats.videosPending + stats.videosDone, sub: `已完成 ${stats.videosDone}`, icon: <VideoCameraOutlined />, accent: '#6366f1' },
    { title: '客户总数', value: stats.customers, sub: `今日 +${stats.customersNew} · 高意向 ${stats.customersHigh}`, icon: <TeamOutlined />, accent: '#10b981' },
    { title: '待发布', value: stats.publishPending, sub: `已发布 ${stats.publishDone}`, icon: <RocketOutlined />, accent: '#f59e0b', path: '/publish' },
  ]

  const modules = [
    { title: '知识条目', value: stats.knowledgeItems, sub: `今日 +${stats.knowledgeToday}`, icon: <BulbOutlined />, accent: '#14b8a6', path: '/knowledge' },
    { title: '自选股票', value: stats.stockCount, sub: `持仓 ${stats.stockHolding}`, icon: <StockOutlined />, accent: '#ec4899', path: '/stocks' },
    { title: 'AI Agents', value: stats.agents, sub: `活跃 ${stats.agentsActive}`, icon: <RobotOutlined />, accent: '#6366f1', path: '/agents' },
    { title: 'AI助手', value: stats.agents, sub: '客户 / 运营 / 发布', icon: <ApartmentOutlined />, accent: '#f59e0b', path: '/workflows' },
  ]

  const quickLinks = [
    { label: '内容情报', path: '/hot-topics' },
    { label: '文案中心', path: '/scripts' },
    { label: '视频中心', path: '/videos' },
    { label: '发布中心', path: '/publish' },
    { label: 'AI助手', path: '/workflows' },
  ]

  const link = (path) => () => navigate(path)

  return (
    <div className="dash">
      <section className="dash-hero">
        <div className="dash-hero-inner">
          <div>
            <div className="dash-kicker">
              <span className="dash-pulse" />
              DATA SCREEN · {APP_NAME}
            </div>
            <h1>{greeting()}，运营数据大屏</h1>
            <p className="dash-hero-sub">
              一屏查看热点、文案、视频、客户与发布数据。待办与提醒请看右上角。
            </p>
          </div>
          <div className="dash-hero-meta">
            <div className="dash-date">{formatDate()}</div>
            <div className="dash-quick">
              {quickLinks.map(q => (
                <button key={q.path} type="button" className="dash-chip" onClick={() => navigate(q.path)}>
                  <ThunderboltOutlined style={{ marginRight: 4 }} />
                  {q.label}
                </button>
              ))}
            </div>
          </div>
        </div>
      </section>

      <div className="dash-metrics">
        {metrics.map((s, i) => (
          <div
            key={s.title}
            className={`dash-metric${s.path ? ' clickable' : ''}`}
            style={{ '--accent': s.accent, animationDelay: `${i * 40}ms` }}
            onClick={() => s.path && navigate(s.path)}
          >
            <div className="dash-metric-top">
              <span className="dash-metric-label">{s.title}</span>
              <span className="dash-metric-icon" style={{ background: s.accent }}>{s.icon}</span>
            </div>
            <div className="dash-metric-value">{s.value}</div>
            <div className="dash-metric-sub">{s.sub}</div>
          </div>
        ))}
      </div>

      <div className="dash-modules">
        {modules.map((s, i) => (
          <div
            key={s.title}
            className="dash-module"
            style={{ animationDelay: `${120 + i * 40}ms` }}
            onClick={() => navigate(s.path)}
          >
            <div className="dash-module-icon" style={{ background: s.accent }}>{s.icon}</div>
            <div className="dash-module-body">
              <div className="dash-module-title">{s.title}</div>
              <div className="dash-module-value">{s.value}</div>
              <div className="dash-module-sub">{s.sub}</div>
            </div>
          </div>
        ))}
      </div>

      {platformDist?.length > 0 && (
        <div className="dash-platform">
          <div className="dash-platform-head">
            <div className="dash-platform-title"><FireOutlined /> 热点平台分布</div>
            <Button type="link" size="small" onClick={() => navigate('/hot-topics')}>查看情报</Button>
          </div>
          <div className="dash-bars">
            {platformDist.map(p => (
              <div key={p.platform} className="dash-bar-row">
                <div className="dash-bar-name">{p.platform}</div>
                <div className="dash-bar-track">
                  <div
                    className="dash-bar-fill"
                    style={{ width: `${Math.max(6, (p.count / platformMax) * 100)}%` }}
                  />
                </div>
                <div className="dash-bar-count">{p.count}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      <Row gutter={[16, 16]}>
        <Col xs={24} lg={12}>
          <Panel
            title="最新热点"
            icon={<FireOutlined />}
            mark="#f43f5e"
            extra={<Button type="link" size="small" onClick={link('/hot-topics')}>查看全部</Button>}
          >
            <Feed empty="暂无热点">
              {(recentTopics || []).map(t => (
                <FeedItem
                  key={t.id}
                  avatar={<FireOutlined />}
                  soft
                  avatarStyle={{ '--avatar': colorOf(t.platform), '--avatar-bg': `${colorOf(t.platform)}22`, '--avatar-ink': colorOf(t.platform) }}
                  title={t.title}
                  onClick={link('/hot-topics')}
                  meta={(
                    <>
                      <span>{t.platform || '未知平台'}</span>
                      <span className="dot" />
                      <span><LikeOutlined /> {t.likes?.toLocaleString?.() ?? t.likes ?? 0}</span>
                    </>
                  )}
                  side={(
                    <span className={`dash-badge ${scoreClass(t.ai_score)}`}>AI {t.ai_score ?? '-'}</span>
                  )}
                />
              ))}
            </Feed>
          </Panel>
        </Col>

        <Col xs={24} lg={12}>
          <Panel
            title="最新文案"
            icon={<FileTextOutlined />}
            mark="#3b82f6"
            extra={<Button type="link" size="small" onClick={link('/scripts')}>查看全部</Button>}
          >
            <Feed empty="暂无文案">
              {(recentScripts || []).map(s => {
                const st = SCRIPT_STATUS[s.status] || { label: s.status, cls: 'neutral' }
                return (
                  <FeedItem
                    key={s.id}
                    avatar={<FileTextOutlined />}
                    soft
                    avatarStyle={{ '--avatar-bg': 'rgba(59,130,246,0.12)', '--avatar-ink': '#2563eb' }}
                    title={s.title}
                    onClick={link('/scripts')}
                    meta={(
                      <>
                        <span>版本 v{s.version}</span>
                      </>
                    )}
                    side={<span className={`dash-badge ${st.cls}`}>{st.label}</span>}
                  />
                )
              })}
            </Feed>
          </Panel>
        </Col>
      </Row>

      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col xs={24} lg={12}>
          <Panel
            title="新增客户"
            icon={<UserAddOutlined />}
            mark="#10b981"
            extra={<Button type="link" size="small" onClick={link('/customers')}>查看全部</Button>}
          >
            <Feed empty="暂无新增客户">
              {(recentCustomers || []).map(c => (
                <FeedItem
                  key={c.id}
                  avatar={<UserAddOutlined />}
                  soft
                  avatarStyle={{ '--avatar-bg': 'rgba(16,185,129,0.14)', '--avatar-ink': '#059669' }}
                  title={c.nickname || `客户 #${c.id}`}
                  onClick={link('/customers')}
                  meta={(
                    <>
                      <span>{c.source_video || c.source_channel || '未标注来源'}</span>
                    </>
                  )}
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

        <Col xs={24} lg={12}>
          <Panel
            title="最新知识"
            icon={<BulbOutlined />}
            mark="#14b8a6"
            extra={<Button type="link" size="small" onClick={link('/knowledge')}>查看全部</Button>}
          >
            <Feed empty="暂无知识条目">
              {(recentKnowledge || []).map(k => (
                <FeedItem
                  key={k.id}
                  avatar={<BulbOutlined />}
                  soft
                  avatarStyle={{ '--avatar-bg': 'rgba(20,184,166,0.14)', '--avatar-ink': '#0d9488' }}
                  title={k.title}
                  onClick={link('/knowledge')}
                  meta={(
                    <>
                      {k.category ? <span>{k.category}</span> : <span>未分类</span>}
                      {k.source_type ? (
                        <>
                          <span className="dot" />
                          <span>{k.source_type}</span>
                        </>
                      ) : null}
                    </>
                  )}
                  side={k.category ? <span className="dash-badge cyan">{k.category}</span> : null}
                />
              ))}
            </Feed>
          </Panel>
        </Col>
      </Row>
    </div>
  )
}
