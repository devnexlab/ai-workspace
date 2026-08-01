import { useState, useEffect } from 'react'
import {
  Table, Tag, Button, Input, Select, Space, Modal, message,
  Form, Popconfirm, Tooltip, Row, Col, Card, Statistic, Descriptions,
  Spin, Empty,
} from 'antd'
import {
  PlusOutlined, EditOutlined, DeleteOutlined, SearchOutlined,
  ReloadOutlined, RobotOutlined, BookOutlined, TagsOutlined,
  FileTextOutlined,
} from '@ant-design/icons'
import { knowledgeApi } from '../../api'
import dayjs from 'dayjs'

const sourceTypeOptions = [
  { value: 'note', label: '笔记' },
  { value: 'study', label: '学习' },
  { value: 'chat', label: '聊天' },
  { value: 'voice', label: '语音' },
  { value: 'image', label: '图片' },
  { value: 'web', label: '网页' },
  { value: 'pdf', label: 'PDF' },
  { value: 'excel', label: 'Excel' },
  { value: 'article', label: '公众号' },
  { value: 'video_summary', label: '视频总结' },
  { value: 'stock', label: '股票心得' },
  { value: 'insurance', label: '保险心得' },
  { value: 'inspiration', label: '生活灵感' },
]

const sourceTypeLabels = Object.fromEntries(sourceTypeOptions.map(o => [o.value, o.label]))
const sourceTypeColors = {
  note: 'blue',
  study: 'cyan',
  chat: 'green',
  voice: 'orange',
  image: 'purple',
  web: 'geekblue',
  pdf: 'red',
  excel: 'green',
  article: 'magenta',
  video_summary: 'volcano',
  stock: 'gold',
  insurance: 'lime',
  inspiration: 'pink',
}

export default function KnowledgeBase() {
  const [data, setData] = useState({ list: [], total: 0 })
  const [loading, setLoading] = useState(true)
  const [page, setPage] = useState(1)
  const [filters, setFilters] = useState({})
  const [editModal, setEditModal] = useState(false)
  const [aiModal, setAiModal] = useState(false)
  const [aiResult, setAiResult] = useState(null)
  const [aiLoading, setAiLoading] = useState(false)
  const [aiLoadingId, setAiLoadingId] = useState(null)
  const [form] = Form.useForm()
  const [editing, setEditing] = useState(null)
  const [categories, setCategories] = useState([])

  const loadData = (p = page, f = filters) => {
    setLoading(true)
    knowledgeApi.list({ page: p, pageSize: 15, ...f })
      .then(res => { setData(res); setPage(p) })
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    loadData(1)
    knowledgeApi.categories().then(res => setCategories(res.list || [])).catch(() => {})
  }, [])

  const handleSearch = () => loadData(1, filters)

  const handleSave = () => {
    form.validateFields().then(values => {
      if (editing) {
        knowledgeApi.update(editing.id, values).then(() => {
          message.success('已更新')
          setEditModal(false)
          loadData()
        })
      } else {
        knowledgeApi.create(values).then(() => {
          message.success('知识已添加')
          setEditModal(false)
          loadData(1)
        })
      }
    })
  }

  const handleAiProcess = (record) => {
    setAiLoadingId(record.id)
    setAiLoading(true)
    knowledgeApi.aiProcess(record.id).then(res => {
      setAiResult(res)
      setAiModal(true)
      loadData()
    }).catch(err => {
      message.error(err?.error || 'AI 整理失败，请检查 AI 配置')
    }).finally(() => {
      setAiLoadingId(null)
      setAiLoading(false)
    })
  }

  const columns = [
    { title: 'ID', dataIndex: 'id', width: 60 },
    {
      title: '标题', dataIndex: 'title', width: 200, ellipsis: true,
      render: (v, r) => (
        <Tooltip title={v}>
          <a style={{ fontWeight: 500 }}>{v}</a>
        </Tooltip>
      ),
    },
    {
      title: '来源', dataIndex: 'source_type', width: 100,
      render: v => <Tag color={sourceTypeColors[v]}>{sourceTypeLabels[v] || v}</Tag>
    },
    {
      title: '分类', dataIndex: 'category', width: 100,
      render: v => v ? <Tag color="blue">{v}</Tag> : '-'
    },
    {
      title: '标签', dataIndex: 'tags', width: 180, ellipsis: true,
      render: v => v ? (Array.isArray(v) ? v : v.split(',')).map((t, i) => (
        <Tag key={i} color="default">{typeof t === 'string' ? t.trim() : t}</Tag>
      )) : '-'
    },
    {
      title: '摘要', dataIndex: 'summary', width: 240, ellipsis: true,
      render: v => v || <span style={{ color: '#ccc' }}>暂无摘要，可点击 AI 整理生成</span>,
    },
    {
      title: '创建时间', dataIndex: 'created_at', width: 170,
      render: v => v ? dayjs(v).format('YYYY-MM-DD HH:mm') : '-',
    },
    {
      title: '操作', key: 'action', width: 220, fixed: 'right',
      render: (_, r) => (
        <Space size="small">
          <Tooltip title="AI 整理">
            <Button
              size="small"
              type="primary"
              ghost
              icon={<RobotOutlined />}
              loading={aiLoadingId === r.id}
              onClick={() => handleAiProcess(r)}
            />
          </Tooltip>
          <Tooltip title="编辑">
            <Button size="small" icon={<EditOutlined />} onClick={() => {
              setEditing(r)
              const formData = { ...r }
              if (typeof formData.tags === 'string') {
                formData.tags = formData.tags.split(',').map(t => t.trim()).join(',')
              } else if (Array.isArray(formData.tags)) {
                formData.tags = formData.tags.join(',')
              }
              form.setFieldsValue(formData)
              setEditModal(true)
            }} />
          </Tooltip>
          <Popconfirm title="确认删除？" onConfirm={() => {
            knowledgeApi.delete(r.id).then(() => { message.success('已删除'); loadData() })
          }}>
            <Button size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      )
    },
  ]

  const totalCount = data.total
  const noteCount = data.list.filter(d => d.source_type === 'note').length
  const studyCount = data.list.filter(d => d.source_type === 'study').length

  return (
    <div>
      <div className="page-title">AI知识库</div>

      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={6}>
          <Card size="small">
            <Statistic title="知识总数" value={totalCount} prefix={<BookOutlined />} />
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small">
            <Statistic title="笔记" value={noteCount} valueStyle={{ color: '#1890ff' }} />
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small">
            <Statistic title="学习" value={studyCount} valueStyle={{ color: '#13c2c2' }} />
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small">
            <Statistic title="分类数" value={categories.length} prefix={<TagsOutlined />} />
          </Card>
        </Col>
      </Row>

      <div className="table-toolbar">
        <div className="table-toolbar-left">
          <Select
            placeholder="来源类型"
            allowClear
            style={{ width: 130 }}
            value={filters.source_type}
            onChange={v => setFilters({ ...filters, source_type: v })}
            options={sourceTypeOptions}
          />
          <Select
            placeholder="分类筛选"
            allowClear
            style={{ width: 150 }}
            value={filters.category}
            onChange={v => setFilters({ ...filters, category: v })}
            options={categories.map(c => ({ value: c, label: c }))}
          />
          <Input
            placeholder="搜索标题/标签/内容"
            allowClear
            style={{ width: 220 }}
            value={filters.q}
            onChange={e => setFilters({ ...filters, q: e.target.value })}
            onPressEnter={handleSearch}
          />
          <Button type="primary" icon={<SearchOutlined />} onClick={handleSearch}>搜索</Button>
          <Button icon={<ReloadOutlined />} onClick={() => { setFilters({}); loadData(1, {}) }}>重置</Button>
        </div>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => {
          setEditing(null)
          form.resetFields()
          setEditModal(true)
        }}>添加知识</Button>
      </div>

      <Table
        columns={columns}
        dataSource={data.list}
        rowKey="id"
        loading={loading}
        scroll={{ x: 1300 }}
        pagination={{
          current: page,
          total: data.total,
          pageSize: 15,
          onChange: (p) => loadData(p),
          showTotal: (t) => `共 ${t} 条`,
        }}
        size="middle"
      />

      {/* 添加/编辑 Modal */}
      <Modal
        title={editing ? '编辑知识' : '添加知识'}
        open={editModal}
        onOk={handleSave}
        onCancel={() => setEditModal(false)}
        width={660}
      >
        <Form form={form} layout="vertical" style={{ marginTop: 16 }}>
          <Row gutter={16}>
            <Col span={16}>
              <Form.Item name="title" label="标题" rules={[{ required: true, message: '请输入标题' }]}>
                <Input placeholder="请输入知识标题" />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="source_type" label="来源类型" rules={[{ required: true, message: '请选择来源类型' }]}>
                <Select
                  placeholder="选择来源类型"
                  options={sourceTypeOptions}
                  optionRender={option => (
                    <Tag color={sourceTypeColors[option.value]}>{option.label}</Tag>
                  )}
                />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="category" label="分类">
                <Select
                  placeholder="选择或输入分类"
                  mode="tags"
                  maxCount={1}
                  options={categories.map(c => ({ value: c, label: c }))}
                />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="tags" label="标签（逗号分隔）">
                <Input placeholder="如：Python,AI,笔记" />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item name="content" label="内容">
            <Input.TextArea rows={6} placeholder="请输入知识内容" />
          </Form.Item>
          <Form.Item name="source_url" label="来源链接">
            <Input placeholder="如：原文链接、文件路径等" />
          </Form.Item>
        </Form>
      </Modal>

      {/* AI 整理结果 Modal */}
      <Modal
        title={<span><RobotOutlined /> AI 整理结果</span>}
        open={aiModal}
        onCancel={() => { setAiModal(false); setAiResult(null) }}
        footer={
          <Button onClick={() => { setAiModal(false); setAiResult(null) }}>关闭</Button>
        }
        width={700}
      >
        {aiResult ? (
          <div>
            <Descriptions column={2} size="small" bordered style={{ marginBottom: 16 }}>
              {aiResult.category && (
                <Descriptions.Item label="分类" span={1}>
                  <Tag color="blue">{aiResult.category}</Tag>
                </Descriptions.Item>
              )}
              {aiResult.tags && (
                <Descriptions.Item label="标签" span={1}>
                  {(Array.isArray(aiResult.tags) ? aiResult.tags : String(aiResult.tags).split(',')).map((t, i) => (
                    <Tag key={i} color="default">{typeof t === 'string' ? t.trim() : t}</Tag>
                  ))}
                </Descriptions.Item>
              )}
              {aiResult.summary && (
                <Descriptions.Item label="摘要" span={2}>
                  {aiResult.summary}
                </Descriptions.Item>
              )}
            </Descriptions>

            {aiResult.related_ids && (Array.isArray(aiResult.related_ids) ? aiResult.related_ids : []).length > 0 && (
              <Card
                size="small"
                title={<span><FileTextOutlined /> 关联知识</span>}
                style={{ marginBottom: 16 }}
              >
                <Space wrap>
                  {(Array.isArray(aiResult.related_ids) ? aiResult.related_ids : []).map((id, i) => (
                    <Tag key={i} color="processing">#{id}</Tag>
                  ))}
                </Space>
              </Card>
            )}

            {aiResult.ai_analysis && (
              <Card
                size="small"
                title={<span><RobotOutlined /> AI 分析</span>}
              >
                <div style={{ whiteSpace: 'pre-wrap', lineHeight: 1.8, color: '#333' }}>
                  {aiResult.ai_analysis}
                </div>
              </Card>
            )}

            {!aiResult.category && !aiResult.tags && !aiResult.summary && !aiResult.ai_analysis && (
              <Empty description="AI 未返回分析结果" />
            )}
          </div>
        ) : (
          <div style={{ textAlign: 'center', padding: 40 }}>
            <Spin size="large" />
            <div style={{ marginTop: 16, color: '#999' }}>加载中...</div>
          </div>
        )}
      </Modal>
    </div>
  )
}
