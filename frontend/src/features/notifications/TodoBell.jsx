import { useCallback, useEffect, useRef, useState } from 'react'
import { Badge, Button, Drawer, Empty, List, Space, Tag, Tooltip, Spin } from 'antd'
import {
  CheckSquareOutlined, FileTextOutlined, VideoCameraOutlined,
  RocketOutlined, TeamOutlined,
} from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import { dashboardApi } from '../../api'
import { formatDateTime } from '../../utils/date'

const intentionLabels = { high: '高意向', medium: '中意向', low: '低意向' }

function Section({ title, icon, count, extra, children }) {
  if (!count) return null
  return (
    <div style={{ marginBottom: 22 }}>
      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        marginBottom: 8,
      }}
      >
        <div style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: 8,
          fontWeight: 600,
          fontSize: 14,
          color: 'var(--text-primary)',
        }}
        >
          <span style={{ color: 'var(--text-secondary)' }}>{icon}</span>
          {title}
          <Tag color="blue">{count}</Tag>
        </div>
        {extra}
      </div>
      {children}
    </div>
  )
}

function sameIdList(a, b) {
  if (a === b) return true
  if (!a || !b || a.length !== b.length) return false
  for (let i = 0; i < a.length; i += 1) {
    if (a[i]?.id !== b[i]?.id) return false
  }
  return true
}

/** 运营待办：待出片文案 / 待生成视频 / 待发布 / 待跟进客户 */
export default function TodoBell() {
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)
  const [loading, setLoading] = useState(false)
  const [pendingScripts, setPendingScripts] = useState([])
  const [pendingVideos, setPendingVideos] = useState([])
  const [pendingPublish, setPendingPublish] = useState([])
  const [followCustomers, setFollowCustomers] = useState([])
  const reqSeq = useRef(0)
  const hasLoaded = useRef(false)

  const load = useCallback((opts = {}) => {
    const silent = opts.silent !== false
    const seq = ++reqSeq.current
    if (!silent) setLoading(true)
    dashboardApi.get()
      .then((dash) => {
        if (seq !== reqSeq.current) return
        const scripts = dash.pendingScripts || []
        const videos = dash.pendingVideos || []
        const publish = dash.pendingPublish || []
        const follows = dash.followCustomers || []
        setPendingScripts((prev) => (sameIdList(prev, scripts) ? prev : scripts))
        setPendingVideos((prev) => (sameIdList(prev, videos) ? prev : videos))
        setPendingPublish((prev) => (sameIdList(prev, publish) ? prev : publish))
        setFollowCustomers((prev) => (sameIdList(prev, follows) ? prev : follows))
        hasLoaded.current = true
      })
      .catch(() => {
        if (seq !== reqSeq.current) return
        if (!silent && !hasLoaded.current) {
          setPendingScripts([])
          setPendingVideos([])
          setPendingPublish([])
          setFollowCustomers([])
        }
      })
      .finally(() => {
        if (seq !== reqSeq.current) return
        if (!silent) setLoading(false)
      })
  }, [])

  useEffect(() => {
    load({ silent: true })
    const timer = setInterval(() => load({ silent: true }), 60000)
    return () => clearInterval(timer)
  }, [load])

  const openDrawer = () => {
    setOpen(true)
    const cached = hasLoaded.current
      || pendingScripts.length
      || pendingVideos.length
      || pendingPublish.length
      || followCustomers.length
    // 已有缓存：立刻展示，后台静默刷新，避免等 dashboard 1～2 秒
    load({ silent: Boolean(cached) })
  }

  const closeDrawer = () => {
    reqSeq.current += 1
    setLoading(false)
    setOpen(false)
  }

  const badgeCount = pendingScripts.length
    + pendingVideos.length
    + pendingPublish.length
    + followCustomers.length

  const go = (path) => {
    closeDrawer()
    navigate(path)
  }

  return (
    <>
      <Badge count={badgeCount} overflowCount={99} size="small" offset={[-2, 4]}>
        <Tooltip
          title={badgeCount ? `${badgeCount} 条待办` : '暂无待办'}
          mouseEnterDelay={0.35}
          mouseLeaveDelay={0.08}
        >
          <Button
            type="text"
            className="app-icon-btn"
            onClick={openDrawer}
            aria-label="打开待办"
            icon={<CheckSquareOutlined />}
          />
        </Tooltip>
      </Badge>

      <Drawer
        title={`待办${badgeCount > 0 ? `（${badgeCount}）` : ''}`}
        open={open}
        onClose={closeDrawer}
        width={460}
        destroyOnClose={false}
        forceRender={false}
      >
        <Spin spinning={loading && !badgeCount}>
          {!badgeCount && !loading ? (
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无待办，一切顺利" />
          ) : (
            <>
              <Section
                title="待出片文案"
                icon={<FileTextOutlined />}
                count={pendingScripts.length}
                extra={<Button type="link" size="small" onClick={() => go('/scripts?status=draft')}>全部</Button>}
              >
                <List
                  size="small"
                  dataSource={pendingScripts}
                  renderItem={(s) => (
                    <List.Item
                      actions={[
                        <Button key="go" type="link" size="small" onClick={() => go(`/scripts?status=draft&focus=${s.id}`)}>
                          去出片
                        </Button>,
                      ]}
                    >
                      <List.Item.Meta
                        title={s.title || `文案 #${s.id}`}
                        description={(
                          <Space size={6}>
                            <Tag>{s.content_type === 'insurance' ? '保险干货' : '泛流量'}</Tag>
                            <Tag color="default">草稿</Tag>
                          </Space>
                        )}
                      />
                    </List.Item>
                  )}
                />
              </Section>

              <Section
                title="待生成视频"
                icon={<VideoCameraOutlined />}
                count={pendingVideos.length}
                extra={<Button type="link" size="small" onClick={() => go('/videos?pending=1')}>全部</Button>}
              >
                <List
                  size="small"
                  dataSource={pendingVideos}
                  renderItem={(v) => (
                    <List.Item
                      actions={[
                        <Button key="go" type="link" size="small" onClick={() => go(`/videos?focus=${v.id}`)}>
                          去处理
                        </Button>,
                      ]}
                    >
                      <List.Item.Meta
                        title={v.title || `视频任务 #${v.id}`}
                        description={(
                          <Space size={4} wrap>
                            {[
                              ['配音', v.voice_status],
                              ['字幕', v.subtitle_status],
                              ['剪辑', v.video_status],
                              ['导出', v.export_status],
                            ].map(([label, status]) => (
                              <Tag key={label} color={status === 'done' ? 'success' : status === 'failed' ? 'error' : 'default'}>
                                {label}
                              </Tag>
                            ))}
                          </Space>
                        )}
                      />
                    </List.Item>
                  )}
                />
              </Section>

              <Section
                title="待发布"
                icon={<RocketOutlined />}
                count={pendingPublish.length}
                extra={<Button type="link" size="small" onClick={() => go('/publish?status=pending')}>全部</Button>}
              >
                <List
                  size="small"
                  dataSource={pendingPublish}
                  renderItem={(p) => (
                    <List.Item
                      actions={[
                        <Button key="go" type="link" size="small" onClick={() => go(`/publish?focus=${p.id}`)}>
                          去发布
                        </Button>,
                      ]}
                    >
                      <List.Item.Meta
                        title={p.video_title || `发布任务 #${p.id}`}
                        description={(
                          <Space size={6}>
                            <span style={{ fontSize: 12, color: 'var(--text-tertiary)' }}>{p.platform || '未指定平台'}</span>
                            <Tag color="orange">{p.status === 'reviewing' ? '待确认' : '待发布'}</Tag>
                          </Space>
                        )}
                      />
                    </List.Item>
                  )}
                />
              </Section>

              <Section
                title="待跟进客户"
                icon={<TeamOutlined />}
                count={followCustomers.length}
                extra={<Button type="link" size="small" onClick={() => go('/customers')}>全部</Button>}
              >
                <List
                  size="small"
                  dataSource={followCustomers}
                  renderItem={(c) => (
                    <List.Item
                      actions={[
                        <Button key="go" type="link" size="small" onClick={() => go(`/customers?focus=${c.id}`)}>
                          去跟进
                        </Button>,
                      ]}
                    >
                      <List.Item.Meta
                        title={c.nickname || `客户 #${c.id}`}
                        description={(
                          <Space size={6}>
                            <Tag color={c.intention === 'high' ? 'red' : 'orange'}>
                              {intentionLabels[c.intention] || c.intention}
                            </Tag>
                            <span style={{ fontSize: 12, color: 'var(--text-tertiary)' }}>
                              {c.last_follow_time ? formatDateTime(c.last_follow_time) : '未跟进'}
                            </span>
                          </Space>
                        )}
                      />
                    </List.Item>
                  )}
                />
              </Section>
            </>
          )}
        </Spin>
      </Drawer>
    </>
  )
}
