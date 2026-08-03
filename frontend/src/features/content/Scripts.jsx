import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import {
  Table, Tag, Button, Input, Select, Space, Modal, message,
  Popconfirm, Tooltip, Row, Col, Card, Statistic, Form, Drawer, Alert,
} from 'antd'
import {
  PlusOutlined, DeleteOutlined, SearchOutlined, ReloadOutlined,
  RobotOutlined, EditOutlined, EyeOutlined, FileTextOutlined, ThunderboltOutlined,
} from '@ant-design/icons'
import { scriptsApi, hotTopicsApi, settingsApi } from '../../api'

const { TextArea } = Input

const statusOptions = [
  { value: 'draft', label: '草稿' },
  { value: 'reviewing', label: '审核中' },
  { value: 'approved', label: '已通过' },
  { value: 'rejected', label: '已驳回' },
]
const statusColors = { draft: 'default', reviewing: 'processing', approved: 'success', rejected: 'error' }
const statusLabels = { draft: '草稿', reviewing: '审核中', approved: '已通过', rejected: '已驳回' }
const typeLabels = { traffic: '泛流量', insurance: '保险干货' }
const typeColors = { traffic: 'blue', insurance: 'orange' }
const ageLabels = {
  '20s': '20岁段', '30s': '30岁段', '40s': '40岁段',
  '50s': '50岁段', '60s': '60岁段', '70s': '70岁段', '80s': '80岁+', all: '全年龄',
}

export default function Scripts() {
  const [data, setData] = useState({ list: [], total: 0 })
  const [loading, setLoading] = useState(true)
  const [page, setPage] = useState(1)
  const [filters, setFilters] = useState({})
  const [editModal, setEditModal] = useState(false)
  const [viewDrawer, setViewDrawer] = useState(false)
  const [genModal, setGenModal] = useState(false)
  const [generating, setGenerating] = useState(false)
  const [planning, setPlanning] = useState(false)
  const [runningDaily, setRunningDaily] = useState(false)
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
    loadData(1)
    settingsApi.check().then(setReadiness).catch(() => {})
    settingsApi.get().then(res => {
      const list = res?.system || []
      const item = Array.isArray(list) ? list.find(s => s.key === 'fixed_ending') : null
      setBrandEnding(item?.value || '祁实说实话，替你的保单说话，给你最放心的选择。关注我，来找我。')
    }).catch(() => {
      setBrandEnding('祁实说实话，替你的保单说话，给你最放心的选择。关注我，来找我。')
    })
    scriptsApi.dailyRunStatus().then(setDailyStatus).catch(() => {})
  }, [])

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
      audience: values.audience || undefined,
      tone: values.tone || undefined,
      extra_req: values.extra_req || undefined,
      content_type: values.content_type || 'traffic',
      age_band: values.age_band || 'all',
    }).then(res => {
      message.success(res.message || '文案生成成功')
      setGenModal(false)
      genForm.resetFields()
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
    { title: '来源热点', dataIndex: 'topic_title', width: 120, ellipsis: true,
      render: v => v || '-' },
    { title: '封面文案', dataIndex: 'cover_text', width: 100, ellipsis: true,
      render: v => v || '-' },
    {
      title: '状态', dataIndex: 'status', width: 80,
      render: v => <Tag color={statusColors[v]}>{statusLabels[v]}</Tag>
    },
    { title: '创建时间', dataIndex: 'created_at', width: 150 },
    {
      title: '操作', key: 'action', width: 140, fixed: 'right',
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
          <Popconfirm title="确认删除？" onConfirm={() => {
            scriptsApi.delete(r.id).then(() => { message.success('已删除'); loadData() })
          }}>
            <Button size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      )
    },
  ]

  return (
    <div>
      <div className="page-title">文案中心</div>
      <div style={{ color: '#888', marginBottom: 12, fontSize: 13 }}>
        每日建议：2 条泛流量涨粉 + 1 条保险干货 · 40-60 秒口播 · 统一收口「祁实说实话…关注我，来找我」
      </div>

      {!readiness.ai?.ready && (
        <Alert type="warning" showIcon style={{ marginBottom: 16 }}
          message="AI 未配置"
          description={
            <span>
              请到 <Link to="/settings/ai">系统设置 · AI 大模型</Link> 填写 API Key 后才能使用 AI 生成文案
            </span>
          }
        />
      )}

      {brandEnding && (
        <Alert type="info" showIcon style={{ marginBottom: 16 }}
          message="品牌固定收口（所有文案自动带上）"
          description={brandEnding} />
      )}

      {dailyStatus && (
        <Alert
          style={{ marginBottom: 16 }}
          type={String(dailyStatus.daily_auto_enabled).toLowerCase() === 'true' ? 'success' : 'warning'}
          showIcon
          message={`今日进度：泛流量 ${dailyStatus.scripts?.traffic || 0}/${dailyStatus.traffic_target || 2}，保险 ${dailyStatus.scripts?.insurance || 0}/${dailyStatus.insurance_target || 1}`}
          description={
            <span>
              出片状态：完成 {dailyStatus.videos?.done || 0} / 进行中 {dailyStatus.videos?.processing || 0} / 待处理 {dailyStatus.videos?.pending || 0}
              {' · '}
              定时日更：{String(dailyStatus.daily_auto_enabled).toLowerCase() === 'true'
                ? `已开启（每天 ${dailyStatus.daily_run_hour || 8} 点）`
                : '未开启（可在 系统设置 → 内容运营 打开）'}
              {dailyStatus.daily_last_run ? ` · 上次：${dailyStatus.daily_last_run}` : ''}
              {' · '}
              <Link to="/videos">去视频页查看出片</Link>
            </span>
          }
        />
      )}

      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={6}><Card size="small"><Statistic title="文案总数" value={data.total} prefix={<FileTextOutlined />} /></Card></Col>
        <Col span={6}><Card size="small"><Statistic title="泛流量" value={data.list.filter(d => (d.content_type || 'traffic') === 'traffic').length} valueStyle={{ color: '#1677ff' }} /></Card></Col>
        <Col span={6}><Card size="small"><Statistic title="保险干货" value={data.list.filter(d => d.content_type === 'insurance').length} valueStyle={{ color: '#fa8c16' }} /></Card></Col>
        <Col span={6}><Card size="small"><Statistic title="已通过" value={data.list.filter(d => d.status === 'approved').length} valueStyle={{ color: '#52c41a' }} /></Card></Col>
      </Row>

      <div className="table-toolbar">
        <div className="table-toolbar-left">
          <Select placeholder="类型" allowClear style={{ width: 120 }}
            value={filters.content_type}
            onChange={v => setFilters({ ...filters, content_type: v })}
            options={[
              { value: 'traffic', label: '泛流量' },
              { value: 'insurance', label: '保险干货' },
            ]} />
          <Select placeholder="状态" allowClear style={{ width: 120 }}
            value={filters.status}
            onChange={v => setFilters({ ...filters, status: v })}
            options={statusOptions} />
          <Input placeholder="搜索标题/内容" allowClear style={{ width: 200 }}
            value={filters.q}
            onChange={e => setFilters({ ...filters, q: e.target.value })}
            onPressEnter={() => loadData(1, filters)} />
          <Button type="primary" icon={<SearchOutlined />} onClick={() => loadData(1, filters)}>搜索</Button>
          <Button icon={<ReloadOutlined />} onClick={() => { setFilters({}); loadData(1, {}) }}>重置</Button>
        </div>
        <Space wrap>
          <Button type="primary" icon={<ThunderboltOutlined />} loading={runningDaily} onClick={handleDailyRun}>
            今日计划并出片
          </Button>
          <Button icon={<ThunderboltOutlined />} loading={planning} onClick={handleDailyPlan}>
            仅生成文案（2+1）
          </Button>
          <Button icon={<RobotOutlined />} loading={generating} onClick={() => setGenModal(true)}>
            AI 生成文案
          </Button>
          <Button icon={<PlusOutlined />} onClick={() => {
            setEditing(null); form.resetFields(); setEditModal(true)
          }}>手动添加</Button>
        </Space>
      </div>

      <Table columns={columns} dataSource={data.list} rowKey="id" loading={loading}
        scroll={{ x: 1200 }}
        pagination={{
          current: page, total: data.total, pageSize: 15,
          onChange: (p) => loadData(p),
          showTotal: (t) => `共 ${t} 条`,
        }}
        size="middle" />

      {/* Generate Modal */}
      <Modal title="AI 生成文案" open={genModal} onOk={handleGenerate}
        onCancel={() => setGenModal(false)} width={600} confirmLoading={generating}>
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
                ]} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="duration" label="视频时长" initialValue="40-60秒">
                <Select options={[
                  { label: '40-60秒 (推荐口播)', value: '40-60秒' },
                  { label: '15-30秒 (短快爆)', value: '15-30秒' },
                  { label: '30-60秒 (标准)', value: '30-60秒' },
                  { label: '1-3分钟 (深度)', value: '1-3分钟' },
                ]} />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="content_type" label="内容类型" initialValue="traffic">
                <Select options={[
                  { label: '泛流量涨粉', value: 'traffic' },
                  { label: '保险干货', value: 'insurance' },
                ]} />
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
                ]} />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="tone" label="文案语气" initialValue="casual"
                extra="不填则使用系统设置中的默认语气">
                <Select allowClear placeholder="自动" options={[
                  { label: '专业权威', value: 'professional' },
                  { label: '轻松口语化', value: 'casual' },
                  { label: '激情澎湃', value: 'passionate' },
                  { label: '幽默风趣', value: 'humorous' },
                  { label: '严肃认真', value: 'serious' },
                  { label: '亲切友好', value: 'friendly' },
                ]} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="audience" label="目标受众"
                extra="默认已覆盖 20-80 岁泛流量">
                <Input placeholder="留空使用默认" />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item name="prompt" label="创作主题/提示词"
            extra="填写后将从主题生成；不填则从爆款热点生成">
            <TextArea rows={3} placeholder="如：写一个关于AI工具提升效率的短视频文案" />
          </Form.Item>
          <Form.Item name="extra_req" label="额外要求"
            extra="如：必须提到XX工具、加入数据引用等">
            <TextArea rows={2} placeholder="可选" />
          </Form.Item>
        </Form>
        {!readiness.ai?.ready && (
          <Alert type="error" message="AI API Key 未配置，无法生成。请先在系统设置中配置。" />
        )}
      </Modal>

      {/* Edit Modal */}
      <Modal title={editing ? '编辑文案' : '添加文案'} open={editModal} onOk={handleSave}
        onCancel={() => setEditModal(false)} width={640}>
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
          <Form.Item name="status" label="状态">
            <Select options={statusOptions} />
          </Form.Item>
        </Form>
      </Modal>

      {/* View Drawer */}
      <Drawer title="文案详情" open={viewDrawer} onClose={() => setViewDrawer(false)} width={520}>
        {viewing && (
          <div>
            <h3>{viewing.title}</h3>
            {viewing.model_name && <Tag color="purple">{viewing.model_name} · {viewing.tokens_used} tokens</Tag>}
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
