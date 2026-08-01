import { useState, useEffect } from 'react'
import {
  Tag, Button, Space, Modal, message,
  Popconfirm, Tooltip, Row, Col, Card, Statistic,
  Steps, Empty, Spin, Typography,
} from 'antd'
import {
  PlusOutlined, DeleteOutlined, ReloadOutlined,
  ForwardOutlined, RobotOutlined, TeamOutlined,
  FileTextOutlined, StockOutlined, CheckCircleOutlined,
  ClockCircleOutlined, PlayCircleOutlined,
} from '@ant-design/icons'
import { workflowsApi } from '../../api'
import dayjs from 'dayjs'

const { Text } = Typography

// 工作流类型配置
const workflowTypeOptions = [
  { value: 'customer', label: '客户跟进流程' },
  { value: 'content', label: '内容运营流程' },
  { value: 'stock', label: '股票研究流程' },
]
const workflowTypeLabels = Object.fromEntries(workflowTypeOptions.map(o => [o.value, o.label]))
const workflowTypeColors = { customer: 'green', content: 'blue', stock: 'gold' }
const workflowTypeIcons = {
  customer: <TeamOutlined />,
  content: <FileTextOutlined />,
  stock: <StockOutlined />,
}

// 模板步骤定义
const templateSteps = {
  customer: ['客户识别', '需求分析', '初次接触', '方案提供', '跟进沟通', '成交转化'],
  content: ['选题策划', '热点分析', '大纲制定', '文案撰写', '内容审核', '视觉制作', '视频剪辑', '发布准备', '数据复盘'],
  stock: ['行业筛选', '个股初筛', '基本面分析', '技术面分析', '风险评估', '投资决策', '持仓跟踪'],
}
const templateDescriptions = {
  customer: '从客户识别到成交转化的完整跟进流程，共 6 个步骤',
  content: '从选题策划到数据复盘的内容运营全流程，共 9 个步骤',
  stock: '从行业筛选到持仓跟踪的股票研究流程，共 7 个步骤',
}

// 工作流状态配置
const statusColors = { draft: 'default', running: 'processing', completed: 'success' }
const statusLabels = { draft: '草稿', running: '进行中', completed: '已完成' }
const statusIcons = {
  draft: <ClockCircleOutlined />,
  running: <PlayCircleOutlined />,
  completed: <CheckCircleOutlined />,
}

export default function Workflows() {
  const [list, setList] = useState([])
  const [templates, setTemplates] = useState({})
  const [loading, setLoading] = useState(true)
  const [advancingId, setAdvancingId] = useState(null)
  const [createModal, setCreateModal] = useState(false)
  const [selectedType, setSelectedType] = useState(null)

  const loadData = () => {
    setLoading(true)
    workflowsApi.list()
      .then(res => setList(res?.list || res || []))
      .catch(() => message.error('加载工作流列表失败'))
      .finally(() => setLoading(false))
  }

  const loadTemplates = () => {
    workflowsApi.templates()
      .then(res => {
        // 后端返回模板数据，合并本地步骤定义作为后备
        const data = res?.templates || res || {}
        setTemplates(data)
      })
      .catch(() => {
        // 后端未返回则使用本地定义
      })
  }

  useEffect(() => {
    loadData()
    loadTemplates()
  }, [])

  // 获取工作流步骤列表：优先使用后端返回的，其次用本地模板定义
  const getSteps = (workflow) => {
    let steps = []
    if (workflow.steps_json) {
      try {
        const parsed = typeof workflow.steps_json === 'string'
          ? JSON.parse(workflow.steps_json)
          : workflow.steps_json
        steps = Array.isArray(parsed)
          ? parsed.map(s => typeof s === 'string' ? s : (s.name || s.title || String(s)))
          : []
      } catch {
        steps = []
      }
    }
    if (steps.length === 0 && workflow.workflow_type) {
      steps = templateSteps[workflow.workflow_type] || []
    }
    return steps
  }

  const handleCreateFromTemplate = (type) => {
    setSelectedType(type)
    setCreateModal(true)
  }

  const handleConfirmCreate = () => {
    const steps = templateSteps[selectedType] || []
    workflowsApi.create({
      name: workflowTypeLabels[selectedType],
      workflow_type: selectedType,
      steps_json: steps,
      status: 'draft',
      current_step: 0,
    }).then(() => {
      message.success('工作流已创建')
      setCreateModal(false)
      setSelectedType(null)
      loadData()
    }).catch(() => message.error('创建失败'))
  }

  const handleAdvance = (workflow) => {
    setAdvancingId(workflow.id)
    workflowsApi.advance(workflow.id).then(res => {
      message.success(res?.message || '工作流已推进')
      loadData()
    }).catch(err => {
      message.error(err?.error || '推进失败')
    }).finally(() => {
      setAdvancingId(null)
    })
  }

  const totalCount = list.length
  const runningCount = list.filter(w => w.status === 'running').length
  const completedCount = list.filter(w => w.status === 'completed').length

  // 渲染模板卡片
  const renderTemplateCards = () => {
    return workflowTypeOptions.map(opt => {
      const steps = templateSteps[opt.value] || []
      const tplData = templates[opt.value] || {}
      return (
        <Card
          key={opt.value}
          size="small"
          hoverable
          style={{ marginBottom: 16 }}
          onClick={() => handleCreateFromTemplate(opt.value)}
        >
          <div style={{ display: 'flex', alignItems: 'center', marginBottom: 8 }}>
            {workflowTypeIcons[opt.value]}
            <span style={{ marginLeft: 8, fontWeight: 600, fontSize: 15 }}>
              {opt.label}
            </span>
          </div>
          <Tag color={workflowTypeColors[opt.value]} style={{ marginBottom: 8 }}>
            {opt.value}
          </Tag>
          <p style={{ fontSize: 12, color: '#999', marginBottom: 12 }}>
            {tplData.description || templateDescriptions[opt.value]}
          </p>
          <div style={{ fontSize: 12, color: '#666', marginBottom: 12 }}>
            <ClockCircleOutlined /> 共 {tplData.steps?.length || steps.length} 个步骤
          </div>
          <Button
            type="primary"
            block
            icon={<PlusOutlined />}
            size="small"
          >
            从模板创建
          </Button>
        </Card>
      )
    })
  }

  // 渲染工作流卡片
  const renderWorkflowCard = (workflow) => {
    const steps = getSteps(workflow)
    const currentStep = workflow.current_step ?? 0
    const totalSteps = steps.length
    const isCompleted = workflow.status === 'completed'
    const isRunning = workflow.status === 'running'

    return (
      <Card
        key={workflow.id}
        size="small"
        style={{ marginBottom: 16 }}
        title={
          <Space>
            {workflowTypeIcons[workflow.workflow_type]}
            <span>{workflow.name}</span>
          </Space>
        }
        extra={
          <Tag color={statusColors[workflow.status]} icon={statusIcons[workflow.status]}>
            {statusLabels[workflow.status] || workflow.status}
          </Tag>
        }
        actions={[
          <Tooltip title="推进到下一步" key="advance">
            <Button
              type="primary"
              size="small"
              ghost
              icon={<ForwardOutlined />}
              loading={advancingId === workflow.id}
              disabled={isCompleted}
              onClick={() => handleAdvance(workflow)}
            >
              推进
            </Button>
          </Tooltip>,
          <Popconfirm
            key="delete"
            title="确认删除该工作流？"
            onConfirm={() => {
              workflowsApi.delete(workflow.id).then(() => {
                message.success('已删除')
                loadData()
              }).catch(() => message.error('删除失败'))
            }}
          >
            <Button size="small" danger icon={<DeleteOutlined />}>删除</Button>
          </Popconfirm>,
        ]}
      >
        {/* 类型与进度信息 */}
        <div style={{ marginBottom: 12 }}>
          <Space>
            <Tag color={workflowTypeColors[workflow.workflow_type]}>
              {workflowTypeLabels[workflow.workflow_type] || workflow.workflow_type}
            </Tag>
            <Text type="secondary" style={{ fontSize: 13 }}>
              步骤 {isCompleted ? totalSteps : currentStep + (isRunning || workflow.status === 'draft' ? 0 : 0)} / {totalSteps}
            </Text>
          </Space>
        </div>

        {/* Steps 进度条 */}
        <Steps
          size="small"
          current={isCompleted ? totalSteps - 1 : currentStep}
          status={isCompleted ? 'finish' : isRunning ? 'process' : 'wait'}
          direction="vertical"
          style={{ marginTop: 8 }}
          items={steps.map((step, idx) => ({
            title: <span style={{ fontSize: 13 }}>{step}</span>,
            status: isCompleted
              ? 'finish'
              : idx < currentStep
                ? 'finish'
                : idx === currentStep
                  ? (isRunning ? 'process' : 'wait')
                  : 'wait',
          }))}
        />

        {/* 底部时间信息 */}
        <div style={{ marginTop: 12, paddingTop: 8, borderTop: '1px solid #f0f0f0' }}>
          <Text type="secondary" style={{ fontSize: 12 }}>
            <ClockCircleOutlined /> 创建时间：{workflow.created_at
              ? dayjs(workflow.created_at).format('YYYY-MM-DD HH:mm')
              : '-'}
          </Text>
        </div>
      </Card>
    )
  }

  return (
    <div>
      <div className="page-title">工作流系统</div>

      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={6}>
          <Card size="small">
            <Statistic title="工作流总数" value={totalCount} prefix={<RobotOutlined />} />
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small">
            <Statistic title="进行中" value={runningCount} valueStyle={{ color: '#1890ff' }} prefix={<PlayCircleOutlined />} />
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small">
            <Statistic title="已完成" value={completedCount} valueStyle={{ color: '#52c41a' }} prefix={<CheckCircleOutlined />} />
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small">
            <Statistic title="草稿" value={list.filter(w => w.status === 'draft').length} valueStyle={{ color: '#999' }} prefix={<ClockCircleOutlined />} />
          </Card>
        </Col>
      </Row>

      <Row gutter={24}>
        {/* 左侧：模板区域 */}
        <Col xs={24} sm={24} md={7} lg={6}>
          <Card
            size="small"
            title={<span><PlusOutlined /> 工作流模板</span>}
            style={{ marginBottom: 16 }}
          >
            <p style={{ fontSize: 12, color: '#999', marginBottom: 16 }}>
              点击模板卡片快速创建工作流
            </p>
            {renderTemplateCards()}
          </Card>
        </Col>

        {/* 右侧：已有工作流列表 */}
        <Col xs={24} sm={24} md={17} lg={18}>
          <Card
            size="small"
            title={
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span>我的工作流</span>
                <Button size="small" icon={<ReloadOutlined />} onClick={loadData}>刷新</Button>
              </div>
            }
          >
            <Spin spinning={loading}>
              {list.length > 0 ? (
                <Row gutter={[16, 16]}>
                  {list.map(workflow => (
                    <Col key={workflow.id} xs={24} lg={12}>
                      {renderWorkflowCard(workflow)}
                    </Col>
                  ))}
                </Row>
              ) : (
                !loading && (
                  <Empty
                    description="暂无工作流，请从左侧模板创建"
                    style={{ padding: 48 }}
                  />
                )
              )}
            </Spin>
          </Card>
        </Col>
      </Row>

      {/* 创建确认 Modal */}
      <Modal
        title="创建工作流"
        open={createModal}
        onOk={handleConfirmCreate}
        onCancel={() => { setCreateModal(false); setSelectedType(null) }}
        width={520}
      >
        {selectedType && (
          <div>
            <div style={{ marginBottom: 16 }}>
              <Space>
                {workflowTypeIcons[selectedType]}
                <span style={{ fontSize: 16, fontWeight: 600 }}>
                  {workflowTypeLabels[selectedType]}
                </span>
              </Space>
            </div>
            <p style={{ color: '#666', marginBottom: 16 }}>
              {templateDescriptions[selectedType]}
            </p>
            <Card size="small" title="流程步骤预览" style={{ marginBottom: 16 }}>
              <Steps
                size="small"
                direction="vertical"
                current={0}
                items={(templateSteps[selectedType] || []).map(step => ({
                  title: <span style={{ fontSize: 13 }}>{step}</span>,
                }))}
              />
            </Card>
            <p style={{ fontSize: 13, color: '#999' }}>
              创建后工作流将处于「草稿」状态，可通过「推进」按钮逐步执行各步骤。
            </p>
          </div>
        )}
      </Modal>
    </div>
  )
}
