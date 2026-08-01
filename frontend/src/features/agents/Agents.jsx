import { useState, useEffect } from 'react'
import {
  Tag, Button, Space, Modal, message,
  Form, Popconfirm, Tooltip, Row, Col, Card, Statistic,
  Input, Select, Spin, Empty, Typography,
} from 'antd'
import {
  PlusOutlined, EditOutlined, DeleteOutlined, ReloadOutlined,
  RobotOutlined, PlayCircleOutlined, CheckCircleOutlined,
  ClockCircleOutlined, ExclamationCircleOutlined,
} from '@ant-design/icons'
import { agentsApi } from '../../api'
import dayjs from 'dayjs'

const { TextArea } = Input
const { Paragraph, Text } = Typography

const agentTypeOptions = [
  { value: 'content', label: '内容生成Agent' },
  { value: 'hotspot', label: '热点分析Agent' },
  { value: 'customer', label: '客户分析Agent' },
  { value: 'stock', label: '股票分析Agent' },
  { value: 'knowledge', label: '知识整理Agent' },
  { value: 'reminder', label: '提醒Agent' },
  { value: 'daily_report', label: '日报Agent' },
  { value: 'data_collector', label: '数据采集Agent' },
]

const agentTypeLabels = Object.fromEntries(agentTypeOptions.map(o => [o.value, o.label]))
const agentTypeColors = {
  content: 'blue',
  hotspot: 'volcano',
  customer: 'green',
  stock: 'gold',
  knowledge: 'purple',
  reminder: 'cyan',
  daily_report: 'magenta',
  data_collector: 'geekblue',
}
const agentTypeIcons = {
  content: <RobotOutlined />,
  hotspot: <RobotOutlined />,
  customer: <RobotOutlined />,
  stock: <RobotOutlined />,
  knowledge: <RobotOutlined />,
  reminder: <RobotOutlined />,
  daily_report: <RobotOutlined />,
  data_collector: <RobotOutlined />,
}

const statusColors = { idle: 'blue', running: 'green', error: 'red', active: 'processing' }
const statusLabels = { idle: '空闲', running: '运行中', error: '错误', active: '活跃' }
const statusIcons = {
  idle: <ClockCircleOutlined />,
  running: <PlayCircleOutlined />,
  error: <ExclamationCircleOutlined />,
  active: <CheckCircleOutlined />,
}

export default function Agents() {
  const [list, setList] = useState([])
  const [loading, setLoading] = useState(true)
  const [editModal, setEditModal] = useState(false)
  const [runModal, setRunModal] = useState(false)
  const [runResult, setRunResult] = useState(null)
  const [runningId, setRunningId] = useState(null)
  const [form] = Form.useForm()
  const [editing, setEditing] = useState(null)

  const loadData = () => {
    setLoading(true)
    agentsApi.list()
      .then(res => setList(res?.list || res || []))
      .catch(() => message.error('加载 Agent 列表失败'))
      .finally(() => setLoading(false))
  }

  useEffect(() => { loadData() }, [])

  const handleSave = () => {
    form.validateFields().then(values => {
      const data = { ...values }
      if (data.config_json && typeof data.config_json === 'string') {
        try {
          data.config_json = JSON.parse(data.config_json)
        } catch {
          // 保留原始字符串，后端处理
        }
      }
      if (editing) {
        agentsApi.update(editing.id, data).then(() => {
          message.success('Agent 已更新')
          setEditModal(false)
          loadData()
        }).catch(() => message.error('更新失败'))
      } else {
        agentsApi.create(data).then(() => {
          message.success('Agent 已创建')
          setEditModal(false)
          loadData()
        }).catch(() => message.error('创建失败'))
      }
    })
  }

  const handleRun = (record) => {
    setRunningId(record.id)
    agentsApi.run(record.id).then(res => {
      setRunResult({ agent: record, result: res })
      setRunModal(true)
      loadData()
    }).catch(err => {
      message.error(err?.error || '执行失败，请检查 AI 配置')
    }).finally(() => {
      setRunningId(null)
    })
  }

  const handleEdit = (record) => {
    setEditing(record)
    const formData = { ...record }
    if (formData.config_json && typeof formData.config_json !== 'string') {
      formData.config_json = JSON.stringify(formData.config_json, null, 2)
    }
    form.setFieldsValue(formData)
    setEditModal(true)
  }

  const handleAdd = () => {
    setEditing(null)
    form.resetFields()
    setEditModal(true)
  }

  const totalCount = list.length
  const runningCount = list.filter(a => a.status === 'running' || a.status === 'active').length
  const errorCount = list.filter(a => a.status === 'error').length

  return (
    <div>
      <div className="page-title">AI Agent 中心</div>

      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={6}>
          <Card size="small">
            <Statistic title="Agent 总数" value={totalCount} prefix={<RobotOutlined />} />
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small">
            <Statistic title="运行中/活跃" value={runningCount} valueStyle={{ color: '#52c41a' }} prefix={<PlayCircleOutlined />} />
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small">
            <Statistic title="空闲" value={list.filter(a => a.status === 'idle').length} valueStyle={{ color: '#1890ff' }} prefix={<ClockCircleOutlined />} />
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small">
            <Statistic title="错误" value={errorCount} valueStyle={{ color: '#ff4d4f' }} prefix={<ExclamationCircleOutlined />} />
          </Card>
        </Col>
      </Row>

      <div className="table-toolbar">
        <div className="table-toolbar-left">
          <Button icon={<ReloadOutlined />} onClick={loadData}>刷新</Button>
        </div>
        <Button type="primary" icon={<PlusOutlined />} onClick={handleAdd}>创建 Agent</Button>
      </div>

      <Spin spinning={loading}>
        {list.length > 0 ? (
          <Row gutter={[16, 16]}>
            {list.map(agent => (
              <Col key={agent.id} xs={24} sm={12} md={8} lg={6}>
                <Card
                  hoverable
                  size="small"
                  title={
                    <Space>
                      {agentTypeIcons[agent.agent_type]}
                      <span>{agent.name}</span>
                    </Space>
                  }
                  extra={
                    <Tag color={statusColors[agent.status]} icon={statusIcons[agent.status]}>
                      {statusLabels[agent.status] || agent.status}
                    </Tag>
                  }
                  actions={[
                    <Tooltip title="执行" key="run">
                      <Button
                        type="primary"
                        size="small"
                        ghost
                        icon={<PlayCircleOutlined />}
                        loading={runningId === agent.id}
                        onClick={() => handleRun(agent)}
                      >执行</Button>
                    </Tooltip>,
                    <Tooltip title="编辑" key="edit">
                      <Button
                        size="small"
                        icon={<EditOutlined />}
                        onClick={() => handleEdit(agent)}
                      >编辑</Button>
                    </Tooltip>,
                    <Popconfirm
                      key="delete"
                      title="确认删除该 Agent？"
                      onConfirm={() => {
                        agentsApi.delete(agent.id).then(() => {
                          message.success('已删除')
                          loadData()
                        }).catch(() => message.error('删除失败'))
                      }}
                    >
                      <Button size="small" danger icon={<DeleteOutlined />}>删除</Button>
                    </Popconfirm>,
                  ]}
                >
                  <div style={{ marginBottom: 8 }}>
                    <Tag color={agentTypeColors[agent.agent_type]}>
                      {agentTypeLabels[agent.agent_type] || agent.agent_type}
                    </Tag>
                  </div>
                  <Paragraph
                    type="secondary"
                    ellipsis={{ rows: 2 }}
                    style={{ minHeight: 44, marginBottom: 8, fontSize: 13 }}
                  >
                    {agent.description || '暂无描述'}
                  </Paragraph>
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    <ClockCircleOutlined /> 上次执行：{agent.last_run
                      ? dayjs(agent.last_run).format('YYYY-MM-DD HH:mm')
                      : '未执行'}
                  </Text>
                </Card>
              </Col>
            ))}
          </Row>
        ) : (
          !loading && (
            <Card>
              <Empty description="暂无 Agent，点击「创建 Agent」开始" style={{ padding: 48 }} />
            </Card>
          )
        )}
      </Spin>

      {/* 创建/编辑 Agent Modal */}
      <Modal
        title={editing ? '编辑 Agent' : '创建 Agent'}
        open={editModal}
        onOk={handleSave}
        onCancel={() => setEditModal(false)}
        width={600}
      >
        <Form form={form} layout="vertical" style={{ marginTop: 16 }}>
          <Form.Item name="name" label="名称" rules={[{ required: true, message: '请输入 Agent 名称' }]}>
            <Input placeholder="如：每日热点分析助手" />
          </Form.Item>
          <Form.Item name="agent_type" label="Agent 类型" rules={[{ required: true, message: '请选择 Agent 类型' }]}>
            <Select
              placeholder="选择 Agent 类型"
              options={agentTypeOptions}
              optionRender={option => (
                <Tag color={agentTypeColors[option.value]}>{option.label}</Tag>
              )}
            />
          </Form.Item>
          <Form.Item name="description" label="描述">
            <TextArea rows={3} placeholder="描述该 Agent 的功能和用途..." />
          </Form.Item>
          <Form.Item
            name="config_json"
            label="配置 (JSON)"
            extra="输入 JSON 格式的配置，如提示词模板、参数等"
          >
            <TextArea
              rows={6}
              placeholder={'{\n  "prompt": "你是一个内容生成助手...",\n  "model": "deepseek",\n  "params": {}\n}'}
              style={{ fontFamily: 'monospace' }}
            />
          </Form.Item>
        </Form>
      </Modal>

      {/* 执行结果 Modal */}
      <Modal
        title={<span><RobotOutlined /> Agent 执行结果</span>}
        open={runModal}
        onCancel={() => { setRunModal(false); setRunResult(null) }}
        footer={<Button onClick={() => { setRunModal(false); setRunResult(null) }}>关闭</Button>}
        width={700}
      >
        {runResult ? (
          <div>
            <Card size="small" style={{ marginBottom: 16 }}>
              <Row gutter={16}>
                <Col span={12}>
                  <p><strong>Agent：</strong>{runResult.agent.name}</p>
                  <p><strong>类型：</strong>
                    <Tag color={agentTypeColors[runResult.agent.agent_type]}>
                      {agentTypeLabels[runResult.agent.agent_type]}
                    </Tag>
                  </p>
                </Col>
                <Col span={12}>
                  <p><strong>执行时间：</strong>{dayjs().format('YYYY-MM-DD HH:mm:ss')}</p>
                  <p><strong>状态：</strong>
                    <Tag color="green" icon={<CheckCircleOutlined />}>已完成</Tag>
                  </p>
                </Col>
              </Row>
            </Card>

            {runResult.result && (
              <Card size="small" title="执行输出">
                {runResult.result.message && (
                  <div style={{ marginBottom: 12, fontWeight: 600 }}>
                    {runResult.result.message}
                  </div>
                )}
                {runResult.result.output && (
                  <div style={{
                    background: '#f5f5f5', padding: 16, borderRadius: 8,
                    whiteSpace: 'pre-wrap', lineHeight: 1.8, maxHeight: 400, overflow: 'auto',
                  }}>
                    {runResult.result.output}
                  </div>
                )}
                {runResult.result.data && (
                  <pre style={{
                    background: '#f5f5f5', padding: 16, borderRadius: 8,
                    maxHeight: 400, overflow: 'auto', margin: 0,
                  }}>
                    {typeof runResult.result.data === 'object'
                      ? JSON.stringify(runResult.result.data, null, 2)
                      : String(runResult.result.data)}
                  </pre>
                )}
                {!runResult.result.message && !runResult.result.output && !runResult.result.data && (
                  <pre style={{
                    background: '#f5f5f5', padding: 16, borderRadius: 8,
                    maxHeight: 400, overflow: 'auto', margin: 0,
                  }}>
                    {typeof runResult.result === 'object'
                      ? JSON.stringify(runResult.result, null, 2)
                      : String(runResult.result)}
                  </pre>
                )}
              </Card>
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
