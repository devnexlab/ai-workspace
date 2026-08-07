import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Button, Drawer, Empty, Form, Input, Modal, Select, Space, Table, Tag, message,
} from 'antd'
import {
  PlusOutlined, ReloadOutlined, UserAddOutlined, SearchOutlined,
} from '@ant-design/icons'
import { leadsApi } from '../../api'
import { formatDateTime } from '../../utils/date'
import './Leads.css'

const STATUS_COLOR = {
  pending_contact: 'processing',
  following: 'blue',
  converted: 'success',
  invalid: 'default',
}

const SOURCE_TAG = {
  wechat_oa: 'green',
  douyin: 'purple',
  xiaohongshu: 'magenta',
  channels: 'blue',
  manual: 'orange',
}

const FILTER_CHIPS = [
  { key: 'all', label: '全部' },
  { key: 'pending_contact', label: '待首联', status: 'pending_contact' },
  { key: 'following', label: '跟进中', status: 'following' },
  { key: 'wechat_oa', label: '服务号', source: 'wechat_oa' },
  { key: 'content', label: '内容引流', source: 'content' },
  { key: 'invalid', label: '无效', status: 'invalid' },
]

export default function Leads() {
  const navigate = useNavigate()
  const [loading, setLoading] = useState(true)
  const [data, setData] = useState({ list: [], total: 0, stats: {} })
  const [page, setPage] = useState(1)
  const [chip, setChip] = useState('all')
  const [q, setQ] = useState('')
  const [selectedRowKeys, setSelectedRowKeys] = useState([])
  const [meta, setMeta] = useState({ sources: [], statuses: [] })
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [editing, setEditing] = useState(null)
  const [saving, setSaving] = useState(false)
  const [form] = Form.useForm()

  const activeFilter = useMemo(
    () => FILTER_CHIPS.find(c => c.key === chip) || FILTER_CHIPS[0],
    [chip],
  )

  const load = useCallback((p = page) => {
    setLoading(true)
    const params = { page: p, pageSize: 20 }
    if (activeFilter.status) params.status = activeFilter.status
    if (activeFilter.source) params.source = activeFilter.source
    if (q.trim()) params.q = q.trim()
    leadsApi.list(params)
      .then(res => {
        setData({
          list: res.list || [],
          total: res.total || 0,
          stats: res.stats || {},
        })
        setPage(p)
      })
      .catch(() => message.error('加载线索失败'))
      .finally(() => setLoading(false))
  }, [page, activeFilter, q])

  useEffect(() => {
    leadsApi.meta().then(setMeta).catch(() => {})
  }, [])

  useEffect(() => {
    load(1)
  }, [chip]) // eslint-disable-line react-hooks/exhaustive-deps

  const openCreate = () => {
    setEditing(null)
    form.resetFields()
    form.setFieldsValue({ source: 'manual', status: 'pending_contact' })
    setDrawerOpen(true)
  }

  const openEdit = (row) => {
    setEditing(row)
    form.setFieldsValue({
      nickname: row.nickname,
      phone: row.phone,
      wechat: row.wechat,
      source: row.source,
      related_content: row.related_content,
      preferred_time: row.preferred_time,
      remark: row.remark,
      status: row.status,
    })
    setDrawerOpen(true)
  }

  const handleSave = () => {
    form.validateFields().then(values => {
      setSaving(true)
      const req = editing
        ? leadsApi.update(editing.id, values)
        : leadsApi.create(values)
      req
        .then(() => {
          message.success(editing ? '已保存' : '线索已创建')
          setDrawerOpen(false)
          load(editing ? page : 1)
        })
        .catch(err => message.error(err?.error || '保存失败'))
        .finally(() => setSaving(false))
    })
  }

  const handleConvert = (row) => {
    Modal.confirm({
      title: `将「${row.nickname}」转为客户？`,
      content: '将进入客户列表（生命周期默认「约访」），并从线索池移除。',
      okText: '转客户',
      onOk: () => leadsApi.convert(row.id)
        .then(res => {
          message.success(res.message || '已转为客户')
          setDrawerOpen(false)
          load(page)
          if (res.customer_id) {
            navigate(`/customers?id=${res.customer_id}`)
          }
        })
        .catch(err => message.error(err?.error || '转化失败')),
    })
  }

  const handleBatchConvert = () => {
    if (!selectedRowKeys.length) {
      message.warning('请先选择线索')
      return
    }
    Modal.confirm({
      title: `批量转客户（${selectedRowKeys.length} 条）？`,
      content: '无效/已转化线索会跳过或失败。',
      okText: '转客户',
      onOk: () => leadsApi.batchConvert(selectedRowKeys)
        .then(res => {
          message.success(res.message || '已完成')
          setSelectedRowKeys([])
          load(page)
        })
        .catch(err => message.error(err?.error || '批量转化失败')),
    })
  }

  const handleInvalid = (row) => {
    leadsApi.update(row.id, { status: 'invalid' })
      .then(() => {
        message.success('已标为无效')
        setDrawerOpen(false)
        load(page)
      })
      .catch(err => message.error(err?.error || '操作失败'))
  }

  const stats = data.stats || {}

  const columns = [
    {
      title: '线索',
      dataIndex: 'nickname',
      render: (_, row) => (
        <div>
          <div className="leads-name">{row.nickname}</div>
          <div className="leads-sub">
            {[row.phone && `手机 ${row.phone}`, row.wechat && `微信 ${row.wechat}`]
              .filter(Boolean)
              .join(' · ') || '无联系方式'}
            {row.preferred_time ? ` · ${row.preferred_time}` : ''}
          </div>
        </div>
      ),
    },
    {
      title: '来源',
      dataIndex: 'source',
      width: 120,
      render: (v, row) => (
        <Tag color={SOURCE_TAG[v] || 'default'}>{row.source_label || v}</Tag>
      ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 100,
      render: (v, row) => (
        <Tag color={STATUS_COLOR[v] || 'default'}>{row.status_label || v}</Tag>
      ),
    },
    {
      title: '进线时间',
      dataIndex: 'created_at',
      width: 160,
      render: v => formatDateTime(v),
    },
    {
      title: '操作',
      width: 200,
      render: (_, row) => (
        <Space size={6} wrap>
          <Button size="small" type="link" onClick={() => openEdit(row)}>详情</Button>
          {row.status !== 'invalid' ? (
            <Button size="small" type="primary" onClick={() => handleConvert(row)}>
              转客户
            </Button>
          ) : null}
        </Space>
      ),
    },
  ]

  return (
    <div className="leads-page">
      <div className="leads-head">
        <div>
          <h1 className="leads-title">线索池</h1>
          <p className="leads-desc">
            汇集服务号预约、内容引流私信与手工登记。待首联、待转化在这里处理，转客户后再进客户列表。
          </p>
        </div>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={() => load(page)}>刷新</Button>
          <Button icon={<PlusOutlined />} onClick={openCreate}>录入线索</Button>
          <Button type="primary" icon={<UserAddOutlined />} onClick={handleBatchConvert}>
            转客户（批量）
          </Button>
        </Space>
      </div>

      <div className="leads-kpis">
        <div className="leads-kpi"><div className="k">今日新增</div><div className="v">{stats.today_new || 0}</div></div>
        <div className="leads-kpi"><div className="k">待首联</div><div className={`v${stats.pending_contact ? ' warn' : ''}`}>{stats.pending_contact || 0}</div></div>
        <div className="leads-kpi"><div className="k">跟进中</div><div className="v">{stats.following || 0}</div></div>
        <div className="leads-kpi"><div className="k">本周已转化</div><div className={`v${stats.converted_week ? ' ok' : ''}`}>{stats.converted_week || 0}</div></div>
        <div className="leads-kpi"><div className="k">无效</div><div className="v">{stats.invalid || 0}</div></div>
      </div>

      <div className="leads-layout">
        <div className="leads-main">
          <div className="leads-toolbar">
            <div className="leads-chips">
              {FILTER_CHIPS.map(c => (
                <button
                  key={c.key}
                  type="button"
                  className={`leads-chip${chip === c.key ? ' active' : ''}`}
                  onClick={() => setChip(c.key)}
                >
                  {c.label}
                </button>
              ))}
            </div>
            <Input.Search
              allowClear
              placeholder="搜称呼 / 手机 / 微信"
              style={{ width: 220 }}
              value={q}
              onChange={e => setQ(e.target.value)}
              onSearch={() => load(1)}
              enterButton={<SearchOutlined />}
            />
          </div>

          <div className="leads-panel">
            <Table
              rowKey="id"
              loading={loading}
              columns={columns}
              dataSource={data.list}
              rowSelection={{
                selectedRowKeys,
                onChange: setSelectedRowKeys,
                getCheckboxProps: row => ({
                  disabled: row.status === 'invalid',
                }),
              }}
              locale={{ emptyText: <Empty description="暂无线索" /> }}
              pagination={{
                current: page,
                total: data.total,
                pageSize: 20,
                showTotal: t => `共 ${t} 条`,
                onChange: p => load(p),
              }}
              size="middle"
            />
          </div>
        </div>

        <aside className="leads-side">
          <h3>怎么用</h3>
          <div className="leads-flow">
            <strong>进线</strong> → 线索池<br />
            待首联 / 跟进中<br />
            <strong>转客户</strong> → 客户列表<br />
            （约访 → 跟踪 → 方案 → 成交）
          </div>
          <ul className="leads-tips">
            <li><strong>服务号预约</strong>：来自预约页，自动进池</li>
            <li><strong>内容引流</strong>：抖音/小红书/视频号，手工录入</li>
            <li><strong>转客户</strong>：写入客户列表，默认「约访」</li>
            <li><strong>无效</strong>：空号、广告、无意向，保留备查</li>
          </ul>
        </aside>
      </div>

      <Drawer
        title={editing ? '线索详情' : '录入线索'}
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        width={420}
        destroyOnClose
        extra={
          editing ? (
            <span className="leads-drawer-sub">
              {editing.source_label}
              {editing.created_at ? ` · ${formatDateTime(editing.created_at)}` : ''}
            </span>
          ) : null
        }
      >
        <Form form={form} layout="vertical">
          <Form.Item name="nickname" label="称呼" rules={[{ required: true, message: '必填' }]}>
            <Input placeholder="如：张女士" />
          </Form.Item>
          <Form.Item name="phone" label="手机" dependencies={['wechat']} rules={[
            ({ getFieldValue }) => ({
              validator(_, value) {
                if ((value && String(value).trim()) || (getFieldValue('wechat') && String(getFieldValue('wechat')).trim())) {
                  return Promise.resolve()
                }
                return Promise.reject(new Error('手机与微信至少填一项'))
              },
            }),
          ]}>
            <Input placeholder="选填，与微信至少填一项" />
          </Form.Item>
          <Form.Item name="wechat" label="微信" dependencies={['phone']}>
            <Input placeholder="选填" />
          </Form.Item>
          <Form.Item name="source" label="来源" rules={[{ required: true }]}>
            <Select options={(meta.sources || []).map(s => ({ value: s.value, label: s.label }))} />
          </Form.Item>
          <Form.Item name="related_content" label="关联内容（可选）">
            <Input placeholder="如：养老金避坑 3 问" />
          </Form.Item>
          <Form.Item name="preferred_time" label="期望联系时间">
            <Input placeholder="如：今晚 8 点后" />
          </Form.Item>
          <Form.Item name="remark" label="备注">
            <Input.TextArea rows={3} placeholder="进线说明" />
          </Form.Item>
          <Form.Item name="status" label="状态" rules={[{ required: true }]}>
            <Select
              options={(meta.statuses || [])
                .filter(s => s.value !== 'converted')
                .map(s => ({ value: s.value, label: s.label }))}
            />
          </Form.Item>
        </Form>

        <Space wrap style={{ marginTop: 8 }}>
          {editing && editing.status !== 'converted' && editing.status !== 'invalid' && (
            <Button type="primary" onClick={() => handleConvert(editing)}>转为客户</Button>
          )}
          <Button type={editing ? 'default' : 'primary'} loading={saving} onClick={handleSave}>
            保存
          </Button>
          {editing && editing.status !== 'invalid' && editing.status !== 'converted' && (
            <Button danger onClick={() => handleInvalid(editing)}>标为无效</Button>
          )}
          <Button onClick={() => setDrawerOpen(false)}>关闭</Button>
        </Space>
      </Drawer>
    </div>
  )
}
