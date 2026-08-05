import { useState, useEffect, useMemo } from 'react'
import {
  Table, Tag, Button, Input, Select, Space, Modal, message,
  Popconfirm, Tooltip, Row, Col, Card, Statistic, Form, Alert, Checkbox, Switch,
} from 'antd'
import {
  PlusOutlined, DeleteOutlined, SearchOutlined, ReloadOutlined,
  RocketOutlined, CheckOutlined, LinkOutlined, SyncOutlined,
  CopyOutlined,
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
  const [confirmConsult, setConfirmConsult] = useState(false)
  const [weekStats, setWeekStats] = useState(null)
  const [publishing, setPublishing] = useState(null)
  const [syncing, setSyncing] = useState(null)
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
    publishApi.analytics({ range: 'week' }).then(setWeekStats).catch(() => setWeekStats(null))
    platformsApi.list()
      .then(res => setPlatforms(res.list || []))
      .catch(() => {})
    loadSessions()
    const timer = setInterval(loadSessions, 10000)
    return () => clearInterval(timer)
  }, [searchParams])

  // 确认弹窗打开时，若会话新抓到链接则自动填入
  useEffect(() => {
    if (!confirmModal.open || !confirmModal.id || confirmUrl.trim()) return
    const row = data.list.find(x => x.id === confirmModal.id)
    const fromSession = sessions.find(s =>
      s.task_id === confirmModal.id || (row?.session_id && s.id === row.session_id)
    )
    const autoUrl = (row?.publish_url || fromSession?.detected_url || '').trim()
    if (autoUrl) setConfirmUrl(autoUrl)
  }, [sessions, confirmModal, data.list])

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

  const handlePrepare = (id) => {
    setPublishing(id)
    publishApi.prepare(id).then(async (res) => {
      const text = res.clipboard_text || ''
      if (text && navigator.clipboard?.writeText) {
        try {
          await navigator.clipboard.writeText(text)
          message.success('文案已复制到剪贴板')
        } catch {
          Modal.info({
            title: '请手动复制文案',
            width: 520,
            content: <Input.TextArea value={text} rows={8} readOnly />,
          })
        }
      } else if (text) {
        Modal.info({
          title: '请手动复制文案',
          width: 520,
          content: <Input.TextArea value={text} rows={8} readOnly />,
        })
      }
      if (res.creator_url) {
        window.open(res.creator_url, '_blank', 'noopener,noreferrer')
      }
      message.info({
        content: res.message || '请在官方创作者页上传成片、粘贴文案并点发表，然后回来「确认已发」',
        duration: 8,
      })
      loadData()
    }).catch(err => {
      message.error(err?.error || err?.message || '准备发布失败')
    }).finally(() => setPublishing(null))
  }

  const handlePublish = (id) => {
    Modal.confirm({
      title: '使用浏览器自动填充？（高风险）',
      content: '会用自动化浏览器登录创作者后台填表，个人号有封号风险。推荐改用「准备发布」：复制文案并打开官方页，由你手动点发表。',
      okText: '仍要自动填充',
      okButtonProps: { danger: true },
      cancelText: '取消',
      onOk: () => {
        setPublishing(id)
        return publishApi.publish(id, { force_autofill: true }).then(res => {
          if (res.status === 'pending_review') {
            message.info({
              content: res.message || '内容已填好：请到已打开的浏览器里点「发布/发表」，回来后点「确认已发」。',
              duration: 10,
            })
          } else if (res.status === 'need_login') {
            message.warning({
              content: res.message || '需要登录：请在已打开的浏览器中扫码登录。',
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
      },
    })
  }

  const openConfirm = (id) => {
    const row = data.list.find(x => x.id === id)
    const fromSession = sessions.find(s =>
      s.task_id === id || (row?.session_id && s.id === row.session_id)
    )
    const autoUrl = (row?.publish_url || fromSession?.detected_url || '').trim()
    setConfirmUrl(autoUrl)
    setConfirmConsult(!!row?.got_consult)
    setConfirmModal({ open: true, id })
  }

  const handleConfirm = () => {
    const id = confirmModal.id
    if (!id) return
    publishApi.confirm(id, { publish_url: confirmUrl.trim(), got_consult: confirmConsult }).then(() => {
      message.success(confirmUrl.trim() ? '已标记已发布，并保存作品链接' : '已标记为已发布')
      setConfirmModal({ open: false, id: null })
      setConfirmUrl('')
      setConfirmConsult(false)
      loadData()
      publishApi.analytics({ range: 'week' }).then(setWeekStats).catch(() => {})
    }).catch(err => message.error(err?.error || '确认失败'))
  }

  const handleSync = (id) => {
    setSyncing(id)
    publishApi.sync(id).then(res => {
      message.success(res.message || '同步完成')
      loadData()
      publishApi.analytics({ range: 'week' }).then(setWeekStats).catch(() => {})
    }).catch(err => {
      message.error(err?.error || err?.message || '同步失败：请确认已登录创作者后台，或先保持发布浏览器打开')
    }).finally(() => setSyncing(null))
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
      title: '有咨询', dataIndex: 'got_consult', width: 90,
      render: (v, r) => (
        <Switch
          size="small"
          checked={!!v}
          disabled={r.status !== 'done'}
          onChange={(checked) => {
            publishApi.update(r.id, { got_consult: checked })
              .then(() => {
                message.success(checked ? '已标记有咨询' : '已取消咨询标记')
                loadData()
                publishApi.analytics({ range: 'week' }).then(setWeekStats).catch(() => {})
              })
              .catch(err => message.error(err?.error || '更新失败'))
          }}
        />
      ),
    },
    {
      title: '赞/评', key: 'engage', width: 80,
      render: (_, r) => (
        <span style={{ fontSize: 12, color: '#64748b' }}>
          {Number(r.likes || 0)}/{Number(r.comments || 0)}
        </span>
      ),
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
      title: '操作', key: 'action', width: 260, fixed: 'right',
      render: (_, r) => (
        <Space size="small">
          {r.status === 'reviewing' || r.status === 'pending' ? (
            <Tooltip title={r.status === 'reviewing' ? '平台已点发表？确认并回写链接' : '复制文案并打开官方创作者页（推荐，不易封号）'}>
              <Button
                size="small"
                type="primary"
                ghost
                icon={r.status === 'reviewing' ? <CheckOutlined /> : <CopyOutlined />}
                loading={publishing === r.id}
                onClick={() => (r.status === 'reviewing' ? openConfirm(r.id) : handlePrepare(r.id))}
              >
                {r.status === 'reviewing' ? '确认已发' : '准备发布'}
              </Button>
            </Tooltip>
          ) : null}
          {r.status === 'pending' || r.status === 'reviewing' || r.status === 'failed' ? (
            <Tooltip title="高级：浏览器自动填充（有封号风险）">
              <Button
                size="small"
                icon={<RocketOutlined />}
                loading={publishing === r.id}
                onClick={() => handlePublish(r.id)}
              />
            </Tooltip>
          ) : null}
          {(r.status === 'done' || r.status === 'reviewing') ? (
            <Tooltip title="从创作者后台同步作品链接与点赞/评论（可选，仍可能需登录浏览器）">
              <Button
                size="small"
                icon={<SyncOutlined />}
                loading={syncing === r.id}
                onClick={() => handleSync(r.id)}
              >
                同步
              </Button>
            </Tooltip>
          ) : null}
          {r.status === 'done' && !r.publish_url ? (
            <Tooltip title="补填作品链接">
              <Button size="small" icon={<LinkOutlined />} onClick={() => openConfirm(r.id)} />
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
        安全流程：点「准备发布」→ 自动复制文案并打开官方创作者页 → 你在平台上传成片并点发表 → 回本系统「确认已发」。火箭按钮是高级自动填充（易封号，不推荐）。
      </div>

      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 16 }}
        message="已改为人工确认发布，降低封号风险"
        description={
          <span>
            日常请用「准备发布」。平台登录态自动采集默认已关闭，选题请走内容情报的全网热榜。
            发布平台可在 <Link to="/settings/publish">设置 · 发布平台</Link> 启用。
          </span>
        }
      />

      {pubStatus.playwright_installed === false && (
        <Alert type="info" showIcon style={{ marginBottom: 16 }}
          message="Playwright 未安装（可选）"
          description="安全发布模式不需要 Playwright。仅当你使用「浏览器自动填充」高级功能时才需要安装。" />
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
                {s.detected_url ? (
                  <a href={s.detected_url} target="_blank" rel="noreferrer" style={{ fontSize: 12 }}>已抓到链接</a>
                ) : null}
                <Button size="small" onClick={() => handleCloseSession(s.id)}>关闭浏览器</Button>
              </div>
            ))}
          </Space>
        </Card>
      )}

      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={6}><Card size="small"><Statistic title="发布任务" value={data.total} prefix={<RocketOutlined />} /></Card></Col>
        <Col span={6}><Card size="small"><Statistic title="本周已发" value={weekStats?.published ?? '-'} valueStyle={{ color: '#52c41a' }} /></Card></Col>
        <Col span={6}><Card size="small"><Statistic title="本周有咨询" value={weekStats?.consult ?? '-'} /></Card></Col>
        <Col span={6}><Card size="small"><Statistic title="咨询率" value={weekStats ? `${Math.round((weekStats.consult_rate || 0) * 100)}%` : '-'} /></Card></Col>
      </Row>
      {weekStats?.by_content_type?.length > 0 && (
        <Card size="small" style={{ marginBottom: 16 }} title="本周选题类型">
          <Space wrap>
            {weekStats.by_content_type.map((x) => (
              <Tag key={x.key} color={x.key === 'insurance' ? 'gold' : 'blue'}>
                {x.label} {x.count} 条 · 咨询 {x.consult}
              </Tag>
            ))}
          </Space>
        </Card>
      )}

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
          请确认已在平台点过发表。若发布会话已抓到作品链接会自动填入；也可稍后点「同步」从作品管理页拉取。
        </p>
        <Input
          prefix={<LinkOutlined />}
          placeholder="作品链接（可选，可自动回填）https://..."
          value={confirmUrl}
          onChange={(e) => setConfirmUrl(e.target.value)}
        />
        <div style={{ marginTop: 12 }}>
          <Checkbox checked={confirmConsult} onChange={(e) => setConfirmConsult(e.target.checked)}>
            这条带来了咨询 / 私信（也可事后用「同步」按赞/评自动标）
          </Checkbox>
        </div>
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
        <Alert type="info" message="创建后请点「准备发布」：复制文案并打开官方创作者页，由你在平台上传成片并点发表，再回本系统确认。避免自动化登录封号。" />
      </Modal>
    </div>
  )
}
