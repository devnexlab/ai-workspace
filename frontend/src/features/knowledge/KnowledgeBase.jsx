import { useState, useEffect } from 'react'
import {
  Tag, Button, Input, Select, Space, Modal, message,
  Form, Popconfirm, Tooltip, Row, Col, Card, Descriptions,
  Spin, Empty, Alert, Upload, Checkbox, Pagination,
} from 'antd'
import {
  PlusOutlined, EditOutlined, DeleteOutlined, SearchOutlined,
  ReloadOutlined, RobotOutlined, BookOutlined,
  FileTextOutlined, UploadOutlined, MessageOutlined,
  SoundOutlined, PictureOutlined, GlobalOutlined,
  FilePdfOutlined, FileExcelOutlined, StockOutlined,
  BulbOutlined, ReadOutlined, VideoCameraOutlined,
} from '@ant-design/icons'
import { knowledgeApi } from '../../api'
import { formatDate, formatDateTime } from '../../utils/date'
import './KnowledgeBase.css'

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

const sourceTypeIconStyle = {
  note: { bg: 'rgba(59,130,246,0.1)', color: '#3b82f6', icon: <FileTextOutlined /> },
  study: { bg: 'rgba(0,184,132,0.1)', color: '#00b884', icon: <ReadOutlined /> },
  chat: { bg: 'rgba(0,184,132,0.1)', color: '#00b884', icon: <MessageOutlined /> },
  voice: { bg: 'rgba(255,149,0,0.1)', color: '#ff9500', icon: <SoundOutlined /> },
  image: { bg: 'rgba(139,92,246,0.1)', color: '#8b5cf6', icon: <PictureOutlined /> },
  web: { bg: 'rgba(91,91,214,0.1)', color: '#5b5bd6', icon: <GlobalOutlined /> },
  pdf: { bg: 'rgba(255,59,92,0.1)', color: '#ff3b5c', icon: <FilePdfOutlined /> },
  excel: { bg: 'rgba(0,184,132,0.1)', color: '#00b884', icon: <FileExcelOutlined /> },
  article: { bg: 'rgba(236,72,153,0.1)', color: '#ec4899', icon: <BookOutlined /> },
  video_summary: { bg: 'rgba(249,115,22,0.1)', color: '#f97316', icon: <VideoCameraOutlined /> },
  stock: { bg: 'rgba(234,179,8,0.12)', color: '#ca8a04', icon: <StockOutlined /> },
  insurance: { bg: 'rgba(34,197,94,0.1)', color: '#16a34a', icon: <BulbOutlined /> },
  inspiration: { bg: 'rgba(244,114,182,0.12)', color: '#db2777', icon: <BulbOutlined /> },
}

function cardSnippet(item) {
  const raw = (item.summary || item.content || '').replace(/\s+/g, ' ').trim()
  return raw || '暂无摘要，可点击 AI 整理生成'
}

function parseRelatedIds(raw) {
  if (Array.isArray(raw)) return raw
  if (raw == null || raw === '') return []
  if (typeof raw === 'string') {
    try {
      const parsed = JSON.parse(raw)
      return Array.isArray(parsed) ? parsed : []
    } catch {
      return String(raw).split(',').map(s => Number(s.trim())).filter(Boolean)
    }
  }
  return []
}

function hasAiResult(item) {
  if (!item) return false
  return Boolean(
    (item.summary && String(item.summary).trim())
    || (item.ai_analysis && String(item.ai_analysis).trim())
  )
}

function buildAiResultFromItem(item) {
  if (!item) return null
  return {
    category: item.category || '',
    tags: item.tags || '',
    summary: item.summary || '',
    related_ids: parseRelatedIds(item.related_ids),
    ai_analysis: item.ai_analysis || '',
  }
}

export default function KnowledgeBase() {
  const [data, setData] = useState({ list: [], total: 0 })
  const [loading, setLoading] = useState(true)
  const [page, setPage] = useState(1)
  const [filters, setFilters] = useState({})
  const [editModal, setEditModal] = useState(false)
  const [aiModal, setAiModal] = useState(false)
  const [aiResult, setAiResult] = useState(null)
  const [aiResultId, setAiResultId] = useState(null)
  const [aiLoading, setAiLoading] = useState(false)
  const [aiLoadingId, setAiLoadingId] = useState(null)
  const [selectedRowKeys, setSelectedRowKeys] = useState([])
  const [compareModal, setCompareModal] = useState(false)
  const [compareResult, setCompareResult] = useState(null)
  const [compareLoading, setCompareLoading] = useState(false)
  const [form] = Form.useForm()
  const [editing, setEditing] = useState(null)
  const [categories, setCategories] = useState([])
  const [viewing, setViewing] = useState(null)
  const [uploading, setUploading] = useState(false)

  const loadData = (p = page, f = filters) => {
    setLoading(true)
    knowledgeApi.list({ page: p, pageSize: 12, ...f })
      .then(res => { setData(res); setPage(p) })
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    loadData(1)
    knowledgeApi.categories().then(res => setCategories(res.list || [])).catch(() => {})
  }, [])

  const handleSearch = () => loadData(1, filters)

  const toggleSelect = (id, checked) => {
    setSelectedRowKeys(prev => (
      checked ? [...new Set([...prev, id])] : prev.filter(x => x !== id)
    ))
  }

  const handleSave = () => {
    form.validateFields().then(values => {
      const payload = {
        ...values,
        category: Array.isArray(values.category)
          ? (values.category[0] || '')
          : (values.category || ''),
      }
      if (editing) {
        knowledgeApi.update(editing.id, payload).then(() => {
          message.success('已更新')
          setEditModal(false)
          loadData()
          knowledgeApi.categories().then(res => setCategories(res.list || [])).catch(() => {})
        })
      } else {
        knowledgeApi.create(payload).then(() => {
          message.success('知识已添加')
          setEditModal(false)
          loadData(1)
          knowledgeApi.categories().then(res => setCategories(res.list || [])).catch(() => {})
        })
      }
    })
  }

  const openAiResult = (record) => {
    const show = (item) => {
      setAiResultId(item.id)
      setAiResult(buildAiResultFromItem(item))
      setAiModal(true)
    }
    // 列表项已有字段则直接看；否则拉详情
    if (hasAiResult(record) && (record.ai_analysis || record.summary)) {
      show(record)
      return
    }
    knowledgeApi.get(record.id)
      .then((item) => {
        if (!hasAiResult(item)) {
          message.info('尚未整理，正在生成…')
          handleAiProcess(item, true)
          return
        }
        show(item)
      })
      .catch(() => message.error('加载失败'))
  }

  const handleAiProcess = (record, force = false) => {
    if (!force && hasAiResult(record)) {
      openAiResult(record)
      return
    }
    setAiLoadingId(record.id)
    setAiLoading(true)
    setAiResultId(record.id)
    knowledgeApi.aiProcess(record.id).then(res => {
      const result = res?.result || res
      setAiResult({
        ...result,
        related_ids: parseRelatedIds(result?.related_ids),
      })
      setAiModal(true)
      loadData()
      // 同步详情弹窗里的数据
      if (viewing?.id === record.id) {
        knowledgeApi.get(record.id).then(setViewing).catch(() => {})
      }
    }).catch(err => {
      message.error(err?.error || 'AI 整理失败，请检查 AI 配置')
    }).finally(() => {
      setAiLoadingId(null)
      setAiLoading(false)
    })
  }

  const handleCompare = () => {
    if (selectedRowKeys.length < 1) {
      message.warning('请先勾选至少 1 条笔记')
      return
    }
    setCompareLoading(true)
    setCompareModal(true)
    setCompareResult(null)
    knowledgeApi.compare({ ids: selectedRowKeys })
      .then(res => setCompareResult(res?.result || res))
      .catch(err => message.error(err?.error || '对比失败'))
      .finally(() => setCompareLoading(false))
  }

  const openRelated = (id) => {
    knowledgeApi.get(id).then(res => setViewing(res)).catch(() => message.error('加载失败'))
  }

  const openEdit = (r) => {
    setEditing(r)
    const formData = { ...r }
    if (typeof formData.tags === 'string') {
      formData.tags = formData.tags.split(',').map(t => t.trim()).join(',')
    } else if (Array.isArray(formData.tags)) {
      formData.tags = formData.tags.join(',')
    }
    form.setFieldsValue(formData)
    setEditModal(true)
  }

  return (
    <div className="kb-page">
      <div className="page-title">知识库</div>
      <div className="page-desc">
        笔记、学习资料、聊天记录、行业资讯的沉淀与搜索。
      </div>

      <div className="table-toolbar kb-toolbar">
        <div className="table-toolbar-left">
          <Select
            placeholder="类型"
            allowClear
            style={{ width: 120 }}
            value={filters.source_type}
            onChange={v => setFilters({ ...filters, source_type: v })}
            options={sourceTypeOptions}
          />
          <Select
            placeholder="分类"
            allowClear
            style={{ width: 140 }}
            value={filters.category}
            onChange={v => setFilters({ ...filters, category: v })}
            options={categories.map(c => ({ value: c, label: c }))}
          />
          <Input
            placeholder="搜索标题/内容"
            allowClear
            style={{ width: 220 }}
            value={filters.q}
            onChange={e => setFilters({ ...filters, q: e.target.value })}
            onPressEnter={handleSearch}
          />
          <Button type="primary" icon={<SearchOutlined />} onClick={handleSearch}>搜索</Button>
          <Button icon={<ReloadOutlined />} onClick={() => { setFilters({}); loadData(1, {}) }}>重置</Button>
        </div>
        <div className="table-toolbar-right">
          <Space>
            <Button
              type="link"
              icon={<RobotOutlined />}
              loading={compareLoading}
              onClick={handleCompare}
              disabled={!selectedRowKeys.length}
            >
              AI 总结 / 对比 ({selectedRowKeys.length})
            </Button>
            <Upload
              showUploadList={false}
              accept=".pdf,audio/*,.mp3,.wav,.m4a,.aac,.ogg,.flac,.webm"
              beforeUpload={(file) => {
                const fd = new FormData()
                fd.append('file', file)
                setUploading(true)
                knowledgeApi.upload(fd)
                  .then((res) => {
                    message.success(res.message || '导入成功')
                    loadData(1)
                    if (res.id) {
                      knowledgeApi.get(res.id).then((item) => {
                        setEditing(item)
                        form.setFieldsValue(item)
                        setEditModal(true)
                      }).catch(() => {})
                    }
                  })
                  .catch((err) => message.error(err?.error || err?.message || '导入失败'))
                  .finally(() => setUploading(false))
                return false
              }}
            >
              <Button icon={<UploadOutlined />} loading={uploading}>导入文件</Button>
            </Upload>
            <Button type="primary" icon={<PlusOutlined />} onClick={() => {
              setEditing(null)
              form.resetFields()
              setEditModal(true)
            }}>添加笔记</Button>
          </Space>
        </div>
      </div>

      <Spin spinning={loading}>
        <div className="kb-grid">
          {!data.list.length && !loading ? (
            <div className="kb-empty"><Empty description="暂无知识，点右上角添加" /></div>
          ) : data.list.map(item => {
            const st = sourceTypeIconStyle[item.source_type] || sourceTypeIconStyle.note
            const selected = selectedRowKeys.includes(item.id)
            return (
              <div
                key={item.id}
                className={`kb-card${selected ? ' is-selected' : ''}`}
                onClick={() => setViewing(item)}
              >
                <div className="kb-card-check" onClick={e => e.stopPropagation()}>
                  <Checkbox
                    checked={selected}
                    onChange={e => toggleSelect(item.id, e.target.checked)}
                  />
                </div>
                <div className="kb-card-header">
                  <div className="kb-card-icon" style={{ background: st.bg, color: st.color }}>
                    {st.icon}
                  </div>
                  <div className="kb-card-title" title={item.title}>{item.title}</div>
                </div>
                <div className="kb-card-desc">{cardSnippet(item)}</div>
                <div className="kb-card-footer">
                  <div className="kb-card-meta">
                    <Tag color={sourceTypeColors[item.source_type]}>
                      {sourceTypeLabels[item.source_type] || item.source_type}
                    </Tag>
                    {item.category ? <span className="kb-card-cat" title={item.category}>{item.category}</span> : null}
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    <div className="kb-card-actions" onClick={e => e.stopPropagation()}>
                      <Tooltip title={hasAiResult(item) ? '查看 AI 整理' : 'AI 整理'}>
                        <Button
                          size="small"
                          type="text"
                          icon={<RobotOutlined />}
                          loading={aiLoadingId === item.id}
                          onClick={() => hasAiResult(item) ? openAiResult(item) : handleAiProcess(item, true)}
                        />
                      </Tooltip>
                      <Tooltip title="编辑">
                        <Button size="small" type="text" icon={<EditOutlined />} onClick={() => openEdit(item)} />
                      </Tooltip>
                      <Popconfirm title="确认删除？" onConfirm={() => {
                        knowledgeApi.delete(item.id).then(() => {
                          message.success('已删除')
                          loadData()
                        })
                      }}>
                        <Button size="small" type="text" danger icon={<DeleteOutlined />} />
                      </Popconfirm>
                    </div>
                    <span className="kb-card-date">{formatDate(item.created_at).slice(5) || '-'}</span>
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      </Spin>

      {data.total > 0 && (
        <div className="kb-pagination">
          <Pagination
            current={page}
            total={data.total}
            pageSize={12}
            onChange={(p) => loadData(p)}
            showTotal={(t) => `共 ${t} 条`}
            size="small"
          />
        </div>
      )}

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
              <Form.Item name="category" label="分类"
                getValueFromEvent={(v) => (Array.isArray(v) ? (v[0] || undefined) : v)}
                normalize={(v) => (v ? [v] : [])}
              >
                <Select
                  placeholder="选择或输入分类"
                  mode="tags"
                  maxCount={1}
                  allowClear
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

      <Modal
        title={<span><RobotOutlined /> AI 整理结果</span>}
        open={aiModal}
        onCancel={() => { setAiModal(false); setAiResult(null); setAiResultId(null) }}
        footer={
          <Space>
            {aiResultId ? (
              <Popconfirm
                title="重新整理会覆盖当前结果，确定吗？"
                okText="重新整理"
                cancelText="取消"
                onConfirm={() => handleAiProcess({ id: aiResultId }, true)}
              >
                <Button icon={<RobotOutlined />} loading={aiLoading && aiLoadingId === aiResultId}>
                  重新整理
                </Button>
              </Popconfirm>
            ) : null}
            <Button type="primary" onClick={() => { setAiModal(false); setAiResult(null); setAiResultId(null) }}>
              关闭
            </Button>
          </Space>
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
                    <Tag key={i} color="processing" style={{ cursor: 'pointer' }} onClick={() => openRelated(id)}>
                      #{id} 查看
                    </Tag>
                  ))}
                </Space>
              </Card>
            )}

            {aiResult.ai_analysis && (
              <Card size="small" title={<span><RobotOutlined /> AI 分析</span>}>
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

      <Modal
        title="AI 对比启发"
        open={compareModal}
        onCancel={() => setCompareModal(false)}
        footer={<Button onClick={() => setCompareModal(false)}>关闭</Button>}
        width={720}
      >
        <Spin spinning={compareLoading}>
          {compareResult ? (
            <div>
              {compareResult.one_liner && (
                <Alert type="success" showIcon style={{ marginBottom: 12 }} message={compareResult.one_liner} />
              )}
              <Descriptions column={1} bordered size="small">
                {compareResult.common_themes && (
                  <Descriptions.Item label="共同主题">{compareResult.common_themes}</Descriptions.Item>
                )}
                {compareResult.conflicts && (
                  <Descriptions.Item label="矛盾/待验证">{compareResult.conflicts}</Descriptions.Item>
                )}
                {compareResult.connections && (
                  <Descriptions.Item label="可打通连接">{compareResult.connections}</Descriptions.Item>
                )}
              </Descriptions>
              {!!(compareResult.inspirations || []).length && (
                <Card size="small" title="灵感" style={{ marginTop: 12 }}>
                  <ul style={{ margin: 0, paddingLeft: 18 }}>
                    {(compareResult.inspirations || []).map((x, i) => <li key={i}>{x}</li>)}
                  </ul>
                </Card>
              )}
              {!!(compareResult.next_actions || []).length && (
                <Card size="small" title="下一步" style={{ marginTop: 12 }}>
                  <ul style={{ margin: 0, paddingLeft: 18 }}>
                    {(compareResult.next_actions || []).map((x, i) => <li key={i}>{x}</li>)}
                  </ul>
                </Card>
              )}
            </div>
          ) : !compareLoading ? <Empty description="暂无结果" /> : null}
        </Spin>
      </Modal>

      <Modal
        title={viewing?.title || '知识详情'}
        open={!!viewing}
        onCancel={() => setViewing(null)}
        footer={
          <Space>
            {viewing && hasAiResult(viewing) && (
              <Button icon={<RobotOutlined />} onClick={() => openAiResult(viewing)}>
                查看整理结果
              </Button>
            )}
            {viewing && (
              hasAiResult(viewing) ? (
                <Popconfirm
                  title="重新整理会覆盖当前结果，确定吗？"
                  okText="重新整理"
                  onConfirm={() => handleAiProcess(viewing, true)}
                >
                  <Button loading={aiLoading && aiLoadingId === viewing.id}>重新整理</Button>
                </Popconfirm>
              ) : (
                <Button
                  icon={<RobotOutlined />}
                  loading={aiLoading && aiLoadingId === viewing.id}
                  onClick={() => handleAiProcess(viewing, true)}
                >
                  AI 整理
                </Button>
              )
            )}
            {viewing && (
              <Button icon={<EditOutlined />} onClick={() => { openEdit(viewing); setViewing(null) }}>编辑</Button>
            )}
            <Button onClick={() => setViewing(null)}>关闭</Button>
          </Space>
        }
        width={640}
      >
        {viewing && (
          <div>
            <Space wrap style={{ marginBottom: 8 }}>
              <Tag color={sourceTypeColors[viewing.source_type]}>
                {sourceTypeLabels[viewing.source_type] || viewing.source_type}
              </Tag>
              {viewing.category && <Tag color="blue">{viewing.category}</Tag>}
              {(String(viewing.tags || '').split(',').filter(Boolean)).map((t, i) => (
                <Tag key={i}>{t.trim()}</Tag>
              ))}
            </Space>
            <div style={{ fontSize: 12, color: '#94a3b8', marginBottom: 10 }}>
              {formatDateTime(viewing.created_at)}
            </div>
            <div style={{ whiteSpace: 'pre-wrap', lineHeight: 1.7 }}>{viewing.content}</div>
            {viewing.summary && (
              <Card size="small" title="摘要" style={{ marginTop: 12 }}>
                {viewing.summary}
              </Card>
            )}
            {viewing.ai_analysis && (
              <Card size="small" title={<span><RobotOutlined /> AI 分析</span>} style={{ marginTop: 12 }}>
                <div style={{ whiteSpace: 'pre-wrap', lineHeight: 1.7 }}>{viewing.ai_analysis}</div>
              </Card>
            )}
          </div>
        )}
      </Modal>
    </div>
  )
}
