import { useCallback, useEffect, useState } from 'react'
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
  general: { label: '一般', color: 'default' },
}

function isOverdue(dateStr) {
  if (!dateStr) return false
  const today = new Date().toISOString().slice(0, 10)
  return String(dateStr).slice(0, 10) < today
}

/** 客户提醒（生日 / 保单 / 跟进日程等） */
export default function NotificationBell() {
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)
  const [loading, setLoading] = useState(false)
  const [items, setItems] = useState([])
  const [actingId, setActingId] = useState(null)

  const load = useCallback(() => {
    setLoading(true)
    remindersApi.list({ status: 'pending' })
      .then(res => setItems(res.list || []))
      .catch(() => setItems([]))
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

  const badgeCount = items.length

  const handleDone = (id) => {
    setActingId(id)
    remindersApi.update(id, { status: 'done' })
      .then(() => {
        message.success('已完成')
        load()
      })
      .catch(err => message.error(err?.error || '操作失败'))
      .finally(() => setActingId(null))
  }

  const handleSnooze = (id, days = 1) => {
    setActingId(id)
    remindersApi.update(id, { snooze_days: days })
      .then(() => {
        message.success(`已延期 ${days} 天`)
        load()
      })
      .catch(err => message.error(err?.error || '操作失败'))
      .finally(() => setActingId(null))
  }

  return (
    <>
      <Tooltip title={badgeCount ? `${badgeCount} 条客户提醒` : '暂无客户提醒'}>
        <Badge count={badgeCount} overflowCount={99} size="small" offset={[-2, 2]}>
          <Button
            type="text"
            onClick={() => setOpen(true)}
            aria-label="打开提醒"
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 6,
              height: 36,
              padding: '0 10px',
              borderRadius: 18,
            }}
          >
            <BellOutlined style={{ fontSize: 18 }} />
            <span style={{ fontSize: 13, color: '#475569', fontWeight: 600 }}>提醒</span>
          </Button>
        </Badge>
      </Tooltip>

      <Drawer
        title={`客户提醒${badgeCount > 0 ? `（${badgeCount}）` : ''}`}
        open={open}
        onClose={() => setOpen(false)}
        width={420}
        extra={(
          <Button
            type="link"
            size="small"
            onClick={() => {
              setOpen(false)
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
                        <span>{r.title || '未命名提醒'}</span>
                        <Tag color={tp.color}>{tp.label}</Tag>
                        {overdue && <Tag color="red">逾期</Tag>}
                      </Space>
                    )}
                    description={(
                      <span style={{ fontSize: 12, color: '#64748b' }}>
                        {r.customer_name || '未关联客户'}
                        {r.remind_date ? ` · ${formatDate(r.remind_date)}` : ''}
                        {r.suggested_action ? ` · ${r.suggested_action}` : ''}
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
