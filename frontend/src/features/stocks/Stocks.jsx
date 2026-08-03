import { useState, useEffect } from 'react'
import {
  Table, Tag, Button, Input, Select, Space, Modal, message,
  Form, Popconfirm, Tooltip, Row, Col, Card, Tabs, Checkbox,
  InputNumber, Spin, Empty, Divider,
} from 'antd'
import {
  PlusOutlined, EditOutlined, DeleteOutlined, ReloadOutlined,
  SearchOutlined, LineChartOutlined, FundOutlined,
  ThunderboltOutlined, RobotOutlined, AimOutlined,
} from '@ant-design/icons'
import { stocksApi } from '../../api'

const listTypeOptions = [
  { value: 'watch', label: '关注' },
  { value: 'observe', label: '观察' },
  { value: 'holding', label: '持仓' },
  { value: 'history', label: '历史' },
  { value: 'all', label: '全部' },
]
const listTypeColors = { holding: 'red', watch: 'blue', observe: 'orange', history: 'default', all: 'purple' }
const listTypeLabels = { holding: '持仓', watch: '关注', observe: '观察', history: '历史', all: '全部' }

const strategyTypeOptions = [
  { value: 'trend', label: '趋势' },
  { value: 'breakout', label: '突破' },
  { value: 'rebound', label: '反弹' },
  { value: 'leader', label: '龙头' },
]
const strategyTypeColors = { trend: 'blue', breakout: 'green', rebound: 'orange', leader: 'red' }
const strategyTypeLabels = { trend: '趋势', breakout: '突破', rebound: '反弹', leader: '龙头' }

const screeningConditions = [
  'MACD金叉', '均线多头', '成交量放大', '突破平台',
  'RSI低位', '布林下轨', 'KDJ金叉', '回踩支撑',
]

const INDICATOR_LABELS = {
  MACD: 'MACD', KDJ: 'KDJ', RSI: 'RSI', MA: '均线', BOLL: '布林带',
  VOLUME: '成交量', TREND: '趋势',
}

function numOrNull(v) {
  if (v == null || v === '') return null
  const n = Number(v)
  return Number.isFinite(n) ? n : null
}

function KLineChart({ bars = [] }) {
  const data = Array.isArray(bars) ? bars.slice(-80) : []
  if (data.length < 2) {
    return <Empty description="K线数据不足（接口未返回 bars）" style={{ padding: 24 }} />
  }

  const width = 900
  const height = 360
  const pad = { left: 54, right: 15, top: 25, bottom: 34 }
  const plotW = width - pad.left - pad.right
  const plotH = height - pad.top - pad.bottom
  const maKeys = ['MA5', 'MA10', 'MA20', 'MA30', 'MA60', 'MA250']
  const colors = {
    MA5: '#e6a23c', MA10: '#8b5cf6', MA20: '#1677ff',
    MA30: '#13c2c2', MA60: '#722ed1', MA250: '#333',
  }
  // JSON null 经 Number() 会变成 0，必须先过滤，否则坐标被压扁
  const values = data.flatMap(d => [
    numOrNull(d.high), numOrNull(d.low),
    ...maKeys.map(k => numOrNull(d[k])),
  ]).filter(v => v != null)
  if (values.length < 2) {
    return <Empty description="K线价格字段无效" style={{ padding: 24 }} />
  }
  const min = Math.min(...values)
  const max = Math.max(...values)
  const range = Math.max(max - min, 0.01)
  const y = v => pad.top + (max - Number(v)) / range * plotH
  const step = plotW / data.length
  const x = i => pad.left + step * (i + 0.5)
  const bodyW = Math.max(2, step * 0.58)

  const linePath = key => {
    let started = false
    return data.map((d, i) => {
      const v = numOrNull(d[key])
      if (v == null) return ''
      const cmd = started ? 'L' : 'M'
      started = true
      return `${cmd}${x(i).toFixed(1)},${y(v).toFixed(1)}`
    }).filter(Boolean).join(' ')
  }

  return (
    <div style={{ overflowX: 'auto' }}>
      <Space wrap size={12} style={{ marginBottom: 6 }}>
        {maKeys.map(k => (
          <span key={k} style={{ color: colors[k], fontSize: 12 }}>
            {k === 'MA250' ? '年线MA250' : k}
          </span>
        ))}
        <span style={{ color: '#999', fontSize: 12 }}>红涨绿跌 · 日K · 最近{data.length}日</span>
      </Space>
      <svg viewBox={`0 0 ${width} ${height}`} style={{ width: '100%', minWidth: 680, background: '#fafafa', display: 'block' }}>
        {[0, 0.25, 0.5, 0.75, 1].map((p, i) => {
          const yy = pad.top + p * plotH
          const price = max - p * range
          return (
            <g key={i}>
              <line x1={pad.left} y1={yy} x2={width - pad.right} y2={yy} stroke="#e8e8e8" />
              <text x={pad.left - 6} y={yy + 4} textAnchor="end" fontSize="11" fill="#888">{price.toFixed(2)}</text>
            </g>
          )
        })}
        {data.map((d, i) => {
          const open = numOrNull(d.open)
          const close = numOrNull(d.close)
          const high = numOrNull(d.high)
          const low = numOrNull(d.low)
          if (open == null || close == null || high == null || low == null) return null
          const color = close >= open ? '#cf1322' : '#389e0d'
          const top = y(Math.max(open, close))
          const bodyH = Math.max(1, Math.abs(y(open) - y(close)))
          return (
            <g key={d.date || i}>
              <line x1={x(i)} y1={y(high)} x2={x(i)} y2={y(low)} stroke={color} />
              <rect
                x={x(i) - bodyW / 2}
                y={top}
                width={bodyW}
                height={bodyH}
                fill={close >= open ? color : '#fff'}
                stroke={color}
              />
            </g>
          )
        })}
        {maKeys.map(k => {
          const d = linePath(k)
          return d ? <path key={k} d={d} fill="none" stroke={colors[k]} strokeWidth="1.2" /> : null
        })}
        {[0, Math.floor(data.length / 2), data.length - 1].map(i => (
          <text key={i} x={x(i)} y={height - 10} textAnchor="middle" fontSize="11" fill="#888">
            {(data[i]?.date || '').slice(5)}
          </text>
        ))}
      </svg>
    </div>
  )
}

export default function Stocks() {
  const [activeTab, setActiveTab] = useState('watchlist')

  // === Tab 1: 自选股管理 ===
  const [watchlist, setWatchlist] = useState([])
  const [watchlistLoading, setWatchlistLoading] = useState(true)
  const [stockModal, setStockModal] = useState(false)
  const [stockEditing, setStockEditing] = useState(null)
  const [stockForm] = Form.useForm()
  const [indicatorsModal, setIndicatorsModal] = useState(false)
  const [indicatorsData, setIndicatorsData] = useState(null)
  const [indicatorsLoading, setIndicatorsLoading] = useState(false)
  const [indicatorsCode, setIndicatorsCode] = useState('')
  const [indicatorsName, setIndicatorsName] = useState('')

  const loadWatchlist = () => {
    setWatchlistLoading(true)
    stocksApi.watchlist()
      .then(res => setWatchlist(res?.list || res || []))
      .catch(() => message.error('加载自选股失败'))
      .finally(() => setWatchlistLoading(false))
  }

  useEffect(() => { loadWatchlist() }, [])

  const handleStockSave = () => {
    stockForm.validateFields().then(values => {
      if (stockEditing) {
        stocksApi.updateStock(stockEditing.id, values).then(() => {
          message.success('已更新'); setStockModal(false); loadWatchlist()
        }).catch(() => message.error('更新失败'))
      } else {
        stocksApi.addStock(values).then(() => {
          message.success('股票已添加'); setStockModal(false); loadWatchlist()
        }).catch(() => message.error('添加失败'))
      }
    })
  }

  const handleViewIndicators = (codeOrRow) => {
    const code = typeof codeOrRow === 'object'
      ? (codeOrRow.stock_code || codeOrRow.code)
      : codeOrRow
    const name = typeof codeOrRow === 'object'
      ? (codeOrRow.stock_name || codeOrRow.name || '')
      : ''
    setIndicatorsCode(code)
    setIndicatorsName(name)
    setIndicatorsModal(true)
    setIndicatorsLoading(true)
    setIndicatorsData(null)
    stocksApi.indicators(code)
      .then(data => setIndicatorsData(data))
      .catch(err => message.error(err?.error || '获取指标失败'))
      .finally(() => setIndicatorsLoading(false))
  }

  const watchlistColumns = [
    { title: 'ID', dataIndex: 'id', width: 60 },
    {
      title: '股票代码', dataIndex: 'stock_code', width: 120,
      render: (v, r) => (
        <a onClick={() => handleViewIndicators(r)} style={{ cursor: 'pointer', color: '#1677ff' }}>
          {v}
        </a>
      ),
    },
    { title: '股票名称', dataIndex: 'stock_name', width: 100 },
    {
      title: '类型', dataIndex: 'list_type', width: 80,
      render: v => <Tag color={listTypeColors[v]}>{listTypeLabels[v] || v}</Tag>,
    },
    { title: '买入价', dataIndex: 'buy_price', width: 100, render: v => v ?? '-' },
    {
      title: '现价', dataIndex: 'current_price', width: 100,
      render: (v, r) => {
        if (v == null) return '-'
        const change = r.buy_price ? ((v - r.buy_price) / r.buy_price * 100) : 0
        return (
          <span style={{ color: change > 0 ? '#cf1322' : change < 0 ? '#3f8600' : '#666' }}>
            {v} {r.buy_price ? `(${change > 0 ? '+' : ''}${change.toFixed(2)}%)` : ''}
          </span>
        )
      },
    },
    { title: '数量', dataIndex: 'quantity', width: 80, render: v => v ?? '-' },
    { title: '备注', dataIndex: 'notes', width: 160, ellipsis: true, render: v => v || '-' },
    { title: '添加时间', dataIndex: 'added_at', width: 160 },
    {
      title: '操作', key: 'action', width: 120, fixed: 'right',
      render: (_, r) => (
        <Space size="small">
          <Tooltip title="编辑">
            <Button size="small" icon={<EditOutlined />} onClick={() => {
              setStockEditing(r); stockForm.setFieldsValue(r); setStockModal(true)
            }} />
          </Tooltip>
          <Popconfirm title="确认删除？" onConfirm={() => {
            stocksApi.deleteStock(r.id).then(() => { message.success('已删除'); loadWatchlist() })
              .catch(() => message.error('删除失败'))
          }}>
            <Button size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ]

  // === Tab 2: 条件筛选 ===
  const [selectedConditions, setSelectedConditions] = useState([])
  const [screeningLoading, setScreeningLoading] = useState(false)
  const [screeningHistory, setScreeningHistory] = useState([])
  const [screeningResult, setScreeningResult] = useState(null)
  const [historyLoading, setHistoryLoading] = useState(false)

  const loadScreeningHistory = () => {
    setHistoryLoading(true)
    stocksApi.screeningHistory()
      .then(res => setScreeningHistory(res?.list || res || []))
      .catch(() => {})
      .finally(() => setHistoryLoading(false))
  }

  const handleScreening = () => {
    if (selectedConditions.length === 0) {
      message.warning('请至少选择一个筛选条件')
      return
    }
    setScreeningLoading(true)
    stocksApi.screening({ conditions: selectedConditions })
      .then(res => {
        message.success('筛选完成')
        setScreeningResult(res)
        loadScreeningHistory()
      })
      .catch(() => message.error('筛选失败'))
      .finally(() => setScreeningLoading(false))
  }

  const screeningHistoryColumns = [
    { title: 'ID', dataIndex: 'id', width: 60 },
    { title: '名称', dataIndex: 'name', width: 140, ellipsis: true, render: v => v || '-' },
    {
      title: '条件', dataIndex: 'conditions_json', width: 240, ellipsis: true,
      render: v => {
        if (!v) return '-'
        try {
          const obj = typeof v === 'string' ? JSON.parse(v) : v
          return (obj.conditions || []).join('、') || '-'
        } catch { return String(v) }
      },
    },
    {
      title: '状态', dataIndex: 'status', width: 80,
      render: v => <Tag color={v === 'completed' ? 'green' : 'blue'}>{v || '-'}</Tag>,
    },
    { title: '创建时间', dataIndex: 'created_at', width: 160 },
  ]

  // === Tab 3: AI策略 ===
  const [strategies, setStrategies] = useState([])
  const [strategiesLoading, setStrategiesLoading] = useState(true)
  const [strategyModal, setStrategyModal] = useState(false)
  const [strategyEditing, setStrategyEditing] = useState(null)
  const [strategyForm] = Form.useForm()

  const loadStrategies = () => {
    setStrategiesLoading(true)
    stocksApi.strategies()
      .then(res => setStrategies(res?.list || res || []))
      .catch(() => message.error('加载策略失败'))
      .finally(() => setStrategiesLoading(false))
  }

  const handleStrategySave = () => {
    strategyForm.validateFields().then(values => {
      if (strategyEditing) {
        stocksApi.updateStrategy(strategyEditing.id, values).then(() => {
          message.success('策略已更新'); setStrategyModal(false); loadStrategies()
        }).catch(() => message.error('更新失败'))
      } else {
        stocksApi.createStrategy(values).then(() => {
          message.success('策略已创建'); setStrategyModal(false); loadStrategies()
        }).catch(() => message.error('创建失败'))
      }
    })
  }

  const strategyColumns = [
    { title: 'ID', dataIndex: 'id', width: 60 },
    { title: '名称', dataIndex: 'name', width: 140, ellipsis: true },
    {
      title: '类型', dataIndex: 'strategy_type', width: 80,
      render: v => <Tag color={strategyTypeColors[v]}>{strategyTypeLabels[v] || v}</Tag>,
    },
    {
      title: '得分', dataIndex: 'score', width: 80,
      render: v => v != null ? <span style={{ color: v >= 80 ? '#ff4d4f' : v >= 60 ? '#faad14' : '#999', fontWeight: 600 }}>{v}</span> : '-',
    },
    {
      title: '命中率', dataIndex: 'hit_rate', width: 80,
      render: v => v != null ? `${(v * 100).toFixed(1)}%` : '-',
    },
    { title: '总交易', dataIndex: 'total_trades', width: 80, render: v => v ?? '-' },
    { title: '胜场', dataIndex: 'winning_trades', width: 80, render: v => v ?? '-' },
    {
      title: '状态', dataIndex: 'status', width: 80,
      render: v => <Tag color={v === 'active' ? 'green' : 'default'}>{v === 'active' ? '启用' : v || '-'}</Tag>,
    },
    {
      title: '操作', key: 'action', width: 120, fixed: 'right',
      render: (_, r) => (
        <Space size="small">
          <Tooltip title="编辑">
            <Button size="small" icon={<EditOutlined />} onClick={() => {
              setStrategyEditing(r)
              strategyForm.setFieldsValue({
                ...r,
                rules_json: r.rules_json ? (typeof r.rules_json === 'string' ? r.rules_json : JSON.stringify(r.rules_json, null, 2)) : '',
              })
              setStrategyModal(true)
            }} />
          </Tooltip>
          <Popconfirm title="确认删除？" onConfirm={() => {
            stocksApi.deleteStrategy(r.id).then(() => { message.success('已删除'); loadStrategies() })
              .catch(() => message.error('删除失败'))
          }}>
            <Button size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ]

  // === Tab 4: AI复盘 ===
  const [reviewText, setReviewText] = useState('')
  const [reviewLoading, setReviewLoading] = useState(false)
  const [reviewResult, setReviewResult] = useState(null)

  const handleReview = () => {
    if (!reviewText.trim()) {
      message.warning('请输入交易记录')
      return
    }
    setReviewLoading(true)
    stocksApi.review({ input: reviewText })
      .then(res => {
        message.success('AI复盘完成')
        setReviewResult(res)
      })
      .catch(() => message.error('复盘失败'))
      .finally(() => setReviewLoading(false))
  }

  // ==================== RENDER ====================

  const tabItems = [
    // Tab 1: 自选股管理
    {
      key: 'watchlist',
      label: <span><LineChartOutlined /> 自选股管理</span>,
      children: (
        <div>
          <div className="table-toolbar" style={{ marginBottom: 16 }}>
            <div className="table-toolbar-left">
              <Button icon={<ReloadOutlined />} onClick={() => loadWatchlist()}>刷新</Button>
            </div>
            <Button type="primary" icon={<PlusOutlined />} onClick={() => {
              setStockEditing(null); stockForm.resetFields(); setStockModal(true)
            }}>添加股票</Button>
          </div>

          <Table
            columns={watchlistColumns}
            dataSource={watchlist}
            rowKey="id"
            loading={watchlistLoading}
            scroll={{ x: 1100 }}
            size="middle"
            pagination={{ pageSize: 15, showTotal: (t) => `共 ${t} 条` }}
          />

          {/* Add/Edit Stock Modal */}
          <Modal
            title={stockEditing ? '编辑股票' : '添加股票'}
            open={stockModal}
            onOk={handleStockSave}
            onCancel={() => setStockModal(false)}
            width={560}
          >
            <Form form={stockForm} layout="vertical" style={{ marginTop: 16 }}>
              <Row gutter={16}>
                <Col span={12}>
                  <Form.Item name="stock_code" label="股票代码" rules={[{ required: true, message: '请输入股票代码' }]}>
                    <Input placeholder="如：600519" />
                  </Form.Item>
                </Col>
                <Col span={12}>
                  <Form.Item name="stock_name" label="股票名称" rules={[{ required: true, message: '请输入股票名称' }]}>
                    <Input placeholder="如：贵州茅台" />
                  </Form.Item>
                </Col>
              </Row>
              <Row gutter={16}>
                <Col span={12}>
                  <Form.Item name="list_type" label="类型" initialValue="watch">
                    <Select options={listTypeOptions} />
                  </Form.Item>
                </Col>
                <Col span={12}>
                  <Form.Item name="current_price" label="现价">
                    <InputNumber style={{ width: '100%' }} precision={2} placeholder="0.00" />
                  </Form.Item>
                </Col>
              </Row>
              <Row gutter={16}>
                <Col span={12}>
                  <Form.Item name="buy_price" label="买入价">
                    <InputNumber style={{ width: '100%' }} precision={2} placeholder="0.00" />
                  </Form.Item>
                </Col>
                <Col span={12}>
                  <Form.Item name="quantity" label="数量">
                    <InputNumber style={{ width: '100%' }} precision={0} placeholder="0" />
                  </Form.Item>
                </Col>
              </Row>
              <Form.Item name="notes" label="备注">
                <Input.TextArea rows={2} placeholder="添加备注信息..." />
              </Form.Item>
            </Form>
          </Modal>
        </div>
      ),
    },

    // Tab 2: 条件筛选
    {
      key: 'screening',
      label: <span><SearchOutlined /> 条件筛选</span>,
      children: (
        <div>
          <Card title={<span><FundOutlined /> 筛选条件</span>} size="small" style={{ marginBottom: 16 }}>
            <Checkbox.Group
              value={selectedConditions}
              onChange={setSelectedConditions}
              style={{ width: '100%' }}
            >
              <Row gutter={[16, 12]}>
                {screeningConditions.map(c => (
                  <Col key={c} span={6}>
                    <Checkbox value={c}>{c}</Checkbox>
                  </Col>
                ))}
              </Row>
            </Checkbox.Group>
            <Divider />
            <Button type="primary" icon={<SearchOutlined />} loading={screeningLoading}
              onClick={handleScreening} size="large"
            >开始筛选</Button>
          </Card>

          {/* Screening Result */}
          {screeningResult && (
            <Card title={<span><ThunderboltOutlined /> 筛选结果</span>} size="small" style={{ marginBottom: 16 }}>
              <pre style={{
                background: '#f5f5f5', padding: 16, borderRadius: 8,
                maxHeight: 300, overflow: 'auto', margin: 0,
              }}>
                {typeof screeningResult === 'object'
                  ? JSON.stringify(screeningResult, null, 2)
                  : String(screeningResult)}
              </pre>
            </Card>
          )}

          {/* Screening History */}
          <Card title={<span><ReloadOutlined /> 筛选历史</span>} size="small">
            <Table
              columns={screeningHistoryColumns}
              dataSource={screeningHistory}
              rowKey="id"
              loading={historyLoading}
              scroll={{ x: 700 }}
              size="small"
              pagination={{ pageSize: 10, showTotal: (t) => `共 ${t} 条` }}
              locale={{ emptyText: <Empty description="暂无筛选历史" /> }}
            />
          </Card>
        </div>
      ),
    },

    // Tab 3: AI策略
    {
      key: 'strategy',
      label: <span><RobotOutlined /> AI策略</span>,
      children: (
        <div>
          <div className="table-toolbar" style={{ marginBottom: 16 }}>
            <div className="table-toolbar-left">
              <Button icon={<ReloadOutlined />} onClick={() => loadStrategies()}>刷新</Button>
            </div>
            <Button type="primary" icon={<PlusOutlined />} onClick={() => {
              setStrategyEditing(null); strategyForm.resetFields(); setStrategyModal(true)
            }}>创建策略</Button>
          </div>

          <Table
            columns={strategyColumns}
            dataSource={strategies}
            rowKey="id"
            loading={strategiesLoading}
            scroll={{ x: 900 }}
            size="middle"
            pagination={{ pageSize: 15, showTotal: (t) => `共 ${t} 条` }}
          />

          {/* Create/Edit Strategy Modal */}
          <Modal
            title={strategyEditing ? '编辑策略' : '创建策略'}
            open={strategyModal}
            onOk={handleStrategySave}
            onCancel={() => setStrategyModal(false)}
            width={600}
          >
            <Form form={strategyForm} layout="vertical" style={{ marginTop: 16 }}>
              <Row gutter={16}>
                <Col span={12}>
                  <Form.Item name="name" label="策略名称" rules={[{ required: true, message: '请输入策略名称' }]}>
                    <Input placeholder="如：趋势跟踪策略" />
                  </Form.Item>
                </Col>
                <Col span={12}>
                  <Form.Item name="strategy_type" label="策略类型" initialValue="trend">
                    <Select options={strategyTypeOptions} />
                  </Form.Item>
                </Col>
              </Row>
              <Form.Item name="description" label="策略描述">
                <Input.TextArea rows={2} placeholder="描述策略逻辑..." />
              </Form.Item>
              <Form.Item name="rules_json" label="策略规则 (JSON)"
                extra="输入JSON格式的策略规则，如条件组合、指标参数等">
                <Input.TextArea rows={6} placeholder='{"conditions": ["MACD金叉", "均线多头"], "params": {"period": 20}}' />
              </Form.Item>
              <Row gutter={16}>
                <Col span={12}>
                  <Form.Item name="score" label="得分">
                    <InputNumber style={{ width: '100%' }} min={0} max={100} placeholder="0-100" />
                  </Form.Item>
                </Col>
                <Col span={12}>
                  <Form.Item name="hit_rate" label="命中率 (%)"
                    extra="输入小数，如0.68表示68%">
                    <InputNumber style={{ width: '100%' }} min={0} max={1} step={0.01}
                      placeholder="0.00-1.00" formatter={v => v} parser={v => v} />
                  </Form.Item>
                </Col>
              </Row>
              <Row gutter={16}>
                <Col span={12}>
                  <Form.Item name="total_trades" label="总交易次数">
                    <InputNumber style={{ width: '100%' }} min={0} precision={0} placeholder="0" />
                  </Form.Item>
                </Col>
                <Col span={12}>
                  <Form.Item name="winning_trades" label="胜场数">
                    <InputNumber style={{ width: '100%' }} min={0} precision={0} placeholder="0" />
                  </Form.Item>
                </Col>
              </Row>
              <Form.Item name="status" label="状态" initialValue="active">
                <Select options={[
                  { value: 'active', label: '启用' },
                  { value: 'inactive', label: '停用' },
                ]} />
              </Form.Item>
            </Form>
          </Modal>
        </div>
      ),
    },

    // Tab 4: AI复盘
    {
      key: 'review',
      label: <span><AimOutlined /> AI复盘</span>,
      children: (
        <div>
          <Row gutter={24}>
            <Col span={12}>
              <Card title="交易记录" size="small">
                <Input.TextArea
                  rows={8}
                  value={reviewText}
                  onChange={e => setReviewText(e.target.value)}
                  placeholder="请输入今天的交易记录，包括买入/卖出的股票、价格、数量、操作理由等..."
                  style={{ marginBottom: 16 }}
                />
                <Button type="primary" icon={<RobotOutlined />} loading={reviewLoading}
                  onClick={handleReview} block size="large"
                >AI复盘</Button>
              </Card>
            </Col>
            <Col span={12}>
              {reviewResult ? (
                <div>
                  <Card title="复盘结果" size="small" style={{ marginBottom: 12 }}
                    extra={<Tag color="green">AI 分析完成</Tag>}>
                    <Row gutter={[8, 8]}>
                      {reviewResult.success_trades && (
                        <Col span={12}>
                          <div style={{
                            background: '#f6ffed', padding: '12px 16px',
                            borderRadius: 8, border: '1px solid #b7eb8f',
                          }}>
                            <div style={{ fontSize: 12, color: '#52c41a', marginBottom: 4 }}>成功交易</div>
                            <div style={{ fontSize: 20, fontWeight: 700, color: '#52c41a' }}>
                              {Array.isArray(reviewResult.success_trades)
                                ? reviewResult.success_trades.length
                                : reviewResult.success_trades}
                            </div>
                          </div>
                        </Col>
                      )}
                      {reviewResult.failure_trades != null && (
                        <Col span={12}>
                          <div style={{
                            background: '#fff2f0', padding: '12px 16px',
                            borderRadius: 8, border: '1px solid #ffccc7',
                          }}>
                            <div style={{ fontSize: 12, color: '#ff4d4f', marginBottom: 4 }}>失败交易</div>
                            <div style={{ fontSize: 20, fontWeight: 700, color: '#ff4d4f' }}>
                              {Array.isArray(reviewResult.failure_trades)
                                ? reviewResult.failure_trades.length
                                : reviewResult.failure_trades}
                            </div>
                          </div>
                        </Col>
                      )}
                      {reviewResult.win_rate_trend != null && (
                        <Col span={24} style={{ marginTop: 4 }}>
                          <div style={{ fontSize: 13, color: '#666' }}>
                            胜率趋势：<span style={{ fontWeight: 600, color: '#1677ff' }}>
                              {typeof reviewResult.win_rate_trend === 'number'
                                ? `${(reviewResult.win_rate_trend * 100).toFixed(1)}%`
                                : String(reviewResult.win_rate_trend)}
                            </span>
                          </div>
                        </Col>
                      )}
                    </Row>
                  </Card>
                  {reviewResult.reason_analysis && (
                    <Card title="原因分析" size="small" style={{ marginBottom: 12 }}>
                      <div style={{ whiteSpace: 'pre-wrap', lineHeight: 1.8, fontSize: 13 }}>
                        {reviewResult.reason_analysis}
                      </div>
                    </Card>
                  )}
                  {reviewResult.strategy_suggestions && (
                    <Card title="策略建议" size="small" style={{ marginBottom: 12 }}>
                      <div style={{ whiteSpace: 'pre-wrap', lineHeight: 1.8, fontSize: 13 }}>
                        {reviewResult.strategy_suggestions}
                      </div>
                    </Card>
                  )}
                </div>
              ) : (
                <Card size="small" style={{ minHeight: 240, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                  <Empty description={'点击"AI复盘"按钮开始分析'} />
                </Card>
              )}
            </Col>
          </Row>
        </div>
      ),
    },
  ]

  return (
    <div>
      <div className="page-title">股票研究系统</div>
      <Tabs activeKey={activeTab} onChange={setActiveTab} items={tabItems} size="large" />

      <Modal
        title={`K线/指标 - ${indicatorsName ? `${indicatorsName}(${indicatorsCode})` : indicatorsCode}`}
        open={indicatorsModal}
        onCancel={() => setIndicatorsModal(false)}
        footer={null}
        width={1000}
        destroyOnClose
      >
        <Spin spinning={indicatorsLoading}>
          {Object.keys(indicatorsData?.indicators || {}).length > 0 || (indicatorsData?.bars || []).length > 0 ? (
            <div style={{ marginTop: 8 }}>
              {indicatorsData.close != null && (
                <div style={{ marginBottom: 12, fontSize: 15 }}>
                  收盘 <b>{indicatorsData.close}</b>
                  <span style={{
                    marginLeft: 12,
                    color: (indicatorsData.pct_hint || 0) > 0 ? '#cf1322'
                      : (indicatorsData.pct_hint || 0) < 0 ? '#3f8600' : '#666',
                  }}>
                    {(indicatorsData.pct_hint || 0) > 0 ? '+' : ''}{indicatorsData.pct_hint}%
                  </span>
                </div>
              )}
              <KLineChart bars={indicatorsData.bars || []} />
              <Divider>最新技术指标</Divider>
              {Object.entries(indicatorsData.indicators || {}).map(([key, value]) => (
                <Row key={key} gutter={16} style={{ marginBottom: 10 }}>
                  <Col span={4} style={{ fontWeight: 600 }}>{INDICATOR_LABELS[key] || key}</Col>
                  <Col span={20}>
                    {typeof value === 'object' && value !== null
                      ? Object.entries(value).map(([k, v]) => (
                        <Tag key={k} style={{ marginBottom: 4 }}>{k}: {String(v ?? '-')}</Tag>
                      ))
                      : String(value ?? '-')}
                  </Col>
                </Row>
              ))}
              {indicatorsData.note && <div style={{ color: '#888', marginTop: 8 }}>{indicatorsData.note}</div>}
            </div>
          ) : !indicatorsLoading ? (
            <Empty
              description={indicatorsData?.note || indicatorsData?.error || '暂无指标数据'}
              style={{ padding: 32 }}
            />
          ) : null}
        </Spin>
      </Modal>
    </div>
  )
}
