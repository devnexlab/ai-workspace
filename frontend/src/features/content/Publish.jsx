import { useState, useEffect, useMemo } from 'react'
import {
  Table, Tag, Button, Input, Select, Space, Modal, message,
  Popconfirm, Tooltip, Row, Col, Card, Statistic, Form, Alert,
} from 'antd'
import {
  PlusOutlined, DeleteOutlined, SearchOutlined, ReloadOutlined,
  RocketOutlined, CheckOutlined, LinkOutlined,
} from '@ant-design/icons'
import { Link, useSearchParams } from 'react-router-dom'
import { publishApi, videosApi, platformsApi } from '../../api'
import { formatDateTime } from '../../utils/date'

const statusOptions = [
  { value: 'pending', label: '待发布' },
  { value: 'reviewing', label: '待确认' },
  { value: 'done', label: '已发布' },
  { value: 'failed', label: '失败' },
]
const statusColors = { pending: 'default', reviewing: 'processing', done: 'success', failed: 'error' }
const statusLabels = { pending: '待发布', reviewing: '待确认', done: '已发布', failed: '失败' }

export default function Publish() {
  const [searchParams] = useSearchParams()
  const [data, setData] = useState({ list: [], total: 0 })
  const [loading, setLoading] = useState(true)
  const [page, setPage] = useState(1)
  const [filters, setFilters] = useState({})
  const [focusId, setFocusId] = useState(null)
  const [createModal, setCreateModal] = useState(false)
  const [confirmModal, setConfirmModal] = useState({ open: false, id: null })
  const [confirmUrl, setConfirmUrl] = useState('')
  const [publishing, setPublishing] = useState(null)
  const [videos, setVideos] = useState([])
  const [pubStatus, setPubStatus] = useState({})
  const [platforms, setPlatforms] = useState([])
  const [sessions, setSessions] = useState([])
  const [form] = Form.useForm()

  const platformOptions = useMemo(
    () => platforms
      .filter(p => p.enable_publish !== false)
      .map(p => ({ value: p.key, label: p.label })),
    [platforms],
  )
  const platformLabels = useMemo(
    () => Object.fromEntries(platforms.map(p => [p.key, p.label])),
    [platforms],
  )
  const platformColors = useMemo(
    () => Object.fromEntries(platforms.map(p => [p.key, p.color || 'blue'])),
    [platforms],
  )

  const loadData = (p = page, f = filters) => {
    setLoading(true)
    publishApi.list({ page: p, pageSize: 15, ...f })
      .then(res => { setData(res); setPage(p) })
      .finally(() => setLoading(false))
  }

  const loadSessions = () => {
    publishApi.sessions()
      .then(res => setSessions(res.list || []))
      .catch(() => {})
  }

  useEffect(() => {
    const status = searchParams.get('status') || ''
    const focus = searchParams.get('focus')
    const next = {}
    if (status) next.status = status === 'pending' ? '' : status
    // status=pending 时拉待发+待确认：不传 status，前端可再滤；简单起见传 reviewing 或留空后本地不高亮够用
    if (status === 'reviewing') next.status = 'reviewing'
    setFilters(next)
    if (focus) setFocusId(Number(focus) || focus)
    loadData(1, next)
    publishApi.status().then(setPubStatus).catch(() => {})
    platformsApi.list()
      .then(res => setPlatforms(res.list || []))
      .catch(() => {})
    loadSessions()
    const timer = setInterval(loadSessions, 10000)
    return () => clearInterval(timer)
  }, [searchParams])

  const loadVideos = () => {
    videosApi.list({ export_status: 'done', pageSize: 100 }).then(res => setVideos(res.list)).catch(() => {})
  }

  const handleCreate = () => {
    form.validateFields().then(values => {
      publishApi.create(values).then(() => {
        message.success('发布任务已创建')
        setCreateModal(false)
        form.resetFields()
        loadData(1)
      })
    })
  }

  const handlePublish = (id) => {
    setPublishing(id)
    publishApi.publish(id).then(res => {
      if (res.status === 'pending_review') {
        message.info({
          content: res.message || '内容已填好：请到已打开的浏览器里点「发布/发表」，回来后点「确认已发」并可选填作品链接。',
          duration: 10,
        })
      } else if (res.status === 'need_login') {
        message.warning({
          content: res.message || '需要登录：请在已打开的浏览器中扫码登录；登录成功后会尽量继续填充。若仍失败，请到「设置·发布」检查 Cookie。',
          duration: 14,
        })
      } else if (res.status === 'error') {
        message.error({
          content: res.message || '发布失败，请查看列表中的失败原因后重试',
          duration: 10,
        })
      } else {
        message.success(res.message || '发布成功')
      }
      loadData()
      loadSessions()
      publishApi.status().then(setPubStatus)
    }).catch(err => {
      message.error(err?.error || err?.message || '发布失败')
    }).finally(() => setPublishing(null))
  }

  const openConfirm = (id) => {
    setConfirmUrl('')
    setConfirmModal({ open: true, id })
  }

  const handleConfirm = () => {
    const id = confirmModal.id
    if (!id) return
    publishApi.confirm(id, { publish_url: confirmUrl.trim() }).then(() => {
      message.success(confirmUrl.trim() ? '已标记已发布，并保存作品链接' : '已标记为已发布')
      setConfirmModal({ open: false, id: null })
      setConfirmUrl('')
      loadData()
    }).catch(err => message.error(err?.error || '确认失败'))
  }

  const handleCloseSession = (sid) => {
    publishApi.closeSession(sid).then(() => {
      message.success('已请求关闭浏览器')
      setTimeout(loadSessions, 1500)
    }).catch(() => message.error('关闭失败'))
  }

  const columns = [
    { title: 'ID', dataIndex: 'id', width: 60 },
    { title: '视频', dataIndex: 'video_title', width: 140, ellipsis: true,
      render: v => v || '-' },
    { title: '标题', dataIndex: 'title', ellipsis: true },
    {
      title: '平台', dataIndex: 'platform', width: 100,
      render: v => v
        ? <Tag color={platformColors[v]}>{platformLabels[v] || v}</Tag>
        : '-',
    },
    { title: '描述', dataIndex: 'description', width: 200, ellipsis: true },
    { title: '标签', dataIndex: 'tags', width: 120, ellipsis: true },
    {
      title: '状态', dataIndex: 'status', width: 90,
      render: v => <Tag color={statusColors[v]}>{statusLabels[v] || v}</Tag>
    },
    {
      title: '作品链接', dataIndex: 'publish_url', width: 140, ellipsis: true,
      render: (v) => (v
        ? <a href={v} target="_blank" rel="noreferrer"><LinkOutlined /> 查看</a>
        : '-'),
    },
    {
      title: '失败原因', dataIndex: 'error_msg', width: 160, ellipsis: true,
      render: (v, r) => (r.status === 'failed' || r.status === 'reviewing'
        ? <Tooltip title={v}><span style={{ color: r.status === 'failed' ? '#cf1322' : '#64748b', fontSize: 12 }}>{v || '-'}</span></Tooltip>
        : '-'),
    },
    { title: '发布时间', dataIndex: 'published_at', width: 160, render: v => formatDateTime(v) },
    { title: '定时', dataIndex: 'scheduled_time', width: 160, render: v => formatDateTime(v) },
    { title: '创建时间', dataIndex: 'created_at', width: 160, render: v => formatDateTime(v) },
    {
      title: '操作', key: 'action', width: 200, fixed: 'right',
      render: (_, r) => (
        <Space size="small">
          {r.status === 'reviewing' || r.status === 'pending' ? (
            <Tooltip title={r.status === 'reviewing' ? '平台已点发布？确认并回写链接' : '打开发布页自动填充'}>
              <Button
                size="small"
                type="primary"
                ghost
                icon={r.status === 'reviewing' ? <CheckOutlined /> : <RocketOutlined />}
                loading={publishing === r.id}
                onClick={() => (r.status === 'reviewing' ? openConfirm(r.id) : handlePublish(r.id))}
              >
                {r.status === 'reviewing' ? '确认已发' : '发布'}
              </Button>
            </Tooltip>
          ) : null}
          {r.status === 'reviewing' ? (
            <Tooltip title="重新打开浏览器发布">
              <Button
                size="small"
                icon={<RocketOutlined />}
                loading={publishing === r.id}
                onClick={() => handlePublish(r.id)}
              />
            </Tooltip>
          ) : null}
          {r.status === 'done' && !r.publish_url ? (
            <Tooltip title="补填作品链接">
              <Button size="small" icon={<LinkOutlined />} onClick={() => openConfirm(r.id)} />
            </Tooltip>
          ) : null}
          {r.status === 'failed' ? (
            <Tooltip title={r.error_msg ? `失败原因：${r.error_msg}` : '重试发布'}>
              <Button
                size="small"
                type="primary"
                ghost
                icon={<RocketOutlined />}
                loading={publishing === r.id}
                onClick={() => handlePublish(r.id)}
              />
            </Tooltip>
          ) : null}
          <Popconfirm title="确认删除？" onConfirm={() => {
            publishApi.delete(r.id).then(() => { message.success('已删除'); loadData() })
          }}>
            <Button size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      )
    },
  ]

  const unconfigured = Object.entries(pubStatus)
    .filter(([k, v]) => k !== 'playwright_installed' && v && !v.enabled)
    .map(([k, v]) => v.platform_name || k)

  return (
    <div>
      <div className="page-title">发布中心</div>
      <div className="page-desc">
        选择成品视频，半自动打开抖音 / 小红书 / 视频号创作者后台并填充内容；你在平台点发表后，回到这里「确认已发」并可填写作品链接。
      </div>

      {pubStatus.playwright_installed === false && (
        <Alert type="warning" showIcon style={{ marginBottom: 16 }}
          message="Playwright 未安装"
          description="自动发布需要 Playwright。请运行: pip install playwright && playwright install chromium" />
      )}

      {unconfigured.length > 0 && (
        <Alert type="info" showIcon style={{ marginBottom: 16 }}
          message="部分平台发布未启用"
          description={
            <span>
              请到 <Link to="/settings/publish">系统设置 · 发布平台</Link> 启用并配置：
              {unconfigured.join('、')}
            </span>
          }
        />
      )}

      {sessions.length > 0 && (
        <Card size="small" style={{ marginBottom: 16 }}
          title={<span><RocketOutlined /> 正在打开的发布浏览器（确认发布后再关闭）</span>}>
          <Space direction="vertical" style={{ width: '100%' }}>
            {sessions.map(s => (
              <div key={s.id} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <Tag color={s.status === 'need_login' ? 'warning' : 'processing'}>{s.label}</Tag>
                <span style={{ flex: 1, color: '#555' }}>{s.message}</span>
                <Button size="small" onClick={() => handleCloseSession(s.id)}>关闭浏览器</Button>
              </div>
            ))}
          </Space>
        </Card>
      )}

      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={6}><Card size="small"><Statistic title="发布任务" value={data.total} prefix={<RocketOutlined />} /></Card></Col>
        <Col span={6}><Card size="small"><Statistic title="已发布" value={data.list.filter(d => d.status === 'done').length} valueStyle={{ color: '#52c41a' }} /></Card></Col>
        <Col span={6}><Card size="small"><Statistic title="待发布" value={data.list.filter(d => d.status === 'pending').length} /></Card></Col>
        <Col span={6}><Card size="small"><Statistic title="待确认" value={data.list.filter(d => d.status === 'reviewing').length} /></Card></Col>
      </Row>

      <div className="table-toolbar">
        <div className="table-toolbar-left">
          <Select placeholder="平台" allowClear style={{ width: 120 }}
            value={filters.platform}
            onChange={v => setFilters({ ...filters, platform: v })}
            options={platformOptions} />
          <Select placeholder="状态" allowClear style={{ width: 120 }}
            value={filters.status}
            onChange={v => setFilters({ ...filters, status: v })}
            options={statusOptions} />
          <Button type="primary" icon={<SearchOutlined />} onClick={() => loadData(1, filters)}>搜索</Button>
          <Button icon={<ReloadOutlined />} onClick={() => { setFilters({}); loadData(1, {}) }}>重置</Button>
        </div>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => {
          loadVideos(); form.resetFields(); setCreateModal(true)
        }}>创建发布任务</Button>
      </div>

      <Table columns={columns} dataSource={data.list} rowKey="id" loading={loading}
        scroll={{ x: 1600 }}
        rowClassName={(r) => (String(r.id) === String(focusId) ? 'row-focus' : '')}
        pagination={{
          current: page, total: data.total, pageSize: 15,
          onChange: (p) => loadData(p),
          showTotal: (t) => `共 ${t} 条`,
        }}
        size="middle" />

      <Modal
        title="确认已发布"
        open={confirmModal.open}
        onOk={handleConfirm}
        onCancel={() => setConfirmModal({ open: false, id: null })}
        okText="确认已发"
      >
        <p style={{ marginBottom: 12, color: '#64748b' }}>
          请确认已在平台点过发表。可选填作品链接，方便以后回看。
        </p>
        <Input
          prefix={<LinkOutlined />}
          placeholder="作品链接（可选）https://..."
          value={confirmUrl}
          onChange={(e) => setConfirmUrl(e.target.value)}
        />
      </Modal>

      <Modal title="创建发布任务" open={createModal} onOk={handleCreate}
        onCancel={() => setCreateModal(false)} width={560}>
        <Form form={form} layout="vertical" style={{ marginTop: 16 }}>
          <Form.Item name="video_task_id" label="选择视频" rules={[{ required: true }]}>
            <Select showSearch optionFilterProp="label"
              options={videos.map(v => ({ label: v.title, value: v.id }))} />
          </Form.Item>
          <Form.Item name="platform" label="发布平台" rules={[{ required: true }]}>
            <Select options={platformOptions} placeholder="选择平台" />
          </Form.Item>
          <Form.Item name="title" label="发布标题">
            <Input placeholder="视频标题" />
          </Form.Item>
          <Form.Item name="description" label="描述">
            <Input.TextArea rows={3} />
          </Form.Item>
          <Form.Item name="tags" label="标签">
            <Input placeholder="逗号分隔" />
          </Form.Item>
          <Form.Item name="cover_text" label="封面文案">
            <Input />
          </Form.Item>
        </Form>
        <Alert type="info" message="发布时会打开浏览器自动填充内容，浏览器会一直保持打开，等你手动点完发布再关掉即可。" />
      </Modal>
    </div>
  )
}
