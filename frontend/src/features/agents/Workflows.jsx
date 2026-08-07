import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Tag, Button, Space, message, Empty, Spin, Typography, Modal, Card, Row, Col, Collapse,
} from 'antd'
import {
  ReloadOutlined, TeamOutlined, RobotOutlined,
  ThunderboltOutlined, FundProjectionScreenOutlined, RocketOutlined, PlusOutlined,
} from '@ant-design/icons'
import { agentsApi } from '../../api'

const { Text, Paragraph } = Typography

const TYPE_META = {
  customer: {
    color: 'green',
    icon: <TeamOutlined />,
    verb: '让助手跟进',
    hint: '点卡片按钮，助手会给出跟进话术和下一步建议。',
  },
  operations: {
    color: 'blue',
    icon: <FundProjectionScreenOutlined />,
    verb: '一键执行',
    hint: '刷新热点、写文案、做视频等，点一下即可交给助手。',
  },
  publish: {
    color: 'orange',
    icon: <RocketOutlined />,
    verb: '一键执行',
    hint: '处理待发布任务，助手帮你推进发布。',
  },
}

export default function Workflows() {
  const navigate = useNavigate()
  const [assistants, setAssistants] = useState([])
  const [activeId, setActiveId] = useState(null)
  const [tasksData, setTasksData] = useState(null)
  const [loadingList, setLoadingList] = useState(true)
  const [loadingTasks, setLoadingTasks] = useState(false)
  const [runningKey, setRunningKey] = useState(null)
  const [lastOutput, setLastOutput] = useState('')

  const active = assistants.find(a => String(a.id) === String(activeId)) || assistants[0]
  const agentType = active?.agent_type || 'customer'
  const meta = TYPE_META[agentType] || TYPE_META.customer

  const loadAssistants = useCallback(() => {
    setLoadingList(true)
    agentsApi.assistants()
      .then(res => {
        const list = res?.list || []
        setAssistants(list)
        setActiveId(prev => {
          if (prev && list.some(a => String(a.id) === String(prev))) return prev
          return list[0]?.id ?? null
        })
      })
      .catch(() => message.error('加载 AI 助手失败'))
      .finally(() => setLoadingList(false))
  }, [])

  const loadTasks = useCallback((type) => {
    if (!type) return
    setLoadingTasks(true)
    agentsApi.assistantTasks(type)
      .then(res => setTasksData(res || null))
      .catch(() => {
        setTasksData(null)
        message.error('加载任务失败')
      })
      .finally(() => setLoadingTasks(false))
  }, [])

  useEffect(() => { loadAssistants() }, [loadAssistants])
  useEffect(() => {
    if (active?.agent_type) {
      loadTasks(active.agent_type)
      setLastOutput(active.last_result || '')
    }
  }, [active?.id, active?.agent_type, active?.last_result, loadTasks])

  const runTask = (taskItem) => {
    if (!active) return
    const key = taskItem?.id || 'all'
    setRunningKey(key)
    const payload = {
      task: taskItem?.task || '',
      customer_id: taskItem?.customer_id,
      trigger: 'manual',
    }
    agentsApi.run(active.id, payload)
      .then(res => {
        const output = res?.output || res?.message || '已完成'
        setLastOutput(output)
        message.success(typeof output === 'string' ? output.split('\n')[0] : '已完成')
        loadTasks(active.agent_type)
        loadAssistants()
        Modal.info({
          title: `${active.name || '助手'} · 执行结果`,
          width: 560,
          content: (
            <pre style={{ whiteSpace: 'pre-wrap', margin: 0, fontFamily: 'inherit', lineHeight: 1.7 }}>
              {output}
            </pre>
          ),
        })
      })
      .catch(err => message.error(err?.error || '执行失败'))
      .finally(() => setRunningKey(null))
  }

  const tasks = tasksData?.tasks || []

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16, gap: 12, flexWrap: 'wrap' }}>
        <div>
          <div className="page-title">AI助手</div>
          <div className="page-desc" style={{ marginBottom: 0 }}>
            选一个助手，点任务卡片即可执行。适合客户跟进、内容运营和发布这类重复操作。
          </div>
        </div>
        <Space>
          <Button icon={<PlusOutlined />} onClick={() => navigate('/agents')}>配置 Agent</Button>
          <Button icon={<ReloadOutlined />} onClick={() => { loadAssistants(); if (active) loadTasks(active.agent_type) }}>
            刷新
          </Button>
        </Space>
      </div>

      <Spin spinning={loadingList}>
        {assistants.length === 0 ? (
          <Empty description="还没有助手。请先在 Agent 中心创建并填写系统提示词。">
            <Button type="primary" onClick={() => navigate('/agents')}>打开 Agent 中心</Button>
          </Empty>
        ) : (
          <>
            <div style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))',
              gap: 12,
              marginBottom: 20,
            }}
            >
              {assistants.map((a) => {
                const m = TYPE_META[a.agent_type] || TYPE_META.customer
                const selected = String(a.id) === String(active?.id)
                return (
                  <button
                    key={a.id}
                    type="button"
                    onClick={() => setActiveId(a.id)}
                    style={{
                      textAlign: 'left',
                      cursor: 'pointer',
                      border: selected ? '1.5px solid #5b5bd6' : '1px solid #ededf0',
                      background: selected ? 'rgba(59,130,246,0.06)' : '#fff',
                      borderRadius: 14,
                      padding: '14px 16px',
                      boxShadow: selected ? '0 8px 20px rgba(59,130,246,0.08)' : 'none',
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
                      <span style={{
                        width: 32,
                        height: 32,
                        borderRadius: 10,
                        display: 'grid',
                        placeItems: 'center',
                        background: selected ? '#5b5bd6' : '#fafafa',
                        color: selected ? '#fff' : '#6b6b80',
                      }}
                      >
                        {m.icon || <RobotOutlined />}
                      </span>
                      <Text strong style={{ fontSize: 14 }}>{a.name || a.label}</Text>
                    </div>
                    <Tag color={m.color}>{a.label || a.agent_type}</Tag>
                  </button>
                )
              })}
            </div>

            {active && (
              <div style={{ marginBottom: 16 }}>
                <Paragraph type="secondary" style={{ marginBottom: 8 }}>
                  {tasksData?.intro || meta.hint}
                </Paragraph>
                {active.system_prompt ? (
                  <Collapse
                    ghost
                    size="small"
                    items={[{
                      key: 'prompt',
                      label: <span style={{ color: '#6b6b80', fontSize: 13 }}>查看系统提示词</span>,
                      children: (
                        <div style={{
                          background: '#f8fafc',
                          border: '1px solid #ededf0',
                          borderRadius: 10,
                          padding: 12,
                          fontSize: 13,
                          color: '#475569',
                          whiteSpace: 'pre-wrap',
                          lineHeight: 1.7,
                        }}
                        >
                          {active.system_prompt}
                        </div>
                      ),
                    }]}
                  />
                ) : null}
              </div>
            )}

            <Spin spinning={loadingTasks}>
              {tasks.length === 0 ? (
                <Empty description={agentType === 'customer' ? '暂无待跟进客户。新增客户或写跟进后会出现在这里。' : '暂无待办任务'} />
              ) : (
                <Row gutter={[14, 14]}>
                  {tasks.map((t) => (
                    <Col xs={24} md={12} xl={8} key={t.id}>
                      <Card
                        size="small"
                        hoverable
                        styles={{ body: { padding: 16 } }}
                        style={{
                          height: '100%',
                          borderRadius: 14,
                          borderColor: runningKey === t.id ? '#93c5fd' : '#ededf0',
                        }}
                      >
                        <div style={{ fontWeight: 600, fontSize: 15, marginBottom: 8, color: '#1e1e2e' }}>
                          {t.title}
                          {t.runnable === false ? (
                            <Tag style={{ marginLeft: 8 }}>暂不可执行</Tag>
                          ) : null}
                        </div>
                        <div style={{
                          color: '#6b6b80',
                          fontSize: 13,
                          lineHeight: 1.6,
                          marginBottom: 14,
                          minHeight: 40,
                        }}
                        >
                          {t.desc}
                        </div>
                        <Space wrap>
                          <Button
                            type="primary"
                            icon={<ThunderboltOutlined />}
                            disabled={t.runnable === false}
                            loading={runningKey === t.id}
                            onClick={() => runTask(t)}
                          >
                            {meta.verb}
                          </Button>
                          {t.secondary?.path ? (
                            <Button onClick={() => navigate(t.secondary.path)}>
                              {t.secondary.label || '打开'}
                            </Button>
                          ) : null}
                        </Space>
                      </Card>
                    </Col>
                  ))}
                </Row>
              )}
            </Spin>

            {lastOutput ? (
              <Card
                size="small"
                title="最近一次结果"
                style={{ marginTop: 20, borderRadius: 14 }}
                styles={{ body: { padding: 14 } }}
              >
                <pre style={{
                  margin: 0,
                  whiteSpace: 'pre-wrap',
                  fontFamily: 'inherit',
                  fontSize: 13,
                  color: '#334155',
                  lineHeight: 1.7,
                  maxHeight: 160,
                  overflow: 'auto',
                }}
                >
                  {lastOutput}
                </pre>
              </Card>
            ) : null}
          </>
        )}
      </Spin>
    </div>
  )
}
