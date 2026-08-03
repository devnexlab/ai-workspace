import { useCallback, useEffect, useState } from 'react'
import { Badge, Button, Drawer, Empty, List, Space, Tag, Tooltip } from 'antd'
import {
  CheckSquareOutlined, FileTextOutlined, VideoCameraOutlined,
  RocketOutlined, TeamOutlined,
} from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import { dashboardApi } from '../../api'

const intentionLabels = { high: '高意向', medium: '中意向', low: '低意向' }

function Section({ title, icon, count, extra, children, empty }) {
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
          color: '#0f172a',
        }}
        >
          <span style={{ color: '#64748b' }}>{icon}</span>
          {title}
          {count > 0 ? <Tag color="blue">{count}</Tag> : null}
        </div>
        {extra}
      </div>
      {count === 0 ? (
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={empty} style={{ margin: '8px 0' }} />
      ) : children}
    </div>
  )
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

  const load = useCallback(() => {
    setLoading(true)
    dashboardApi.get()
      .then((dash) => {
        setPendingScripts(dash.pendingScripts || [])
        setPendingVideos(dash.pendingVideos || [])
        setPendingPublish(dash.pendingPublish || [])
        setFollowCustomers(dash.followCustomers || [])
      })
      .catch(() => {
        setPendingScripts([])
        setPendingVideos([])
        setPendingPublish([])
        setFollowCustomers([])
      })
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    load()
    const timer = setInterval(load, 60000)
    return () => clearInterval(timer)
  }, [load])

  useEffect(() => {
    if (open) load()
  }, [open, load])

  const badgeCount = pendingScripts.length
    + pendingVideos.length
    + pendingPublish.length
    + followCustomers.length

  const go = (path) => {
    setOpen(false)
    navigate(path)
  }

  return (
    <>
      <Tooltip title={badgeCount ? `${badgeCount} 条待办` : '暂无待办'}>
        <Badge count={badgeCount} overflowCount={99} size="small" offset={[-2, 2]}>
          <Button
            type="text"
            onClick={() => setOpen(true)}
            aria-label="打开待办"
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 6,
              height: 36,
              padding: '0 10px',
              borderRadius: 18,
            }}
          >
            <CheckSquareOutlined style={{ fontSize: 18 }} />
            <span style={{ fontSize: 13, color: '#475569', fontWeight: 600 }}>
              {badgeCount > 0 ? `待办 ${badgeCount}` : '待办'}
            </span>
          </Button>
        </Badge>
      </Tooltip>

      <Drawer
        title={`待办${badgeCount > 0 ? `（${badgeCount}）` : ''}`}
        open={open}
        onClose={() => setOpen(false)}
        width={460}
      >
        <Section
          title="待出片文案"
          icon={<FileTextOutlined />}
          count={pendingScripts.length}
          empty="暂无待出片文案"
          extra={<Button type="link" size="small" onClick={() => go('/scripts')}>全部</Button>}
        >
          <List
            loading={loading}
            size="small"
            dataSource={pendingScripts}
            renderItem={(s) => (
              <List.Item
                actions={[
                  <Button key="go" type="link" size="small" onClick={() => go('/scripts')}>
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
          empty="暂无待生成视频"
          extra={<Button type="link" size="small" onClick={() => go('/videos')}>全部</Button>}
        >
          <List
            loading={loading}
            size="small"
            dataSource={pendingVideos}
            renderItem={(v) => (
              <List.Item
                actions={[
                  <Button key="go" type="link" size="small" onClick={() => go('/videos')}>
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
                        <Tag key={label} color={status === 'done' ? 'success' : 'default'}>
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
          empty="暂无待发布任务"
          extra={<Button type="link" size="small" onClick={() => go('/publish')}>全部</Button>}
        >
          <List
            loading={loading}
            size="small"
            dataSource={pendingPublish}
            renderItem={(p) => (
              <List.Item
                actions={[
                  <Button key="go" type="link" size="small" onClick={() => go('/publish')}>
                    去发布
                  </Button>,
                ]}
              >
                <List.Item.Meta
                  title={p.video_title || `发布任务 #${p.id}`}
                  description={(
                    <Space size={6}>
                      <span style={{ fontSize: 12, color: '#64748b' }}>{p.platform || '未指定平台'}</span>
                      <Tag color="orange">待发布</Tag>
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
          empty="暂无待跟进客户"
          extra={<Button type="link" size="small" onClick={() => go('/customers')}>全部</Button>}
        >
          <List
            loading={loading}
            size="small"
            dataSource={followCustomers}
            renderItem={(c) => (
              <List.Item
                actions={[
                  <Button key="go" type="link" size="small" onClick={() => go('/customers')}>
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
                      <span style={{ fontSize: 12, color: '#64748b' }}>
                        {c.last_follow_time || '未跟进'}
                      </span>
                    </Space>
                  )}
                />
              </List.Item>
            )}
          />
        </Section>
      </Drawer>
    </>
  )
}
