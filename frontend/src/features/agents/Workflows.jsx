import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Tag, Button, Space, message, Empty, Spin, Typography, Tabs, Steps, Modal,
} from 'antd'
import {
  ReloadOutlined, TeamOutlined, RobotOutlined,
  ThunderboltOutlined, FundProjectionScreenOutlined, RocketOutlined, PlusOutlined,
} from '@ant-design/icons'
import { agentsApi } from '../../api'

const { Text, Paragraph } = Typography

const TYPE_META = {
  customer: { color: 'green', icon: <TeamOutlined />, verb: '让助手跟进' },
  operations: { color: 'blue', icon: <FundProjectionScreenOutlined />, verb: '执行' },
  publish: { color: 'orange', icon: <RocketOutlined />, verb: '执行' },
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
          <Space>
            <RobotOutlined style={{ fontSize: 20, color: '#5b6eff' }} />
            <Text strong style={{ fontSize: 16 }}>AI 助手</Text>
          </Space>
          <div style={{ color: '#888', fontSize: 13, marginTop: 4 }}>
            像工作流一样，把客户跟进、写文案、做视频、发布等重复操作交给助手执行。
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
            <Tabs
              activeKey={String(active?.id || '')}
              onChange={(key) => setActiveId(Number(key))}
              items={assistants.map(a => ({
                key: String(a.id),
                label: (
                  <Space>
                    {(TYPE_META[a.agent_type] || {}).icon || <RobotOutlined />}
                    {a.name || a.label}
                  </Space>
                ),
              }))}
            />

            {active && (
              <div style={{ marginBottom: 20 }}>
                <Space wrap style={{ marginBottom: 8 }}>
                  <Text strong style={{ fontSize: 15 }}>{active.name}</Text>
                  <Tag color={meta.color}>{active.label || agentType}</Tag>
                </Space>
                <Paragraph type="secondary" style={{ marginBottom: 8 }}>
                  {tasksData?.intro || active.description || '按步骤执行下方任务'}
                </Paragraph>
                {active.system_prompt ? (
                  <Paragraph
                    type="secondary"
                    ellipsis={{ rows: 2, expandable: true, symbol: '展开提示词' }}
                    style={{ fontSize: 12, background: '#fafafa', padding: '8px 12px', borderRadius: 6 }}
                  >
                    系统提示词：{active.system_prompt}
                  </Paragraph>
                ) : null}
              </div>
            )}

            <Spin spinning={loadingTasks}>
              {tasks.length === 0 ? (
                <Empty description={agentType === 'customer' ? '暂无待跟进客户。新增客户或写跟进后会出现在这里。' : '暂无待办任务'} />
              ) : (
                <Steps
                  direction="vertical"
                  current={-1}
                  items={tasks.map((t) => ({
                    title: (
                      <Space wrap>
                        <span>{t.title}</span>
                        {t.runnable === false ? <Tag>暂不可执行</Tag> : null}
                      </Space>
                    ),
                    description: (
                      <div style={{ paddingBottom: 16 }}>
                        <div style={{ color: '#666', marginBottom: 10 }}>{t.desc}</div>
                        <Space wrap>
                          <Button
                            type="primary"
                            size="small"
                            icon={<ThunderboltOutlined />}
                            disabled={t.runnable === false}
                            loading={runningKey === t.id}
                            onClick={() => runTask(t)}
                          >
                            {meta.verb}
                          </Button>
                          {t.secondary?.path ? (
                            <Button size="small" onClick={() => navigate(t.secondary.path)}>
                              {t.secondary.label || '打开'}
                            </Button>
                          ) : null}
                        </Space>
                      </div>
                    ),
                    status: runningKey === t.id ? 'process' : 'wait',
                  }))}
                />
              )}
            </Spin>

            {lastOutput ? (
              <div style={{ marginTop: 24 }}>
                <Text type="secondary" style={{ fontSize: 12 }}>最近一次执行</Text>
                <pre style={{
                  marginTop: 6, background: '#f7f7f7', padding: 12, borderRadius: 8,
                  whiteSpace: 'pre-wrap', fontFamily: 'inherit', fontSize: 13, maxHeight: 180, overflow: 'auto',
                }}>
                  {lastOutput}
                </pre>
              </div>
            ) : null}
          </>
        )}
      </Spin>
    </div>
  )
}
