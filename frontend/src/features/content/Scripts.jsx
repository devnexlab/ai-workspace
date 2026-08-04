import { useState, useEffect } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import {
  Table, Tag, Button, Input, Select, Space, Modal, message,
  Popconfirm, Tooltip, Row, Col, Card, Form, Drawer, Alert, Badge, Empty,
} from 'antd'
import {
  PlusOutlined, DeleteOutlined, SearchOutlined, ReloadOutlined,
  RobotOutlined, EditOutlined, EyeOutlined, ThunderboltOutlined,
  VideoCameraOutlined, CheckCircleOutlined, FileOutlined,
} from '@ant-design/icons'
import { scriptsApi, settingsApi, materialsApi, videosApi } from '../../api'
import { formatDateTime } from '../../utils/date'

const { TextArea } = Input

const statusOptions = [
  { value: 'draft', label: '草稿' },
  { value: 'used', label: '已出片' },
]
const statusColors = {
  draft: 'default', reviewing: 'processing', approved: 'success',
  rejected: 'error', used: 'green',
}
const statusLabels = {
  draft: '草稿', reviewing: '草稿', approved: '草稿',
  rejected: '草稿', used: '已出片',
}
const typeLabels = { traffic: '泛流量', insurance: '保险干货' }
const typeColors = { traffic: 'blue', insurance: 'orange' }
const ageLabels = {
  '20s': '20岁段', '30s': '30岁段', '40s': '40岁段',
  '50s': '50岁段', '60s': '60岁段', '70s': '70岁段', '80s': '80岁+', all: '全年龄',
}

export default function Scripts() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const [data, setData] = useState({ list: [], total: 0 })
  const [loading, setLoading] = useState(true)
  const [page, setPage] = useState(1)
  const [filters, setFilters] = useState({})
  const [focusId, setFocusId] = useState(null)
  const [editModal, setEditModal] = useState(false)
  const [viewDrawer, setViewDrawer] = useState(false)
  const [genModal, setGenModal] = useState(false)
  const [generating, setGenerating] = useState(false)
  const [planning, setPlanning] = useState(false)
  const [runningDaily, setRunningDaily] = useState(false)
  const [producingId, setProducingId] = useState(null)
  const [produceModal, setProduceModal] = useState({ open: false, script: null })
  const [produceMaterials, setProduceMaterials] = useState([])
  const [produceSelectedIds, setProduceSelectedIds] = useState([])
  const [produceVoice, setProduceVoice] = useState(undefined)
  const [voiceOptions, setVoiceOptions] = useState([])
  const [dailyStatus, setDailyStatus] = useState(null)
  const [editing, setEditing] = useState(null)
  const [viewing, setViewing] = useState(null)
  const [form] = Form.useForm()
  const [genForm] = Form.useForm()
  const [readiness, setReadiness] = useState({})
  const [brandEnding, setBrandEnding] = useState('')

  const loadData = (p = page, f = filters) => {
    setLoading(true)
    scriptsApi.list({ page: p, pageSize: 15, ...f })
      .then(res => { setData(res); setPage(p) })
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    const status = searchParams.get('status') || ''
    const focus = searchParams.get('focus')
    const next = {}
    if (status) next.status = status
    setFilters(next)
    if (focus) setFocusId(Number(focus) || focus)
    loadData(1, next)
    settingsApi.check().then(setReadiness).catch(() => {})
    settingsApi.get().then(res => {
      const list = res?.system || []
      const item = Array.isArray(list) ? list.find(s => s.key === 'fixed_ending') : null
      setBrandEnding(item?.value || '祁实说实话，替你的保单说话，给你最放心的选择。关注我，来找我。')
    }).catch(() => {
      setBrandEnding('祁实说实话，替你的保单说话，给你最放心的选择。关注我，来找我。')
    })
    scriptsApi.dailyRunStatus().then(setDailyStatus).catch(() => {})
  }, [searchParams])

  const handleDailyPlan = () => {
    setPlanning(true)
    scriptsApi.dailyPlan({})
      .then(res => {
        message.success(res.message || '今日计划已生成')
        if (res.errors?.length) message.warning(res.errors.join('；'))
        if (res.brand_ending) setBrandEnding(res.brand_ending)
        loadData(1)
        scriptsApi.dailyRunStatus().then(setDailyStatus).catch(() => {})
      })
      .catch(err => message.error(err?.error || '生成失败，请检查 AI 与热点采集'))
      .finally(() => setPlanning(false))
  }

  const handleDailyRun = () => {
    setRunningDaily(true)
    message.loading({ content: '日更编排中：采热点 → 写文案 → 出片…', key: 'daily-run', duration: 0 })
    scriptsApi.dailyRun({ refresh: true, produce_video: true, include_platforms: false })
      .then(res => {
        message.success({ content: res.message || '日更已启动', key: 'daily-run', duration: 6 })
        if (res.steps?.plan?.errors?.length) {
          message.warning(res.steps.plan.errors.join('；'))
        }
        loadData(1)
        scriptsApi.dailyRunStatus().then(setDailyStatus).catch(() => {})
      })
      .catch(err => message.error({ content: err?.error || err?.message || '日更失败', key: 'daily-run' }))
      .finally(() => setRunningDaily(false))
  }

  const handleProduce = (row) => {
    setProduceModal({ open: true, script: row })
    setProduceSelectedIds([])
    setProduceVoice(undefined)
    materialsApi.list({ asset_kind: 'scene', pageSize: 100 })
      .then(res => setProduceMaterials(res.list || []))
      .catch(() => setProduceMaterials([]))
    videosApi.lastPrefs().then(prefs => {
      const ids = String(prefs?.material_ids || '')
        .split(',')
        .map(x => Number(x.trim()))
        .filter(Boolean)
      setProduceSelectedIds(ids)
      if (prefs?.voice) setProduceVoice(prefs.voice)
    }).catch(() => {})
    videosApi.voiceOptions().then(res => {
      setVoiceOptions(res.voices || [])
    }).catch(() => {})
  }

  const confirmProduce = () => {
    const row = produceModal.script
    if (!row) return
    setProducingId(row.id)
    const payload = {
      material_ids: produceSelectedIds.join(','),
      voice: produceVoice || '',
    }
    scriptsApi.produce(row.id, payload)
      .then(res => {
        message.success(res.message || '已创建视频任务')
        setProduceModal({ open: false, script: null })
        loadData()
        if (viewing?.id === row.id) {
          setViewing({ ...viewing, status: 'used' })
          setViewDrawer(false)
        }
        const vid = res.video_id
        navigate(vid ? `/videos?focus=${vid}` : '/videos')
      })
      .catch(err => message.error(err?.error || err?.message || '出片失败'))
      .finally(() => setProducingId(null))
  }

  const handleSave = () => {
    form.validateFields().then(values => {
      if (editing) {
        scriptsApi.update(editing.id, values).then(() => {
          message.success('已更新'); setEditModal(false); loadData()
        })
      } else {
        scriptsApi.create(values).then(() => {
          message.success('文案已创建'); setEditModal(false); loadData(1)
        })
      }
    })
  }

  const handleGenerate = () => {
    const values = genForm.getFieldsValue()
    setGenerating(true)
    scriptsApi.generate({
      topic_id: values.topic_id || undefined,
      prompt: values.prompt || undefined,
      style: values.style,
      duration: values.duration,
      tone: values.tone,
      audience: values.audience,
      extra_req: values.extra_req,
      content_type: values.content_type,
      age_band: values.age_band,
    }).then(() => {
      message.success('文案生成成功')
      setGenModal(false)
      loadData(1)
    }).catch(err => {
      message.error(err?.error || '生成失败，请检查 AI 配置')
    }).finally(() => setGenerating(false))
  }

  const columns = [
    { title: 'ID', dataIndex: 'id', width: 60 },
    {
      title: '类型', dataIndex: 'content_type', width: 90,
      render: v => <Tag color={typeColors[v] || 'default'}>{typeLabels[v] || v || '泛流量'}</Tag>,
    },
    {
      title: '年龄段', dataIndex: 'age_band', width: 80,
      render: v => ageLabels[v] || v || '-',
    },
    { title: '标题', dataIndex: 'title', ellipsis: true },
    {
      title: '来源热点', dataIndex: 'topic_title', width: 120, ellipsis: true,
      render: v => v || '-',
    },
    {
      title: '封面文案', dataIndex: 'cover_text', width: 100, ellipsis: true,
      render: v => v || '-',
    },
    {
      title: '状态', dataIndex: 'status', width: 80,
      render: v => <Tag color={statusColors[v] || 'default'}>{statusLabels[v] || v}</Tag>,
    },
    { title: '创建时间', dataIndex: 'created_at', width: 160, render: v => formatDateTime(v) },
    {
      title: '操作', key: 'action', width: 200, fixed: 'right',
      render: (_, r) => (
        <Space size="small">
          <Tooltip title="查看">
            <Button size="small" icon={<EyeOutlined />} onClick={() => {
              setViewing(r); setViewDrawer(true)
            }} />
          </Tooltip>
          <Tooltip title="编辑">
            <Button size="small" icon={<EditOutlined />} onClick={() => {
              setEditing(r); form.setFieldsValue(r); setEditModal(true)
            }} />
          </Tooltip>
          <Tooltip title="出片（创建视频任务）">
            <Button
              size="small"
              type="primary"
              ghost
              icon={<VideoCameraOutlined />}
              loading={producingId === r.id}
              onClick={() => handleProduce(r)}
            >
              出片
            </Button>
          </Tooltip>
          <Popconfirm title="确认删除？" onConfirm={() => {
            scriptsApi.delete(r.id).then(() => { message.success('已删除'); loadData() })
          }}>
            <Button size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <div>
      <div className="page-title">文案中心</div>
      <div className="page-desc">
        管理口播文案，点「出片」可选场景素材并创建视频任务。出片后状态变为「已出片」，仍可再次出片（有进行中的任务会复用并更新素材，已完成的可新建）。
      </div>

      {!readiness.ai?.ready && (
        <Alert
          type="warning"
          showIcon
          style={{ marginBottom: 16 }}
          message="AI 未配置"
          description={(
            <span>
              请到 <Link to="/settings/ai">系统设置 · AI 大模型</Link> 填写 API Key 后才能使用 AI 生成文案
            </span>
          )}
        />
      )}

      <Row gutter={[12, 12]} style={{ marginBottom: 16 }}>
        {[
          {
            title: '文案总数',
            value: data.total,
            color: '#0f172a',
          },
          {
            title: '今日泛流量',
            value: dailyStatus?.scripts?.traffic || 0,
            suffix: `/ ${dailyStatus?.traffic_target || 2}`,
            color: '#1677ff',
          },
          {
            title: '今日保险',
            value: dailyStatus?.scripts?.insurance || 0,
            suffix: `/ ${dailyStatus?.insurance_target || 1}`,
            color: '#fa8c16',
          },
          {
            title: '今日已出片',
            value: dailyStatus?.videos?.done || 0,
            color: '#52c41a',
            onClick: () => navigate('/videos'),
            hint: '点击查看视频',
          },
        ].map((item) => (
          <Col xs={12} sm={6} key={item.title}>
            <Card
              size="small"
              className="stat-card"
              hoverable={!!item.onClick}
              onClick={item.onClick}
              styles={{ body: { padding: '16px 12px', textAlign: 'center', minHeight: 96 } }}
              style={{ cursor: item.onClick ? 'pointer' : 'default' }}
            >
              <div style={{ fontSize: 13, color: '#64748b', marginBottom: 8 }}>{item.title}</div>
              <div style={{ fontSize: 28, fontWeight: 700, color: item.color, lineHeight: 1.2 }}>
                {item.value}
                {item.suffix ? (
                  <span style={{ fontSize: 16, fontWeight: 500, color: '#94a3b8', marginLeft: 4 }}>
                    {item.suffix}
                  </span>
                ) : null}
              </div>
              {item.hint ? (
                <div style={{ fontSize: 12, color: '#94a3b8', marginTop: 6 }}>{item.hint}</div>
              ) : (
                <div style={{ height: 18, marginTop: 6 }} />
              )}
            </Card>
          </Col>
        ))}
      </Row>

      {brandEnding ? (
        <div
          style={{
            marginBottom: 16,
            padding: '10px 14px',
            background: '#f8fafc',
            border: '1px solid #e2e8f0',
            borderRadius: 12,
            fontSize: 13,
            color: '#475569',
            display: 'flex',
            gap: 10,
            alignItems: 'flex-start',
            flexWrap: 'wrap',
          }}
        >
          <Tag color="blue" style={{ margin: 0 }}>品牌收口</Tag>
          <span style={{ flex: 1, minWidth: 200 }}>{brandEnding}</span>
        </div>
      ) : null}

      <div className="table-toolbar">
        <div className="table-toolbar-left">
          <Select
            placeholder="类型"
            allowClear
            style={{ width: 120 }}
            value={filters.content_type}
            onChange={v => setFilters({ ...filters, content_type: v })}
            options={[
              { value: 'traffic', label: '泛流量' },
              { value: 'insurance', label: '保险干货' },
            ]}
          />
          <Select
            placeholder="状态"
            allowClear
            style={{ width: 120 }}
            value={filters.status}
            onChange={v => setFilters({ ...filters, status: v })}
            options={statusOptions}
          />
          <Input
            placeholder="搜索标题/内容"
            allowClear
            style={{ width: 200 }}
            value={filters.q}
            onChange={e => setFilters({ ...filters, q: e.target.value })}
            onPressEnter={() => loadData(1, filters)}
          />
          <Button type="primary" icon={<SearchOutlined />} onClick={() => loadData(1, filters)}>搜索</Button>
          <Button icon={<ReloadOutlined />} onClick={() => { setFilters({}); loadData(1, {}) }}>重置</Button>
        </div>
        <Space wrap>
          <Tooltip
            title={(
              <div style={{ maxWidth: 280 }}>
                <div>会做：采全网热点 → 生成约 2 条流量 + 1 条干货文案 → 创建视频任务。</div>
                <div style={{ marginTop: 6 }}>不会：各平台口播专项采集、自动在平台点「发表」。发布请到发布中心确认。</div>
              </div>
            )}
          >
            <Button type="primary" icon={<ThunderboltOutlined />} loading={runningDaily} onClick={handleDailyRun}>
              今日计划并出片
            </Button>
          </Tooltip>
          <Button icon={<ThunderboltOutlined />} loading={planning} onClick={handleDailyPlan}>
            仅生成文案（2+1）
          </Button>
          <Button icon={<RobotOutlined />} loading={generating} onClick={() => setGenModal(true)}>
            AI 生成文案
          </Button>
          <Button icon={<PlusOutlined />} onClick={() => {
            setEditing(null); form.resetFields(); setEditModal(true)
          }}
          >
            手动添加
          </Button>
        </Space>
      </div>

      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 12 }}
        message="日更说明"
        description="「今日计划并出片」只到创建视频任务为止；真正发出去要在发布中心半自动填表后，你在平台点发表并确认。"
      />

      <Table
        columns={columns}
        dataSource={data.list}
        rowKey="id"
        rowClassName={(r) => (String(r.id) === String(focusId) ? 'row-focus' : '')}
        loading={loading}
        scroll={{ x: 1280 }}
        pagination={{
          current: page,
          total: data.total,
          pageSize: 15,
          onChange: (p) => loadData(p),
          showTotal: (t) => `共 ${t} 条`,
        }}
        size="middle"
      />

      <Modal
        title="AI 生成文案"
        open={genModal}
        onOk={handleGenerate}
        onCancel={() => setGenModal(false)}
        width={600}
        confirmLoading={generating}
      >
        <Form form={genForm} layout="vertical" style={{ marginTop: 16 }}>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="style" label="文案风格" initialValue="高转发共鸣">
                <Select options={[
                  { label: '高转发共鸣', value: '高转发共鸣' },
                  { label: '保险避坑干货', value: '保险避坑干货' },
                  { label: '干货分享', value: '干货分享' },
                  { label: '情感共鸣', value: '情感共鸣' },
                  { label: '知识科普', value: '知识科普' },
                  { label: '故事叙述', value: '故事叙述' },
                ]}
                />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="duration" label="视频时长" initialValue="60秒">
                <Select options={[
                  { label: '60秒口播（推荐）', value: '60秒' },
                  { label: '40-60秒', value: '40-60秒' },
                  { label: '15-30秒 (短快爆)', value: '15-30秒' },
                  { label: '1-3分钟 (深度)', value: '1-3分钟' },
                ]}
                />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="content_type" label="内容类型" initialValue="traffic">
                <Select options={[
                  { label: '泛流量涨粉', value: 'traffic' },
                  { label: '保险干货', value: 'insurance' },
                ]}
                />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="age_band" label="年龄段" initialValue="all">
                <Select options={[
                  { label: '全年龄 20-80', value: 'all' },
                  { label: '20岁段', value: '20s' },
                  { label: '30岁段', value: '30s' },
                  { label: '40岁段', value: '40s' },
                  { label: '50岁段', value: '50s' },
                  { label: '60岁段', value: '60s' },
                  { label: '70岁段', value: '70s' },
                  { label: '80岁+', value: '80s' },
                ]}
                />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item
                name="tone"
                label="文案语气"
                initialValue="casual"
                extra="不填则使用系统设置中的默认语气"
              >
                <Select
                  allowClear
                  placeholder="自动"
                  options={[
                    { label: '专业权威', value: 'professional' },
                    { label: '轻松口语化', value: 'casual' },
                    { label: '激情澎湃', value: 'passionate' },
                    { label: '幽默风趣', value: 'humorous' },
                    { label: '严肃认真', value: 'serious' },
                    { label: '亲切友好', value: 'friendly' },
                  ]}
                />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="audience" label="目标受众" extra="默认已覆盖 20-80 岁泛流量">
                <Input placeholder="留空使用默认" />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item name="prompt" label="创作主题/提示词" extra="填写后将从主题生成；不填则从爆款热点生成">
            <TextArea rows={3} placeholder="如：写一个关于AI工具提升效率的短视频文案" />
          </Form.Item>
          <Form.Item name="extra_req" label="额外要求" extra="如：必须提到XX工具、加入数据引用等">
            <TextArea rows={2} placeholder="可选" />
          </Form.Item>
        </Form>
        {!readiness.ai?.ready && (
          <Alert type="error" message="AI API Key 未配置，无法生成。请先在系统设置中配置。" />
        )}
      </Modal>

      <Modal
        title={editing ? '编辑文案' : '添加文案'}
        open={editModal}
        onOk={handleSave}
        onCancel={() => setEditModal(false)}
        width={640}
      >
        <Form form={form} layout="vertical" style={{ marginTop: 16 }}>
          <Form.Item name="title" label="标题" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="hook" label="钩子（开头3秒）">
            <TextArea rows={2} />
          </Form.Item>
          <Form.Item name="content" label="正文">
            <TextArea rows={5} />
          </Form.Item>
          <Form.Item name="ending" label="结尾（引导互动）">
            <TextArea rows={2} />
          </Form.Item>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="cover_text" label="封面文案"><Input /></Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="tags" label="标签"><Input placeholder="逗号分隔" /></Form.Item>
            </Col>
          </Row>
          <Form.Item name="status" label="状态" initialValue="draft">
            <Select options={statusOptions} />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title={`出片 — ${produceModal.script?.title || ''}`}
        open={produceModal.open}
        onOk={confirmProduce}
        onCancel={() => setProduceModal({ open: false, script: null })}
        okText="创建视频任务"
        confirmLoading={!!producingId}
        width={720}
        destroyOnClose
      >
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 12 }}
          message="请选择场景图片/视频（用于分镜背景）。不选则可用纯色背景，稍后也可在视频中心补选。"
        />
        <div style={{ marginBottom: 12 }}>
          <span style={{ marginRight: 8 }}>音色：</span>
          <Select
            allowClear
            placeholder="默认系统音色"
            style={{ width: 320 }}
            value={produceVoice}
            onChange={setProduceVoice}
            options={voiceOptions}
            showSearch
            optionFilterProp="label"
          />
        </div>
        <div style={{ marginBottom: 8, display: 'flex', justifyContent: 'space-between' }}>
          <Badge count={produceSelectedIds.length} offset={[8, 0]}>
            <span>场景素材</span>
          </Badge>
          <Button size="small" onClick={() => setProduceSelectedIds([])}>清空</Button>
        </div>
        {produceMaterials.length === 0 ? (
          <Empty description="暂无场景素材，可先到视频中心素材库上传" />
        ) : (
          <div style={{
            display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 10,
            maxHeight: 360, overflow: 'auto',
          }}>
            {produceMaterials.map(m => {
              const id = Number(m.id)
              const selected = produceSelectedIds.includes(id)
              return (
                <div
                  key={m.id}
                  onClick={() => setProduceSelectedIds(prev =>
                    prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id]
                  )}
                  style={{
                    border: selected ? '2px solid #1677ff' : '1px solid #e5e7eb',
                    borderRadius: 8, cursor: 'pointer', overflow: 'hidden', position: 'relative',
                  }}
                >
                  <div style={{
                    height: 88, background: '#f5f5f5',
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                  }}>
                    {m.type === 'image' ? (
                      <img
                        src={`/api/materials/${m.id}/preview`}
                        alt={m.name}
                        style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                      />
                    ) : (
                      <FileOutlined style={{ fontSize: 28, color: '#999' }} />
                    )}
                  </div>
                  <div style={{ padding: '4px 6px', fontSize: 12 }} title={m.name}>
                    {m.name}
                  </div>
                  {selected && (
                    <CheckCircleOutlined style={{
                      position: 'absolute', top: 6, right: 6, color: '#1677ff', fontSize: 16,
                      background: '#fff', borderRadius: '50%',
                    }} />
                  )}
                </div>
              )
            })}
          </div>
        )}
      </Modal>

      <Drawer
        title="文案详情"
        open={viewDrawer}
        onClose={() => setViewDrawer(false)}
        width={520}
        extra={viewing ? (
          <Button
            type="primary"
            icon={<VideoCameraOutlined />}
            loading={producingId === viewing.id}
            onClick={() => handleProduce(viewing)}
          >
            出片
          </Button>
        ) : null}
      >
        {viewing && (
          <div>
            <Space style={{ marginBottom: 8 }}>
              <Tag color={statusColors[viewing.status] || 'default'}>
                {statusLabels[viewing.status] || viewing.status}
              </Tag>
              {viewing.model_name && (
                <Tag color="purple">{viewing.model_name} · {viewing.tokens_used} tokens</Tag>
              )}
            </Space>
            <h3>{viewing.title}</h3>
            <div style={{ marginTop: 16 }}>
              <p><strong>钩子：</strong>{viewing.hook || '-'}</p>
              <p><strong>正文：</strong></p>
              <div style={{ background: '#f5f5f5', padding: 12, borderRadius: 8, whiteSpace: 'pre-wrap' }}>
                {viewing.content || '-'}
              </div>
              <p style={{ marginTop: 12 }}><strong>结尾：</strong>{viewing.ending || '-'}</p>
              <p><strong>封面文案：</strong>{viewing.cover_text || '-'}</p>
              <p><strong>标签：</strong>{viewing.tags || '-'}</p>
            </div>
          </div>
        )}
      </Drawer>
    </div>
  )
}
