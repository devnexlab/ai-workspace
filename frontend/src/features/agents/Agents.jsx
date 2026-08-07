import { useState, useEffect } from 'react'
import {
  Tag, Button, Space, Modal, message,
  Form, Popconfirm, Tooltip, Row, Col, Card,
  Input, Select, Spin, Empty, Typography,
} from 'antd'
import {
  PlusOutlined, EditOutlined, DeleteOutlined, ReloadOutlined,
  RobotOutlined, PlayCircleOutlined, CheckCircleOutlined,
  ClockCircleOutlined, ExclamationCircleOutlined,
} from '@ant-design/icons'
import { agentsApi } from '../../api'
import { formatDateTime } from '../../utils/date'

const { TextArea } = Input
const { Paragraph, Text } = Typography

const agentTypeOptions = [
  { value: 'customer', label: '客户管理' },
  { value: 'operations', label: '运营管理' },
  { value: 'publish', label: '发布管理' },
]
const agentTypeLabels = Object.fromEntries(agentTypeOptions.map(o => [o.value, o.label]))
const agentTypeColors = { customer: 'green', operations: 'blue', publish: 'orange' }

const DEFAULT_PROMPTS = {
  customer: `你是资深保险顾问的「客户管理助手」，熟悉寿险/重疾/医疗/增额寿等产品的销售与售后节奏。

【职责】
1. 根据客户画像、意向、性格与最近跟进记录，判断生命周期是否应推进（new→appointment→tracking→proposal→deal→aftercare），证据不足则不盲目推进。
2. 给出 1～3 条当天可执行的跟进动作（电话/微信/约访/发方案/成交确认等），并附简短话术要点与建议联系时段。
3. 高意向、久未联系、约访临近、方案待反馈的客户优先处理。

【每日节奏建议】
- 每天 09:00：梳理待跟进清单，优先处理高意向与逾期未联系客户。
- 每天 11:00、15:00：集中电话/微信触达，写清跟进结果。
- 每天 17:30：复盘未接通与待约访，安排次日提醒。

【输出要求】语言简洁、可直接照做；涉及阶段推进必须有明确依据。`,
  operations: `你是保险短视频团队的「运营管理助手」，负责把「采热点→写文案→做视频」这些重复操作串成日更流水线，减少人工逐一点击。

【职责】
1. 刷新内容情报：筛选可改编、有共鸣、适合口播的泛流量/保险相关热点。
2. 生成文案：口播好念、开头 3 秒抓人、中段有共鸣或避坑点、结尾可带品牌收束；区分流量款与保险专业款。
3. 创建/推进视频：为定稿文案建视频任务，推动配音与合成，避免半成品堆积。
4. 优先处理积压：先清未写文案的热点，再清未出片的文案，再交给发布助手。

【每日定时节奏】
- 每天 08:00：刷新内容情报，选出当日可改编选题。
- 每天 09:00：按日更计划生成文案（如 2 条流量 + 1 条保险）。
- 每天 10:00：为已定稿文案创建视频并启动制作。
- 需要时执行「一键日更」：按上述顺序串行完成采写拍。

【输出要求】给出明确下一步与优先级；文案建议需适合竖屏口播朗读。`,
  publish: `你是保险短视频团队的「发布管理助手」，负责多平台发布节奏、失败重试与标题封面优化。

【职责】
1. 为已完成成片创建发布任务，补全平台与标题/封面要点。
2. 优先重试失败任务（检查 Cookies、成片路径、平台启用状态）。
3. 对待发布任务按平台错峰执行，避免同平台短时间连发。
4. 标题利于点击，封面文案短、有冲突感或利益点，描述清晰不违规。

【每日定时节奏】
- 每天 11:00：检查成片，为未建任务的视频创建发布任务。
- 每天 12:00、18:00、21:00：分批执行待发布（可覆盖抖音/小红书/视频号错峰）。
- 每天 19:00：集中处理失败发布并重试。

【输出要求】说明先做哪几个任务、为何此时段发；失败要给出可操作的排查点。`,
}

const statusColors = { idle: 'blue', running: 'green', error: 'red', active: 'processing' }
const statusLabels = { idle: '空闲', running: '运行中', error: '错误', active: '活跃' }

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
      const data = {
        name: values.name,
        agent_type: values.agent_type,
        description: values.description || '',
        system_prompt: values.system_prompt || '',
      }
      const req = editing
        ? agentsApi.update(editing.id, data)
        : agentsApi.create(data)
      req.then(() => {
        message.success(editing ? '已更新' : '已创建，可在「AI助手」中使用')
        setEditModal(false)
        loadData()
      }).catch(err => message.error(err?.error || '保存失败'))
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
    }).finally(() => setRunningId(null))
  }

  const handleEdit = (record) => {
    setEditing(record)
    form.setFieldsValue({
      name: record.name,
      agent_type: record.agent_type,
      description: record.description,
      system_prompt: record.system_prompt || DEFAULT_PROMPTS[record.agent_type] || '',
    })
    setEditModal(true)
  }

  const handleAdd = () => {
    setEditing(null)
    form.resetFields()
    form.setFieldsValue({
      agent_type: 'customer',
      system_prompt: DEFAULT_PROMPTS.customer,
    })
    setEditModal(true)
  }

  const onTypeChange = (type) => {
    const cur = form.getFieldValue('system_prompt')
    const isDefault = !cur || Object.values(DEFAULT_PROMPTS).includes(cur)
    if (isDefault) {
      form.setFieldsValue({ system_prompt: DEFAULT_PROMPTS[type] || '' })
    }
  }

  return (
    <div>
      <div className="page-title">Agent 中心</div>
      <div className="page-desc">
        创建助手并填写系统提示词。执行时按提示词完成客户跟进 / 采写拍 / 发布等重复工作，结果在「AI助手」中使用。
      </div>

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
              <Col key={agent.id} xs={24} sm={12} md={8} lg={8}>
                <Card
                  hoverable
                  size="small"
                  title={
                    <Space>
                      <RobotOutlined />
                      <span>{agent.name}</span>
                    </Space>
                  }
                  extra={
                    <Tag color={statusColors[agent.status]}>
                      {statusLabels[agent.status] || agent.status}
                    </Tag>
                  }
                  actions={[
                    <Tooltip title="按系统提示词执行任务" key="run">
                      <Button
                        type="primary"
                        size="small"
                        ghost
                        icon={<PlayCircleOutlined />}
                        loading={runningId === agent.id}
                        onClick={() => handleRun(agent)}
                      >执行</Button>
                    </Tooltip>,
                    <Button key="edit" size="small" icon={<EditOutlined />} onClick={() => handleEdit(agent)}>编辑</Button>,
                    <Popconfirm
                      key="delete"
                      title="确认删除？"
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
                  <Tag color={agentTypeColors[agent.agent_type]} style={{ marginBottom: 8 }}>
                    {agentTypeLabels[agent.agent_type] || agent.agent_type}
                  </Tag>
                  <Paragraph type="secondary" ellipsis={{ rows: 2 }} style={{ minHeight: 44, marginBottom: 8, fontSize: 13 }}>
                    {agent.description || '暂无描述'}
                  </Paragraph>
                  <Paragraph ellipsis={{ rows: 3 }} style={{ fontSize: 12, color: '#666', marginBottom: 8, background: '#fafafa', padding: 8, borderRadius: 6 }}>
                    <Text type="secondary">系统提示词：</Text>
                    {agent.system_prompt || '（未设置，将使用默认）'}
                  </Paragraph>
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    <ClockCircleOutlined /> 上次执行：{agent.last_run ? formatDateTime(agent.last_run) : '未执行'}
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

      <Modal
        title={editing ? '编辑 Agent' : '创建 Agent'}
        open={editModal}
        onOk={handleSave}
        onCancel={() => setEditModal(false)}
        width={640}
        okText="保存"
      >
        <Form form={form} layout="vertical" style={{ marginTop: 16 }}>
          <Form.Item name="name" label="名称" rules={[{ required: true, message: '请输入名称' }]}>
            <Input placeholder="如：客户跟进助手" />
          </Form.Item>
          <Form.Item name="agent_type" label="助手类型" rules={[{ required: true, message: '请选择类型' }]}>
            <Select
              options={agentTypeOptions}
              onChange={onTypeChange}
              optionRender={option => (
                <Tag color={agentTypeColors[option.value]}>{option.label}</Tag>
              )}
            />
          </Form.Item>
          <Form.Item name="description" label="说明（可选）">
            <TextArea rows={2} placeholder="这个助手帮你做什么，一句话即可" />
          </Form.Item>
          <Form.Item
            name="system_prompt"
            label="系统提示词"
            rules={[{ required: true, message: '请填写系统提示词' }]}
            extra="用自然语言写清角色、职责，以及每日几点做什么（如：每天 08:00 刷新情报，09:00 生成文案）。无需 JSON，也无需单独配定时任务。"
          >
            <TextArea rows={12} placeholder="你是……助手。职责……每日节奏……" />
          </Form.Item>
          <Button
            type="link"
            style={{ padding: 0, marginTop: -8, marginBottom: 8 }}
            onClick={() => {
              const t = form.getFieldValue('agent_type') || 'customer'
              form.setFieldsValue({ system_prompt: DEFAULT_PROMPTS[t] || '' })
            }}
          >
            填入该类型的专业默认提示词
          </Button>
        </Form>
      </Modal>

      <Modal
        title={<span><RobotOutlined /> 执行结果</span>}
        open={runModal}
        onCancel={() => { setRunModal(false); setRunResult(null) }}
        footer={<Button onClick={() => { setRunModal(false); setRunResult(null) }}>关闭</Button>}
        width={640}
      >
        {runResult ? (
          <div>
            <Space style={{ marginBottom: 12 }} wrap>
              <Text strong>{runResult.agent.name}</Text>
              <Tag color={agentTypeColors[runResult.agent.agent_type]}>
                {agentTypeLabels[runResult.agent.agent_type]}
              </Tag>
              <Tag color="green" icon={<CheckCircleOutlined />}>已完成</Tag>
            </Space>
            <div style={{
              background: '#f5f5f5', padding: 16, borderRadius: 8,
              whiteSpace: 'pre-wrap', lineHeight: 1.8, maxHeight: 420, overflow: 'auto',
            }}>
              {runResult.result?.output
                || runResult.result?.message
                || (typeof runResult.result?.result === 'string' ? runResult.result.result : null)
                || '执行完成'}
            </div>
          </div>
        ) : (
          <div style={{ textAlign: 'center', padding: 40 }}>
            <Spin size="large" />
          </div>
        )}
      </Modal>
    </div>
  )
}
