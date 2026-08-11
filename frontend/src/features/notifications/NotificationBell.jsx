import { useCallback, useEffect, useRef, useState } from 'react'
import { Badge, Button, Drawer, Empty, List, Space, Tag, Tooltip, message } from 'antd'
import { BellOutlined, CheckOutlined, ClockCircleOutlined } from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import { remindersApi } from '../../api'
import { formatDate } from '../../utils/date'

const TYPE_MAP = {
  birthday: { label: '生日', color: 'pink' },
  policy_expiry: { label: '保单到期', color: 'red' },
  silent: { label: '沉默', color: 'orange' },
  high_intent: { label: '高意向', color: 'volcano' },
  follow_up: { label: '跟进', color: 'blue' },
  stock_alert: { label: '股价预警', color: 'gold' },
  general: { label: '一般', color: 'default' },
}

function isOverdue(dateStr) {
  if (!dateStr) return false
  const today = new Date().toISOString().slice(0, 10)
  return String(dateStr).slice(0, 10) < today
}

function sameReminderList(a, b) {
  if (a === b) return true
  if (!a || !b || a.length !== b.length) return false
  for (let i = 0; i < a.length; i += 1) {
    if (a[i].id !== b[i].id || a[i].status !== b[i].status || a[i].remind_date !== b[i].remind_date) {
      return false
    }
  }
  return true
}

/** 客户提醒（生日 / 保单 / 跟进日程等） */
export default function NotificationBell() {
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)
  const [loading, setLoading] = useState(false)
  const [items, setItems] = useState([])
  const [actingId, setActingId] = useState(null)
  const reqSeq = useRef(0)
  const hasLoaded = useRef(false)

  const load = useCallback((opts = {}) => {
    const silent = opts.silent !== false
    const seq = ++reqSeq.current
    if (!silent) setLoading(true)
    remindersApi.list({ status: 'pending', scope: 'all' })
      .then((res) => {
        if (seq !== reqSeq.current) return
        const next = res.list || []
        setItems((prev) => (sameReminderList(prev, next) ? prev : next))
        hasLoaded.current = true
      })
      .catch(() => {
        if (seq !== reqSeq.current) return
        if (!silent && !hasLoaded.current) setItems([])
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
    // 有缓存则静默刷新，不挡首屏；无数据才显示 loading
    load({ silent: hasLoaded.current || items.length > 0 })
  }

  const closeDrawer = () => {
    reqSeq.current += 1 // 丢弃关闭后返回的请求，避免关抽屉时被 setState 拖住
    setLoading(false)
    setOpen(false)
  }

  const badgeCount = items.length

  const handleDone = (id) => {
    setActingId(id)
    remindersApi.update(id, { status: 'done' })
      .then(() => {
        message.success('已完成')
        load({ silent: true })
      })
      .catch((err) => message.error(err?.error || '操作失败'))
      .finally(() => setActingId(null))
  }

  const handleSnooze = (id, days = 1) => {
    setActingId(id)
    remindersApi.update(id, { snooze_days: days })
      .then(() => {
        message.success(`已延期 ${days} 天`)
        load({ silent: true })
      })
      .catch((err) => message.error(err?.error || '操作失败'))
      .finally(() => setActingId(null))
  }

  return (
    <>
      <Badge count={badgeCount} overflowCount={99} size="small" offset={[-2, 4]}>
        <Tooltip
          title={badgeCount ? `${badgeCount} 条提醒` : '暂无提醒'}
          mouseEnterDelay={0.35}
          mouseLeaveDelay={0.08}
        >
          <Button
            type="text"
            className="app-icon-btn"
            onClick={openDrawer}
            aria-label="打开提醒"
            icon={<BellOutlined />}
          />
        </Tooltip>
      </Badge>

      <Drawer
        title={`提醒${badgeCount > 0 ? `（${badgeCount}）` : ''}`}
        open={open}
        onClose={closeDrawer}
        width={420}
        destroyOnClose={false}
        forceRender={false}
        extra={(
          <Button
            type="link"
            size="small"
            onClick={() => {
              closeDrawer()
              navigate('/customers?tab=reminders')
            }}
          >
            查看全部
          </Button>
        )}
      >
        {!items.length && !loading ? (
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无待处理提醒" />
        ) : (
          <List
            loading={loading}
            dataSource={items}
            renderItem={(r) => {
              const tp = TYPE_MAP[r.type] || { label: r.type || '提醒', color: 'default' }
              const overdue = isOverdue(r.remind_date)
              return (
                <List.Item
                  actions={[
                    <Button
                      key="done"
                      type="link"
                      size="small"
                      icon={<CheckOutlined />}
                      loading={actingId === r.id}
                      onClick={() => handleDone(r.id)}
                    >
                      完成
                    </Button>,
                    <Button
                      key="snooze"
                      type="link"
                      size="small"
                      icon={<ClockCircleOutlined />}
                      loading={actingId === r.id}
                      onClick={() => handleSnooze(r.id, 1)}
                    >
                      稍后
                    </Button>,
                  ]}
                >
                  <List.Item.Meta
                    title={(
                      <Space size={6} wrap>
                        <span
                          style={{ cursor: 'pointer' }}
                          onClick={() => {
                            closeDrawer()
                            navigate(r.type === 'stock_alert' ? '/stocks/watchlist' : '/customers?tab=reminders')
                          }}
                        >
                          {r.title || '未命名提醒'}
                        </span>
                        <Tag color={tp.color}>{tp.label}</Tag>
                        {overdue && <Tag color="red">逾期</Tag>}
                      </Space>
                    )}
                    description={(
                      <span style={{ fontSize: 12, color: 'var(--text-tertiary)' }}>
                        {r.type === 'stock_alert'
                          ? (r.content || r.suggested_action || '股价提醒')
                          : (r.customer_name || '未关联客户')}
                        {r.remind_date ? ` · ${formatDate(r.remind_date)}` : ''}
                        {r.type !== 'stock_alert' && r.suggested_action ? ` · ${r.suggested_action}` : ''}
                      </span>
                    )}
                  />
                </List.Item>
              )
            }}
          />
        )}
      </Drawer>
    </>
  )
}
