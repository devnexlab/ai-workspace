import { useState, useEffect, useCallback, useRef } from 'react'
import { useSearchParams } from 'react-router-dom'
import {
  Table, Tag, Button, Input, Select, Space, Modal, message, Form, Popconfirm,
  Tooltip, Drawer, Row, Col, Card, Statistic, Timeline, DatePicker, Tabs,
  Progress, Alert, List, Badge, Divider, Empty, Descriptions,
} from 'antd'
import {
  PlusOutlined, EditOutlined, DeleteOutlined, SearchOutlined, ReloadOutlined,
  EyeOutlined, MessageOutlined, TeamOutlined, BellOutlined, RobotOutlined,
  CheckOutlined, ClockCircleOutlined, ThunderboltOutlined, UserOutlined,
  AudioOutlined,
} from '@ant-design/icons'
import { customersApi, followsApi, remindersApi } from '../../api'
import dayjs from 'dayjs'
import { formatDate, formatDateTime } from '../../utils/date'

function parseAssistantPayload(aiAnalysis) {
  if (!aiAnalysis) return null
  let raw = aiAnalysis.ai_analysis
  if (typeof raw === 'string' && raw.trim()) {
    try { raw = JSON.parse(raw) } catch { raw = null }
  }
  if (raw && typeof raw === 'object') {
    return {
      summary: raw.summary || '',
      next_actions: raw.next_actions || (raw.next_step ? [raw.next_step] : []),
      talk_tips: raw.talk_tips || '',
      best_time: raw.best_time || '',
      next_step: raw.next_step || aiAnalysis.next_step || '',
      stage_label: raw.stage_label || '',
      advanced: !!raw.advanced,
    }
  }
  if (aiAnalysis.next_step) {
    return { summary: '', next_actions: [aiAnalysis.next_step], talk_tips: '', best_time: '', next_step: aiAnalysis.next_step }
  }
  return null
}

function showAssistantTip(assistant, fallbackMsg) {
  if (!assistant || assistant.error || assistant.skipped) {
    if (fallbackMsg) message.success(fallbackMsg)
    return
  }
  const actions = (assistant.next_actions || []).filter(Boolean)
  const stagePart = assistant.advanced
    ? `已推进至「${assistant.stage_label || assistant.lifecycle_stage}」。`
    : (assistant.stage_label ? `当前阶段：${assistant.stage_label}。` : '')
  const actionPart = actions.length ? `下一步：${actions.slice(0, 2).join('；')}` : (assistant.next_step || '')
  message.success({
    content: `${fallbackMsg || '已完成'} ${stagePart}${actionPart}`.trim(),
    duration: 5,
  })
}

const STAGE_OPTIONS = [
  { value: 'new', label: '新增客户', color: 'default' },
  { value: 'appointment', label: '约访', color: 'blue' },
  { value: 'tracking', label: '跟踪中', color: 'orange' },
  { value: 'proposal', label: '方案沟通', color: 'purple' },
  { value: 'deal', label: '成交', color: 'green' },
  { value: 'aftercare', label: '售后维护', color: 'cyan' },
]
const STAGE_MAP = Object.fromEntries(STAGE_OPTIONS.map(s => [s.value, s]))

const INTENTION_OPTIONS = [
  { value: 'high', label: '高意向' },
  { value: 'medium', label: '中意向' },
  { value: 'low', label: '低意向' },
]
const INTENTION_COLORS = { high: 'red', medium: 'orange', low: 'default' }
const INTENTION_LABELS = { high: '高意向', medium: '中意向', low: '低意向' }

const PERSONALITY_OPTIONS = [
  { value: 'rational', label: '理性型' },
  { value: 'emotional', label: '感性型' },
  { value: 'cautious', label: '谨慎型' },
  { value: 'decisive', label: '果断型' },
  { value: 'social', label: '社交型' },
]
const PERSONALITY_MAP = Object.fromEntries(PERSONALITY_OPTIONS.map(p => [p.value, p.label]))

const FOLLOW_RESULTS = [
  { value: 'appointment_scheduled', label: '已约访 → 进入约访' },
  { value: 'interested', label: '有兴趣 → 进入跟踪' },
  { value: 'proposal_sent', label: '已发方案 → 方案沟通' },
  { value: 'deal_closed', label: '已成交 → 成交' },
  { value: 'policy_delivered', label: '保单送达 → 售后' },
  { value: 'no_answer', label: '未接通' },
  { value: 'postponed', label: '客户推迟' },
  { value: 'general', label: '普通沟通' },
]

const METHOD_OPTIONS = [
  { value: 'wechat', label: '微信' },
  { value: 'phone', label: '电话' },
  { value: 'offline', label: '面谈' },
  { value: 'other', label: '其他' },
]

const PRIORITY_COLORS = { urgent: 'red', high: 'orange', normal: 'blue' }
const PRIORITY_LABELS = { urgent: '紧急', high: '重要', normal: '普通' }

export default function Customers() {
  const [searchParams, setSearchParams] = useSearchParams()
  const [activeTab, setActiveTab] = useState(() => (
    searchParams.get('tab') === 'reminders' ? 'reminders' : 'list'
  ))
  const [data, setData] = useState({ list: [], total: 0, stageStats: {} })
  const [loading, setLoading] = useState(true)
  const [page, setPage] = useState(1)
  const [filters, setFilters] = useState({})
  const [owners, setOwners] = useState([])

  const [editModal, setEditModal] = useState(false)
  const [followModal, setFollowModal] = useState(false)
  const [detailDrawer, setDetailDrawer] = useState(false)
  const [form] = Form.useForm()
  const [followForm] = Form.useForm()
  const [editing, setEditing] = useState(null)
  const [viewing, setViewing] = useState(null)
  const [currentCustomerId, setCurrentCustomerId] = useState(null)
  const [followResult, setFollowResult] = useState('')
  const [followTab, setFollowTab] = useState('smart')
  const [smartText, setSmartText] = useState('')
  const [smartParsing, setSmartParsing] = useState(false)
  const [listening, setListening] = useState(false)
  const [quickNote, setQuickNote] = useState('')
  const [quickDeal, setQuickDeal] = useState({ deal_amount: '', policy_type: '', next_time: null })
  const [pendingQuick, setPendingQuick] = useState(null)
  const [strategy, setStrategy] = useState(null)
  const [analyzing, setAnalyzing] = useState(false)
  const [assistantRunning, setAssistantRunning] = useState(false)
  const recognitionRef = useRef(null)

  const [reminders, setReminders] = useState([])
  const [reminderLoading, setReminderLoading] = useState(false)
  const [reminderFilter, setReminderFilter] = useState({ status: 'pending', due: '' })

  const loadData = useCallback((p = page, f = filters) => {
    setLoading(true)
    customersApi.list({ page: p, pageSize: 15, ...f })
      .then(res => { setData(res); setPage(p) })
      .finally(() => setLoading(false))
  }, [page, filters])

  const loadOwners = () => {
    customersApi.owners().then(res => setOwners(res.list || [])).catch(() => {})
  }

  const loadReminders = useCallback((f = reminderFilter) => {
    setReminderLoading(true)
    const params = { status: f.status || 'pending' }
    if (f.due) params.due = f.due
    if (f.owner) params.owner = f.owner
    remindersApi.list(params)
      .then(res => setReminders(res.list || []))
      .finally(() => setReminderLoading(false))
  }, [reminderFilter])

  useEffect(() => {
    loadData(1)
    loadOwners()
    loadReminders()
  }, [])

  // 支持 /customers?tab=reminders 深链
  useEffect(() => {
    const tab = searchParams.get('tab')
    if (tab === 'reminders' && activeTab !== 'reminders') {
      setActiveTab('reminders')
      loadReminders()
    }
  }, [searchParams])

  // 提醒中心：每 60s 刷新一次待办
  useEffect(() => {
    const timer = setInterval(() => {
      if (activeTab === 'reminders' || document.visibilityState === 'visible') {
        loadReminders()
      }
    }, 60000)
    return () => clearInterval(timer)
  }, [activeTab, loadReminders])

  const handleSearch = () => loadData(1, filters)

  const handleStageFilter = (stage) => {
    const next = { ...filters, lifecycle: filters.lifecycle === stage ? undefined : stage }
    setFilters(next)
    loadData(1, next)
  }

  const handleSave = () => {
    form.validateFields().then(values => {
      const payload = { ...values }
      if (payload.birthday) payload.birthday = payload.birthday.format('YYYY-MM-DD')
      if (payload.policy_expiry_date) payload.policy_expiry_date = payload.policy_expiry_date.format('YYYY-MM-DD')
      if (payload.age === undefined || payload.age === null) delete payload.age

      const req = editing
        ? customersApi.update(editing.id, payload)
        : customersApi.create(payload)
      req.then((res) => {
        if (editing) {
          message.success('已更新')
        } else {
          showAssistantTip(res?.assistant, '客户已添加')
        }
        setEditModal(false)
        loadData(editing ? page : 1)
        loadOwners()
        if (!editing && res?.id) {
          handleView({ id: res.id })
        }
      })
    })
  }

  const openEdit = (record = null) => {
    setEditing(record)
    form.resetFields()
    if (record) {
      form.setFieldsValue({
        ...record,
        birthday: record.birthday ? dayjs(record.birthday) : null,
        policy_expiry_date: record.policy_expiry_date ? dayjs(record.policy_expiry_date) : null,
      })
    } else {
      form.setFieldsValue({ intention: 'low', lifecycle_stage: 'new' })
    }
    setEditModal(true)
  }

  const handleView = (record) => {
    setViewing(record)
    setStrategy(null)
    setDetailDrawer(true)
    customersApi.get(record.id).then(res => {
      setViewing(res)
      if (res.personality_type) {
        customersApi.strategy(res.id).then(setStrategy).catch(() => {})
      }
    })
  }

  // 工作流看板「客户详情」深链：/customers?id=123 或 ?focus=123
  useEffect(() => {
    const id = searchParams.get('id') || searchParams.get('focus')
    if (!id) return
    handleView({ id: Number(id) })
    setSearchParams({}, { replace: true })
  }, [searchParams])

  const openFollow = (customer) => {
    setCurrentCustomerId(customer.id)
    setViewing(customer)
    setFollowResult('')
    setFollowTab('smart')
    setSmartText('')
    setQuickNote('')
    setPendingQuick(null)
    setQuickDeal({ deal_amount: '', policy_type: '', next_time: null })
    followForm.resetFields()
    followForm.setFieldsValue({
      operator: customer.owner || customer.assigned_agent || '',
      follow_stage: customer.lifecycle_stage || 'new',
      method: 'wechat',
    })
    setFollowModal(true)
  }

  const afterFollowSaved = (res) => {
    showAssistantTip(
      res?.assistant,
      res?.stage_label ? `跟进已记录，阶段：${res.stage_label}` : '跟进记录已添加',
    )
    setFollowModal(false)
    stopListening()
    if (detailDrawer && currentCustomerId) handleView({ id: currentCustomerId })
    loadData()
    loadReminders()
  }

  const handleAddFollow = () => {
    followForm.validateFields().then(values => {
      const payload = {
        ...values,
        customer_id: currentCustomerId,
        follow_result: values.follow_result === 'general' ? '' : values.follow_result,
      }
      if (payload.next_time) payload.next_time = payload.next_time.format('YYYY-MM-DD HH:mm:ss')
      followsApi.create(payload).then(afterFollowSaved)
    })
  }

  const handleSmartParse = () => {
    if (!smartText.trim()) {
      message.warning('请粘贴微信记录，或口述一句话')
      return
    }
    setSmartParsing(true)
    followsApi.smartParse({
      text: smartText,
      customer_id: currentCustomerId,
      operator: viewing?.owner || '',
    })
      .then(parsed => {
        setFollowTab('manual')
        setFollowResult(parsed.follow_result || 'general')
        followForm.setFieldsValue({
          content: parsed.content,
          follow_result: parsed.follow_result || 'general',
          method: parsed.method || 'wechat',
          operator: parsed.operator || viewing?.owner || viewing?.assigned_agent || '',
          deal_amount: parsed.deal_amount || undefined,
          policy_type: parsed.policy_type || undefined,
          next_time: parsed.next_time ? dayjs(parsed.next_time) : null,
        })
        message.success(`AI 已填好表单（置信度 ${parsed.confidence || '-'}%），确认后点确定保存`)
      })
      .catch(err => message.error(err?.error || '解析失败，请检查 AI 配置'))
      .finally(() => setSmartParsing(false))
  }

  const handleSmartSaveDirect = () => {
    if (!smartText.trim()) {
      message.warning('请先输入内容')
      return
    }
    setSmartParsing(true)
    followsApi.smart({
      text: smartText,
      customer_id: currentCustomerId,
      operator: viewing?.owner || viewing?.assigned_agent || '',
    })
      .then(afterFollowSaved)
      .catch(err => message.error(err?.error || '保存失败'))
      .finally(() => setSmartParsing(false))
  }

  const stopListening = () => {
    try { recognitionRef.current?.stop() } catch {}
    setListening(false)
  }

  const toggleVoice = () => {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition
    if (!SpeechRecognition) {
      message.warning('当前浏览器不支持语音输入，请用 Chrome，或直接粘贴/打字')
      return
    }
    if (listening) {
      stopListening()
      return
    }
    const recog = new SpeechRecognition()
    recognitionRef.current = recog
    recog.lang = 'zh-CN'
    recog.continuous = true
    recog.interimResults = true
    recog.onresult = (event) => {
      let finalText = ''
      for (let i = event.resultIndex; i < event.results.length; i++) {
        if (event.results[i].isFinal) finalText += event.results[i][0].transcript
      }
      if (finalText) setSmartText(prev => (prev ? `${prev}\n` : '') + finalText)
    }
    recog.onerror = () => setListening(false)
    recog.onend = () => setListening(false)
    recog.start()
    setListening(true)
    message.info('正在听写…说完再点一次停止')
  }

  const handleQuick = (tpl) => {
    if (tpl.need_next_time || tpl.need_deal) {
      setPendingQuick(tpl)
      return
    }
    followsApi.quick({
      customer_id: currentCustomerId,
      template: tpl.key,
      operator: viewing?.owner || viewing?.assigned_agent || '',
      note: quickNote,
    }).then(afterFollowSaved).catch(err => message.error(err?.error || '快捷跟进失败'))
  }

  const confirmPendingQuick = () => {
    if (!pendingQuick) return
    const payload = {
      customer_id: currentCustomerId,
      template: pendingQuick.key,
      operator: viewing?.owner || viewing?.assigned_agent || '',
      note: quickNote,
      deal_amount: quickDeal.deal_amount,
      policy_type: quickDeal.policy_type,
    }
    if (quickDeal.next_time) {
      payload.next_time = quickDeal.next_time.format('YYYY-MM-DD HH:mm:ss')
    }
    followsApi.quick(payload)
      .then(res => { setPendingQuick(null); afterFollowSaved(res) })
      .catch(err => message.error(err?.error || '快捷跟进失败'))
  }

  const handleAnalyze = () => {
    if (!viewing?.id) return
    setAnalyzing(true)
    customersApi.analyze(viewing.id)
      .then(res => {
        message.success('AI 分析完成')
        handleView(viewing)
        if (res.analysis?.personality_strategy) {
          customersApi.strategy(viewing.id).then(setStrategy).catch(() => {})
        }
      })
      .catch(err => message.error(err?.error || '分析失败，请检查 AI 配置'))
      .finally(() => setAnalyzing(false))
  }

  const handleRunAssistant = () => {
    if (!viewing?.id) return
    setAssistantRunning(true)
    customersApi.runAssistant(viewing.id)
      .then(res => {
        showAssistantTip(res, '助手已更新')
        handleView(viewing)
      })
      .catch(err => message.error(err?.error || '助手分析失败'))
      .finally(() => setAssistantRunning(false))
  }

  const handleAutoRemind = (id) => {
    customersApi.autoRemind(id).then(res => {
      message.success(res.message || `生成 ${res.count} 条提醒`)
      loadReminders()
      if (viewing?.id === id) handleView(viewing)
    })
  }

  const handleScanReminders = () => {
    remindersApi.scan().then(res => {
      message.success(res.message)
      loadReminders()
    })
  }

  const completeReminder = (id) => {
    remindersApi.update(id, { status: 'done' }).then(() => {
      message.success('已完成')
      loadReminders()
      if (viewing) handleView(viewing)
    })
  }

  const snoozeReminder = (id, days = 1) => {
    remindersApi.update(id, { snooze_days: days }).then(() => {
      message.success(`已延期 ${days} 天`)
      loadReminders()
    })
  }

  const setStage = (id, stage) => {
    customersApi.setLifecycle(id, { stage }).then(res => {
      message.success(res.message)
      loadData()
      if (viewing?.id === id) handleView(viewing)
    })
  }

  const pendingCount = reminders.filter(r => r.status === 'pending').length
  const overdueCount = reminders.filter(r =>
    r.status === 'pending' && r.remind_date && dayjs(r.remind_date).isBefore(dayjs(), 'day')
  ).length

  const columns = [
    { title: '客户', dataIndex: 'nickname', width: 110, fixed: 'left',
      render: (v, r) => (
        <div>
          <a onClick={() => handleView(r)}>{v}</a>
          {r.phone && <div style={{ fontSize: 12, color: '#999' }}>{r.phone}</div>}
        </div>
      ) },
    {
      title: '阶段', dataIndex: 'lifecycle_stage', width: 100,
      render: v => {
        const s = STAGE_MAP[v] || STAGE_MAP.new
        return <Tag color={s.color}>{s.label}</Tag>
      },
    },
    {
      title: '责任人', dataIndex: 'owner', width: 90,
      render: (v, r) => v || r.assigned_agent || <span style={{ color: '#ccc' }}>未指定</span>,
    },
    {
      title: '性格', dataIndex: 'personality_type', width: 80,
      render: v => v ? <Tag>{PERSONALITY_MAP[v] || v}</Tag> : '-',
    },
    {
      title: '意向', dataIndex: 'intention', width: 80,
      render: v => <Tag color={INTENTION_COLORS[v]}>{INTENTION_LABELS[v] || v}</Tag>,
    },
    { title: '微信', dataIndex: 'wechat', width: 110, ellipsis: true },
    {
      title: '最后跟进', dataIndex: 'last_follow_time', width: 160,
      render: v => (v ? formatDateTime(v) : <span style={{ color: '#ff4d4f' }}>未跟进</span>),
    },
    {
      title: '操作', key: 'action', width: 200, fixed: 'right',
      render: (_, r) => (
        <Space size="small">
          <Tooltip title="详情"><Button size="small" icon={<EyeOutlined />} onClick={() => handleView(r)} /></Tooltip>
          <Tooltip title="跟进"><Button size="small" type="primary" ghost icon={<MessageOutlined />} onClick={() => openFollow(r)} /></Tooltip>
          <Tooltip title="编辑"><Button size="small" icon={<EditOutlined />} onClick={() => openEdit(r)} /></Tooltip>
          <Popconfirm title="确认删除？" onConfirm={() => {
            customersApi.delete(r.id).then(() => { message.success('已删除'); loadData() })
          }}>
            <Button size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ]

  const reminderColumns = [
    {
      title: '优先级', dataIndex: 'priority', width: 80,
      render: v => <Tag color={PRIORITY_COLORS[v] || 'blue'}>{PRIORITY_LABELS[v] || v}</Tag>,
    },
    {
      title: '提醒', dataIndex: 'title',
      render: (v, r) => (
        <div>
          <div style={{ fontWeight: 600 }}>{v}</div>
          <div style={{ fontSize: 12, color: '#666' }}>{r.content}</div>
          {r.suggested_action && (
            <div style={{ fontSize: 12, color: '#5b5bd6', marginTop: 4 }}>建议：{r.suggested_action}</div>
          )}
        </div>
      ),
    },
    {
      title: '客户', dataIndex: 'customer_name', width: 100,
      render: (v, r) => (
        <a onClick={() => r.customer_id && handleView({ id: r.customer_id, nickname: v })}>{v}</a>
      ),
    },
    {
      title: '责任人', dataIndex: 'owner', width: 90,
      render: v => v || '-',
    },
    {
      title: '阶段', dataIndex: 'lifecycle_stage', width: 90,
      render: v => {
        const s = STAGE_MAP[v]
        return s ? <Tag color={s.color}>{s.label}</Tag> : '-'
      },
    },
    {
      title: '日期', dataIndex: 'remind_date', width: 120,
      render: v => {
        if (!v) return '-'
        const overdue = dayjs(v).isBefore(dayjs(), 'day')
        return <span style={{ color: overdue ? '#ff4d4f' : undefined }}>{formatDate(v)}</span>
      },
    },
    {
      title: '操作', width: 180,
      render: (_, r) => r.status === 'pending' ? (
        <Space size="small">
          <Button size="small" type="primary" icon={<CheckOutlined />} onClick={() => completeReminder(r.id)}>完成</Button>
          <Button size="small" icon={<ClockCircleOutlined />} onClick={() => snoozeReminder(r.id, 1)}>延期1天</Button>
          <Button size="small" onClick={() => openFollow({
            id: r.customer_id, nickname: r.customer_name, owner: r.owner,
            lifecycle_stage: r.lifecycle_stage,
          })}>跟进</Button>
        </Space>
      ) : <Tag>已完成</Tag>,
    },
  ]

  return (
    <div>
      <div className="page-title">客户管理</div>
      <div className="page-desc">
        工作流：新增 → 约访 → 跟踪 → 方案 → 成交 → 售后；谁谈的谁约谁负责，按客户性格实时提醒跟进
      </div>

      {/* 生命周期漏斗 */}
      <Row gutter={10} style={{ marginBottom: 16 }}>
        {STAGE_OPTIONS.map(s => {
          const count = data.stageStats?.[s.value] || 0
          const active = filters.lifecycle === s.value
          return (
            <Col key={s.value} flex="1">
              <Card
                size="small"
                hoverable
                onClick={() => handleStageFilter(s.value)}
                style={{
                  borderColor: active ? '#5b5bd6' : undefined,
                  background: active ? '#f0f3ff' : undefined,
                  cursor: 'pointer',
                  textAlign: 'center',
                }}
              >
                <Statistic title={s.label} value={count} valueStyle={{ fontSize: 22 }} />
              </Card>
            </Col>
          )
        })}
        <Col flex="1">
          <Card size="small" style={{ textAlign: 'center' }}>
            <Statistic
              title={<span><BellOutlined /> 待办提醒</span>}
              value={pendingCount}
              valueStyle={{ fontSize: 22, color: overdueCount ? '#ff4d4f' : '#5b5bd6' }}
              suffix={overdueCount ? <span style={{ fontSize: 12, color: '#ff4d4f' }}>({overdueCount}逾期)</span> : null}
            />
          </Card>
        </Col>
      </Row>

      <Tabs
        activeKey={activeTab}
        onChange={(k) => {
          setActiveTab(k)
          if (k === 'reminders') {
            setSearchParams({ tab: 'reminders' })
            loadReminders()
          } else {
            setSearchParams({})
          }
        }}
        items={[
          {
            key: 'list',
            label: <span><TeamOutlined /> 客户列表</span>,
            children: (
              <>
                <div className="table-toolbar">
                  <div className="table-toolbar-left">
                    <Select
                      placeholder="意向"
                      allowClear
                      style={{ width: 110 }}
                      value={filters.intention}
                      onChange={v => setFilters({ ...filters, intention: v })}
                      options={INTENTION_OPTIONS}
                    />
                    <Select
                      placeholder="责任人"
                      allowClear
                      showSearch
                      style={{ width: 130 }}
                      value={filters.owner}
                      onChange={v => setFilters({ ...filters, owner: v })}
                      options={owners.map(o => ({ value: o, label: o }))}
                    />
                    <Input
                      placeholder="搜索昵称/微信/电话/标签"
                      allowClear
                      style={{ width: 220 }}
                      value={filters.q}
                      onChange={e => setFilters({ ...filters, q: e.target.value })}
                      onPressEnter={handleSearch}
                    />
                    <Button type="primary" icon={<SearchOutlined />} onClick={handleSearch}>搜索</Button>
                    <Button icon={<ReloadOutlined />} onClick={() => { setFilters({}); loadData(1, {}) }}>重置</Button>
                  </div>
                  <Button type="primary" icon={<PlusOutlined />} onClick={() => openEdit()}>添加客户</Button>
                </div>

                <Table
                  columns={columns}
                  dataSource={data.list}
                  rowKey="id"
                  loading={loading}
                  scroll={{ x: 1100 }}
                  pagination={{
                    current: page, total: data.total, pageSize: 15,
                    onChange: (p) => loadData(p),
                    showTotal: (t) => `共 ${t} 条`,
                  }}
                  size="middle"
                />
              </>
            ),
          },
          {
            key: 'reminders',
            label: (
              <span>
                <BellOutlined /> 提醒中心{' '}
                {pendingCount > 0 && <Badge count={pendingCount} style={{ marginLeft: 4 }} />}
              </span>
            ),
            children: (
              <>
                {overdueCount > 0 && (
                  <Alert
                    type="error"
                    showIcon
                    style={{ marginBottom: 12 }}
                    message={`有 ${overdueCount} 条逾期提醒，请尽快跟进（谁负责谁处理）`}
                  />
                )}
                <div className="table-toolbar">
                  <div className="table-toolbar-left">
                    <Select
                      style={{ width: 120 }}
                      value={reminderFilter.status}
                      onChange={v => {
                        const next = { ...reminderFilter, status: v }
                        setReminderFilter(next)
                        loadReminders(next)
                      }}
                      options={[
                        { value: 'pending', label: '待处理' },
                        { value: 'done', label: '已完成' },
                      ]}
                    />
                    <Select
                      allowClear
                      placeholder="到期筛选"
                      style={{ width: 130 }}
                      value={reminderFilter.due || undefined}
                      onChange={v => {
                        const next = { ...reminderFilter, due: v }
                        setReminderFilter(next)
                        loadReminders(next)
                      }}
                      options={[
                        { value: 'overdue', label: '已逾期' },
                        { value: 'today', label: '今天' },
                        { value: 'upcoming', label: '近7天' },
                      ]}
                    />
                    <Select
                      allowClear
                      showSearch
                      placeholder="责任人"
                      style={{ width: 130 }}
                      value={reminderFilter.owner}
                      onChange={v => {
                        const next = { ...reminderFilter, owner: v }
                        setReminderFilter(next)
                        loadReminders(next)
                      }}
                      options={owners.map(o => ({ value: o, label: o }))}
                    />
                    <Button icon={<ReloadOutlined />} onClick={() => loadReminders()}>刷新</Button>
                  </div>
                  <Button type="primary" icon={<ThunderboltOutlined />} onClick={handleScanReminders}>
                    扫描全部客户生成提醒
                  </Button>
                </div>
                <Table
                  columns={reminderColumns}
                  dataSource={reminders}
                  rowKey="id"
                  loading={reminderLoading}
                  pagination={{ pageSize: 20, showTotal: t => `共 ${t} 条` }}
                  size="middle"
                  locale={{ emptyText: <Empty description="暂无提醒，可点击「扫描」生成" /> }}
                />
              </>
            ),
          },
        ]}
      />

      {/* 添加/编辑客户 */}
      <Modal
        title={editing ? '编辑客户' : '添加客户'}
        open={editModal}
        onOk={handleSave}
        onCancel={() => setEditModal(false)}
        width={720}
        destroyOnClose
      >
        <Form form={form} layout="vertical" style={{ marginTop: 8 }}>
          <Tabs
            items={[
              {
                key: 'basic',
                label: '基本信息',
                children: (
                  <>
                    <Row gutter={16}>
                      <Col span={8}>
                        <Form.Item name="nickname" label="昵称/姓名" rules={[{ required: true }]}>
                          <Input />
                        </Form.Item>
                      </Col>
                      <Col span={8}>
                        <Form.Item name="wechat" label="微信"><Input /></Form.Item>
                      </Col>
                      <Col span={8}>
                        <Form.Item name="phone" label="电话"><Input /></Form.Item>
                      </Col>
                    </Row>
                    <Row gutter={16}>
                      <Col span={8}>
                        <Form.Item name="intention" label="意向">
                          <Select options={INTENTION_OPTIONS} />
                        </Form.Item>
                      </Col>
                      <Col span={8}>
                        <Form.Item name="lifecycle_stage" label="当前阶段">
                          <Select options={STAGE_OPTIONS} />
                        </Form.Item>
                      </Col>
                      <Col span={8}>
                        <Form.Item name="source_channel" label="来源渠道"><Input placeholder="视频号/转介绍/…" /></Form.Item>
                      </Col>
                    </Row>
                    <Row gutter={16}>
                      <Col span={12}>
                        <Form.Item name="source_video" label="来源视频"><Input /></Form.Item>
                      </Col>
                      <Col span={12}>
                        <Form.Item name="tags" label="标签（逗号分隔）"><Input placeholder="高意向,咨询重疾" /></Form.Item>
                      </Col>
                    </Row>
                    <Form.Item name="remark" label="备注"><Input.TextArea rows={2} /></Form.Item>
                  </>
                ),
              },
              {
                key: 'owner',
                label: '责任人与画像',
                children: (
                  <>
                    <Alert
                      type="info"
                      showIcon
                      style={{ marginBottom: 12 }}
                      message="谁谈的谁约谁负责：填写责任人后，提醒会归属到该人"
                    />
                    <Row gutter={16}>
                      <Col span={8}>
                        <Form.Item name="owner" label="责任人（主跟）" rules={[{ required: !editing }]}>
                          <Input placeholder="姓名" prefix={<UserOutlined />} />
                        </Form.Item>
                      </Col>
                      <Col span={8}>
                        <Form.Item name="assigned_agent" label="约访/协助人">
                          <Input placeholder="可与责任人相同" />
                        </Form.Item>
                      </Col>
                      <Col span={8}>
                        <Form.Item name="personality_type" label="客户性格">
                          <Select allowClear options={PERSONALITY_OPTIONS} placeholder="用于售后话术" />
                        </Form.Item>
                      </Col>
                    </Row>
                    <Row gutter={16}>
                      <Col span={6}>
                        <Form.Item name="age" label="年龄"><Input type="number" /></Form.Item>
                      </Col>
                      <Col span={6}>
                        <Form.Item name="occupation" label="职业"><Input /></Form.Item>
                      </Col>
                      <Col span={6}>
                        <Form.Item name="income" label="收入"><Input /></Form.Item>
                      </Col>
                      <Col span={6}>
                        <Form.Item name="region" label="地区"><Input /></Form.Item>
                      </Col>
                    </Row>
                    <Row gutter={16}>
                      <Col span={8}>
                        <Form.Item name="risk_preference" label="风险偏好"><Input /></Form.Item>
                      </Col>
                      <Col span={8}>
                        <Form.Item name="insurance_needs" label="保险需求"><Input /></Form.Item>
                      </Col>
                      <Col span={8}>
                        <Form.Item name="birthday" label="生日">
                          <DatePicker style={{ width: '100%' }} />
                        </Form.Item>
                      </Col>
                    </Row>
                    <Form.Item name="family_info" label="家庭情况"><Input.TextArea rows={2} /></Form.Item>
                  </>
                ),
              },
              {
                key: 'deal',
                label: '成交/保单',
                children: (
                  <Row gutter={16}>
                    <Col span={8}>
                      <Form.Item name="deal_amount" label="成交金额"><Input placeholder="元" /></Form.Item>
                    </Col>
                    <Col span={8}>
                      <Form.Item name="policy_type" label="产品/险种"><Input /></Form.Item>
                    </Col>
                    <Col span={8}>
                      <Form.Item name="policy_expiry_date" label="保单到期日">
                        <DatePicker style={{ width: '100%' }} />
                      </Form.Item>
                    </Col>
                    <Col span={24}>
                      <Form.Item name="existing_policies" label="已有保单"><Input.TextArea rows={2} /></Form.Item>
                    </Col>
                  </Row>
                ),
              },
            ]}
          />
        </Form>
      </Modal>

      {/* 跟进：智能录入 / 一键快捷 / 手动 */}
      <Modal
        title="记录跟进"
        open={followModal}
        onCancel={() => { stopListening(); setFollowModal(false) }}
        width={640}
        destroyOnClose
        footer={
          followTab === 'manual' ? (
            <Space>
              <Button onClick={() => { stopListening(); setFollowModal(false) }}>取消</Button>
              <Button type="primary" onClick={handleAddFollow}>保存跟进</Button>
            </Space>
          ) : followTab === 'smart' ? (
            <Space>
              <Button onClick={() => { stopListening(); setFollowModal(false) }}>取消</Button>
              <Button loading={smartParsing} onClick={handleSmartParse}>AI 解析填表</Button>
              <Button type="primary" loading={smartParsing} onClick={handleSmartSaveDirect}>一键解析并保存</Button>
            </Space>
          ) : (
            <Button onClick={() => { stopListening(); setFollowModal(false) }}>关闭</Button>
          )
        }
      >
        {viewing && (
          <div style={{ marginBottom: 12, color: '#666' }}>
            客户：<strong>{viewing.nickname}</strong>
            {viewing.lifecycle_stage && (
              <Tag color={STAGE_MAP[viewing.lifecycle_stage]?.color} style={{ marginLeft: 8 }}>
                {STAGE_MAP[viewing.lifecycle_stage]?.label}
              </Tag>
            )}
            <span style={{ marginLeft: 8, fontSize: 12, color: '#999' }}>
              责任人：{viewing.owner || viewing.assigned_agent || '未指定'}
            </span>
          </div>
        )}

        <Tabs
          activeKey={followTab}
          onChange={setFollowTab}
          items={[
            {
              key: 'smart',
              label: <span><RobotOutlined /> 智能录入</span>,
              children: (
                <>
                  <Alert
                    type="info"
                    showIcon
                    style={{ marginBottom: 12 }}
                    message="粘贴微信聊天 / 通话摘要 / 面谈笔记，或点麦克风口述一句话，AI 自动整理成跟进"
                  />
                  <Input.TextArea
                    rows={8}
                    value={smartText}
                    onChange={e => setSmartText(e.target.value)}
                    placeholder={`示例：\n张三：李强约好了明天上午10点茶叙面谈保障\n或直接说：刚给周阿姨打电话没接上\n或粘贴整段微信记录…`}
                  />
                  <Space style={{ marginTop: 12 }}>
                    <Button
                      icon={<AudioOutlined />}
                      type={listening ? 'primary' : 'default'}
                      danger={listening}
                      onClick={toggleVoice}
                    >
                      {listening ? '停止听写' : '语音口述'}
                    </Button>
                    <span style={{ fontSize: 12, color: '#999' }}>推荐 Chrome；说完记得点停止</span>
                  </Space>
                </>
              ),
            },
            {
              key: 'quick',
              label: <span><ThunderboltOutlined /> 一键快捷</span>,
              children: (
                <>
                  <Alert
                    type="success"
                    showIcon
                    style={{ marginBottom: 12 }}
                    message="打完电话 / 发完微信，点一下对应按钮即可入库，不用填表"
                  />
                  <Input.TextArea
                    rows={2}
                    value={quickNote}
                    onChange={e => setQuickNote(e.target.value)}
                    placeholder="可选：补充一句备注（如「约了周六下午」）"
                    style={{ marginBottom: 12 }}
                  />
                  <Space wrap>
                    {[
                      { key: 'no_answer', label: '未接通', need_next_time: false },
                      { key: 'wechat_left', label: '微信留言' },
                      { key: 'appointment', label: '已约访', need_next_time: true },
                      { key: 'interested', label: '有兴趣' },
                      { key: 'proposal', label: '已发方案' },
                      { key: 'offline_done', label: '面谈结束' },
                      { key: 'deal', label: '已成交', need_deal: true },
                      { key: 'policy', label: '保单送达' },
                    ].map(tpl => (
                      <Button key={tpl.key} type="primary" ghost onClick={() => handleQuick(tpl)}>
                        {tpl.label}
                      </Button>
                    ))}
                  </Space>
                </>
              ),
            },
            {
              key: 'manual',
              label: '手动填报',
              children: (
                <Form form={followForm} layout="vertical">
                  <Form.Item name="content" label="跟进内容" rules={[{ required: true }]}>
                    <Input.TextArea rows={3} placeholder="沟通要点、客户反馈…" />
                  </Form.Item>
                  <Row gutter={12}>
                    <Col span={12}>
                      <Form.Item name="follow_result" label="跟进结果（推动阶段）" rules={[{ required: true }]}>
                        <Select
                          options={FOLLOW_RESULTS}
                          onChange={setFollowResult}
                          placeholder="选择结果自动推进阶段"
                        />
                      </Form.Item>
                    </Col>
                    <Col span={12}>
                      <Form.Item name="operator" label="本次跟进人" rules={[{ required: true, message: '谁谈的谁负责' }]}>
                        <Input placeholder="姓名" />
                      </Form.Item>
                    </Col>
                  </Row>
                  <Row gutter={12}>
                    <Col span={12}>
                      <Form.Item name="method" label="沟通方式">
                        <Select options={METHOD_OPTIONS} />
                      </Form.Item>
                    </Col>
                    <Col span={12}>
                      <Form.Item name="next_time" label="下次跟进时间">
                        <DatePicker showTime style={{ width: '100%' }} format="YYYY-MM-DD HH:mm" />
                      </Form.Item>
                    </Col>
                  </Row>
                  {(followResult === 'deal_closed') && (
                    <Row gutter={12}>
                      <Col span={12}>
                        <Form.Item name="deal_amount" label="成交金额">
                          <Input placeholder="元" />
                        </Form.Item>
                      </Col>
                      <Col span={12}>
                        <Form.Item name="policy_type" label="产品/险种">
                          <Input />
                        </Form.Item>
                      </Col>
                    </Row>
                  )}
                  <Form.Item name="follow_stage" hidden><Input /></Form.Item>
                </Form>
              ),
            },
          ]}
        />
      </Modal>

      {/* 快捷跟进补充信息 */}
      <Modal
        title={pendingQuick ? `补充信息 · ${pendingQuick.label}` : '补充信息'}
        open={!!pendingQuick}
        onOk={confirmPendingQuick}
        onCancel={() => setPendingQuick(null)}
        okText="确认保存"
      >
        {pendingQuick?.need_next_time && (
          <div style={{ marginBottom: 12 }}>
            <div style={{ marginBottom: 6 }}>约访/下次时间</div>
            <DatePicker
              showTime
              style={{ width: '100%' }}
              format="YYYY-MM-DD HH:mm"
              value={quickDeal.next_time}
              onChange={v => setQuickDeal({ ...quickDeal, next_time: v })}
            />
          </div>
        )}
        {pendingQuick?.need_deal && (
          <Row gutter={12}>
            <Col span={12}>
              <div style={{ marginBottom: 6 }}>成交金额</div>
              <Input
                value={quickDeal.deal_amount}
                onChange={e => setQuickDeal({ ...quickDeal, deal_amount: e.target.value })}
                placeholder="元"
              />
            </Col>
            <Col span={12}>
              <div style={{ marginBottom: 6 }}>产品/险种</div>
              <Input
                value={quickDeal.policy_type}
                onChange={e => setQuickDeal({ ...quickDeal, policy_type: e.target.value })}
              />
            </Col>
          </Row>
        )}
      </Modal>

      {/* 详情 */}
      <Drawer
        title={viewing ? `${viewing.nickname || '客户'} · 详情` : '客户详情'}
        open={detailDrawer}
        onClose={() => setDetailDrawer(false)}
        width={680}
        extra={
          viewing && (
            <Space>
              <Button size="small" icon={<MessageOutlined />} onClick={() => openFollow(viewing)}>跟进</Button>
              <Button size="small" icon={<BellOutlined />} onClick={() => handleAutoRemind(viewing.id)}>生成提醒</Button>
              <Button size="small" icon={<ThunderboltOutlined />} loading={assistantRunning} onClick={handleRunAssistant}>
                客户管理助手
              </Button>
              <Button size="small" type="primary" ghost icon={<RobotOutlined />} loading={analyzing} onClick={handleAnalyze}>
                AI分析
              </Button>
            </Space>
          )
        }
      >
        {viewing && (
          <div>
            {/* 阶段进度 */}
            <Card size="small" title="生命周期" style={{ marginBottom: 12 }}>
              <Space wrap>
                {STAGE_OPTIONS.map((s, idx) => {
                  const cur = STAGE_OPTIONS.findIndex(x => x.value === (viewing.lifecycle_stage || 'new'))
                  const done = idx <= cur
                  return (
                    <Tag
                      key={s.value}
                      color={done ? s.color : undefined}
                      style={{ cursor: 'pointer', opacity: done ? 1 : 0.45 }}
                      onClick={() => setStage(viewing.id, s.value)}
                    >
                      {idx + 1}. {s.label}
                    </Tag>
                  )
                })}
              </Space>
              <div style={{ marginTop: 8, fontSize: 12, color: '#999' }}>点击标签可手动调整阶段</div>
            </Card>

            <Descriptions size="small" bordered column={2} style={{ marginBottom: 12 }}>
              <Descriptions.Item label="责任人">{viewing.owner || '-'}</Descriptions.Item>
              <Descriptions.Item label="约访/协助">{viewing.assigned_agent || '-'}</Descriptions.Item>
              <Descriptions.Item label="性格">
                {PERSONALITY_MAP[viewing.personality_type] || viewing.personality_type || '未设置'}
              </Descriptions.Item>
              <Descriptions.Item label="意向">
                <Tag color={INTENTION_COLORS[viewing.intention]}>{INTENTION_LABELS[viewing.intention]}</Tag>
              </Descriptions.Item>
              <Descriptions.Item label="微信">{viewing.wechat || '-'}</Descriptions.Item>
              <Descriptions.Item label="电话">{viewing.phone || '-'}</Descriptions.Item>
              <Descriptions.Item label="成交日">{viewing.deal_date || '-'}</Descriptions.Item>
              <Descriptions.Item label="成交金额">{viewing.deal_amount || '-'}</Descriptions.Item>
              <Descriptions.Item label="备注" span={2}>{viewing.remark || '-'}</Descriptions.Item>
            </Descriptions>

            {/* 客户助手下一步 */}
            {(() => {
              const tip = parseAssistantPayload(viewing.ai_analysis)
              if (!tip) {
                return (
                  <Alert
                    type="info"
                    showIcon
                    style={{ marginBottom: 12 }}
                    message="客户管理助手尚未分析"
                    description="新增客户或保存跟进后会自动给出下一步；也可点右上角「助手再分析」。"
                  />
                )
              }
              return (
                <Card
                  size="small"
                  title={<Space><ThunderboltOutlined style={{ color: '#5b5bd6' }} />客户管理助手 · 下一步</Space>}
                  style={{ marginBottom: 12, borderColor: '#c5cbff' }}
                  extra={
                    <Button type="link" size="small" loading={assistantRunning} onClick={handleRunAssistant}>
                      刷新
                    </Button>
                  }
                >
                  {tip.summary ? <div style={{ marginBottom: 8, color: '#666' }}>{tip.summary}</div> : null}
                  {(tip.next_actions || []).length > 0 ? (
                    <ol style={{ margin: '0 0 8px', paddingLeft: 18 }}>
                      {tip.next_actions.map((a, i) => <li key={i}>{a}</li>)}
                    </ol>
                  ) : tip.next_step ? (
                    <div style={{ marginBottom: 8 }}>{tip.next_step}</div>
                  ) : null}
                  {(tip.best_time || tip.talk_tips) && (
                    <div style={{ fontSize: 12, color: '#888' }}>
                      {tip.best_time ? `建议联系：${tip.best_time}` : ''}
                      {tip.best_time && tip.talk_tips ? ' · ' : ''}
                      {tip.talk_tips ? `话术：${tip.talk_tips}` : ''}
                    </div>
                  )}
                </Card>
              )
            })()}

            {/* 性格策略 */}
            {strategy && (
              <Card size="small" title={`性格策略 · ${strategy.label || ''}`} style={{ marginBottom: 12 }}>
                <p style={{ marginBottom: 8 }}>{strategy.approach}</p>
                <Row gutter={12}>
                  <Col span={12}>
                    <div style={{ fontWeight: 600, color: '#52c41a' }}>建议做</div>
                    <ul style={{ paddingLeft: 18, margin: '4px 0' }}>
                      {(strategy.do || []).map((x, i) => <li key={i}>{x}</li>)}
                    </ul>
                  </Col>
                  <Col span={12}>
                    <div style={{ fontWeight: 600, color: '#ff4d4f' }}>避免</div>
                    <ul style={{ paddingLeft: 18, margin: '4px 0' }}>
                      {(strategy.dont || []).map((x, i) => <li key={i}>{x}</li>)}
                    </ul>
                  </Col>
                </Row>
                <Divider style={{ margin: '8px 0' }} />
                <div style={{ fontSize: 12, color: '#666' }}>
                  最佳联系：{strategy.best_time || '-'} · 跟进频率：{strategy.follow_up_freq || '-'}
                </div>
              </Card>
            )}

            {/* AI 分析 */}
            {viewing.ai_analysis && (
              <Card size="small" title="AI 分析" style={{ marginBottom: 12 }}>
                <Progress
                  percent={Number(viewing.ai_analysis.deal_probability) || 0}
                  size="small"
                  format={p => `成交概率 ${p}%`}
                  style={{ marginBottom: 8 }}
                />
                <p><strong>关注点：</strong>{viewing.ai_analysis.focus_points}</p>
                <p><strong>风险：</strong>{viewing.ai_analysis.risk_assessment}</p>
                <p><strong>推荐产品：</strong>{viewing.ai_analysis.recommended_products}</p>
                <p><strong>下一步：</strong>{viewing.ai_analysis.next_step}</p>
                {(() => {
                  try {
                    const raw = typeof viewing.ai_analysis.ai_analysis === 'string'
                      ? JSON.parse(viewing.ai_analysis.ai_analysis)
                      : viewing.ai_analysis.ai_analysis
                    return raw?.personality_strategy
                      ? <p><strong>性格策略：</strong>{raw.personality_strategy}</p>
                      : null
                  } catch { return null }
                })()}
              </Card>
            )}

            {/* 提醒 */}
            <Card
              size="small"
              title="待办提醒"
              style={{ marginBottom: 12 }}
              extra={<Button type="link" size="small" onClick={() => handleAutoRemind(viewing.id)}>智能生成</Button>}
            >
              {(viewing.reminders || []).filter(r => r.status === 'pending').length === 0 ? (
                <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无待办提醒" />
              ) : (
                <List
                  size="small"
                  dataSource={(viewing.reminders || []).filter(r => r.status === 'pending')}
                  renderItem={r => (
                    <List.Item
                      actions={[
                        <a key="done" onClick={() => completeReminder(r.id)}>完成</a>,
                        <a key="snooze" onClick={() => snoozeReminder(r.id, 1)}>延期</a>,
                      ]}
                    >
                      <List.Item.Meta
                        title={
                          <Space>
                            <Tag color={PRIORITY_COLORS[r.priority]}>{PRIORITY_LABELS[r.priority] || r.priority}</Tag>
                            {r.title}
                          </Space>
                        }
                        description={
                          <>
                            <div>{r.content}</div>
                            <div style={{ color: '#5b5bd6' }}>{r.suggested_action}</div>
                            <div style={{ fontSize: 12, color: '#999' }}>{formatDate(r.remind_date)}</div>
                          </>
                        }
                      />
                    </List.Item>
                  )}
                />
              )}
            </Card>

            {/* 跟进时间线 */}
            <Card
              size="small"
              title="跟进记录"
              extra={
                <Button size="small" type="primary" icon={<PlusOutlined />} onClick={() => openFollow(viewing)}>
                  添加
                </Button>
              }
            >
              {(viewing.follow_records || []).length === 0 ? (
                <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无跟进" />
              ) : (
                <Timeline
                  items={(viewing.follow_records || []).map(r => ({
                    color: r.follow_result === 'deal_closed' ? 'green'
                      : r.follow_result === 'appointment_scheduled' ? 'blue' : 'gray',
                    children: (
                      <div>
                        <div style={{ fontWeight: 600 }}>{r.content}</div>
                        <div style={{ fontSize: 12, color: '#999', marginTop: 4 }}>
                          {formatDateTime(r.follow_time)}
                          {r.operator && ` · ${r.operator}`}
                          {r.method && ` · ${METHOD_OPTIONS.find(m => m.value === r.method)?.label || r.method}`}
                          {r.follow_result && ` · ${FOLLOW_RESULTS.find(f => f.value === r.follow_result)?.label || r.follow_result}`}
                          {r.next_time && ` · 下次：${formatDateTime(r.next_time)}`}
                        </div>
                      </div>
                    ),
                  }))}
                />
              )}
            </Card>
          </div>
        )}
      </Drawer>
    </div>
  )
}
