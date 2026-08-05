import { useState, useEffect, useMemo, useRef } from 'react'
import {
  Table, Tag, Button, Input, Select, Space, Modal, message,
  Form, Popconfirm, Tooltip, Row, Col, Card, Tabs, Checkbox,
  InputNumber, Spin, Empty, Divider, Switch, Alert,
} from 'antd'
import {
  PlusOutlined, EditOutlined, DeleteOutlined, ReloadOutlined,
  SearchOutlined, LineChartOutlined, FundOutlined,
  ThunderboltOutlined, RobotOutlined, AimOutlined, SettingOutlined,
  UnorderedListOutlined,
} from '@ant-design/icons'
import { stocksApi } from '../../api'
import { formatDateTime } from '../../utils/date'
import './Stocks.css'

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

const STRATEGY_RULE_EXAMPLE = `买入条件：
1. 均线多头排列（MA5 > MA10 > MA20）
2. 当日成交量放大到近5日均量的1.5倍以上
3. 收盘价突破近20日高点

卖出条件：
1. 跌破MA20止损
2. 盈利超过12%减半仓
3. 出现明显放量滞涨则清仓

备注：避开ST、北交所；开盘半小时后再看量能确认。`

/** 把复盘字段（含误返回的 JSON 对象/字符串）整理成可读条目 */
function parseReviewField(value) {
  if (value == null || value === '') return []
  if (Array.isArray(value)) {
    return value
      .map((item, i) => {
        if (item && typeof item === 'object') {
          const label = item.title || item.name || item.label || `第 ${i + 1} 条`
          const text = item.text || item.content || item.action || item.desc || JSON.stringify(item)
          return { label: String(label), text: String(text) }
        }
        return { label: '', text: String(item) }
      })
      .filter(x => x.text.trim())
  }
  if (typeof value === 'object') {
    return Object.entries(value)
      .map(([key, v]) => {
        let label = key
        const m = String(key).match(/^position[_-]?(\d{6})$/i)
        if (m) label = `持仓 ${m[1]}`
        else if (/^strategy[_-]?/i.test(key)) label = `策略 ${String(key).replace(/^strategy[_-]?/i, '') || ''}`.trim()
        else if (key === 'overall' || key === 'general') label = '整体'
        return { label, text: typeof v === 'string' ? v : (v == null ? '' : JSON.stringify(v)) }
      })
      .filter(x => String(x.text).trim())
  }
  const raw = String(value).trim()
  if ((raw.startsWith('{') && raw.endsWith('}')) || (raw.startsWith('[') && raw.endsWith(']'))) {
    try {
      return parseReviewField(JSON.parse(raw))
    } catch {
      /* fall through */
    }
  }
  // 按空行或编号拆成多条
  const chunks = raw
    .split(/\n+/)
    .map(s => s.trim())
    .filter(Boolean)
  if (chunks.length <= 1) return [{ label: '', text: raw }]
  return chunks.map(line => {
    const m = line.match(/^【([^】]+)】\s*(.*)$/)
    if (m) return { label: m[1], text: m[2] || '' }
    return { label: '', text: line }
  })
}

function ReviewFieldText({ value, danger = false }) {
  const items = parseReviewField(value)
  if (!items.length) return null
  const style = {
    whiteSpace: 'pre-wrap',
    lineHeight: 1.8,
    fontSize: 13,
    color: danger ? '#a8071a' : undefined,
  }
  if (items.length === 1 && !items[0].label) {
    return <div style={style}>{items[0].text}</div>
  }
  return (
    <div className="stocks-review-actions">
      {items.map((item, idx) => (
        <div key={`${item.label}-${idx}`} className="stocks-review-action-item">
          {item.label ? <div className="stocks-review-action-label">{item.label}</div> : null}
          <div style={style}>{item.text}</div>
        </div>
      ))}
    </div>
  )
}

/** 把库里的 rules_json 转成普通人可读的文字（兼容旧 JSON） */
function rulesToText(raw) {
  if (raw == null || raw === '') return ''
  if (typeof raw !== 'string') {
    try { return rulesToText(JSON.stringify(raw)) } catch { return String(raw) }
  }
  const text = raw.trim()
  if (!text) return ''
  if (!(text.startsWith('{') || text.startsWith('['))) return text
  try {
    const obj = JSON.parse(text)
    if (typeof obj === 'string') return obj
    if (obj && typeof obj.text === 'string' && obj.text.trim()) return obj.text
    if (obj && typeof obj.content === 'string') return obj.content
    const lines = []
    if (Array.isArray(obj.rules) && obj.rules.length) {
      lines.push('规则：')
      obj.rules.forEach((r, i) => {
        if (!r) return
        const label = r.label || r.key || `规则${i + 1}`
        const params = r.params && Object.keys(r.params).length
          ? `（参数：${Object.entries(r.params).map(([k, v]) => `${k}=${Array.isArray(v) ? v.join(',') : v}`).join('，')}）`
          : ''
        lines.push(`${i + 1}. ${label}${params}`)
      })
    } else if (Array.isArray(obj.conditions) && obj.conditions.length) {
      lines.push('条件：' + obj.conditions.join('、'))
    }
    if (obj.position) {
      const p = obj.position
      lines.push('仓位与进出：')
      if (p.entry) lines.push(`买入：${p.entry}`)
      if (p.stop_loss) lines.push(`止损：${p.stop_loss}`)
      if (p.take_profit) lines.push(`止盈：${p.take_profit}`)
    }
    if (obj.notes) lines.push(`备注：${obj.notes}`)
    if (obj.match_mode) lines.push(`匹配方式：${obj.match_mode}`)
    return lines.length ? lines.join('\n') : text
  } catch {
    return text
  }
}

function rulesPreview(raw, maxLen = 48) {
  const t = rulesToText(raw).replace(/\s+/g, ' ').trim()
  if (!t) return '-'
  return t.length > maxLen ? `${t.slice(0, maxLen)}…` : t
}

function matchedLabelsOf(strategy) {
  if (!strategy) return []
  if (Array.isArray(strategy.matched_labels) && strategy.matched_labels.length) {
    return strategy.matched_labels
  }
  if (Array.isArray(strategy.screen_rules)) {
    return strategy.screen_rules.map(r => r.label || r.key).filter(Boolean)
  }
  return []
}

const screeningConditionsFallback = [
  { key: 'ma_all_rising', label: '多周期均线全部朝上' },
  { key: 'recent_limit_up', label: '近1个月有涨停' },
  { key: 'macd_golden_cross', label: 'MACD金叉' },
  { key: 'ma_bullish', label: '均线多头排列' },
  { key: 'volume_increase', label: '成交量放大' },
  { key: 'breakthrough', label: '突破平台' },
  { key: 'rsi_low', label: 'RSI低位' },
  { key: 'boll_lower', label: '触及布林下轨' },
  { key: 'kdj_golden_cross', label: 'KDJ金叉' },
  { key: 'pullback_support', label: '回踩支撑' },
]

const RULE_GROUPS = [
  {
    key: 'trend',
    title: '趋势 / 结构',
    keys: ['ma_all_rising', 'ma_bullish', 'breakthrough', 'pullback_support'],
  },
  {
    key: 'momentum',
    title: '动量 / 强弱',
    keys: ['recent_limit_up', 'volume_increase', 'macd_golden_cross', 'kdj_golden_cross'],
  },
  {
    key: 'reversion',
    title: '超卖 / 回踩',
    keys: ['rsi_low', 'boll_lower'],
  },
]

function groupPatternRules(rules) {
  const byKey = Object.fromEntries((rules || []).map(r => [r.key, r]))
  const used = new Set()
  const groups = RULE_GROUPS.map(g => {
    const items = g.keys.map(k => byKey[k]).filter(Boolean)
    items.forEach(r => used.add(r.key))
    return { ...g, items }
  }).filter(g => g.items.length)
  const rest = (rules || []).filter(r => r.key && !used.has(r.key))
  if (rest.length) groups.push({ key: 'other', title: '其他条件', items: rest })
  return groups
}

const paramLabels = {
  periods: '均线周期（逗号分隔）',
  slope_days: '与几日前比较',
  lookback: '回看交易日数',
  ratio: '放量倍数',
  base: '成交量均线周期',
  fast: '短均线',
  mid: '中均线',
  slow: '长均线',
  period: '指标周期',
  threshold: '阈值',
  ma: '均线周期',
  tol: '容差比例',
}

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
  const data = bars.slice(-80)
  if (data.length < 2) return <Empty description="K线数据不足" />

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
  // 注意：JSON 的 null 经 Number() 会变成 0，必须先过滤空值，否则坐标轴被压到 0
  const values = data.flatMap(d => [
    numOrNull(d.high), numOrNull(d.low),
    ...maKeys.map(k => numOrNull(d[k])),
  ]).filter(v => v != null)
  if (values.length < 2) return <Empty description="K线数据不足" />
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
        {maKeys.map(k => <span key={k} style={{ color: colors[k], fontSize: 12 }}>{k === 'MA250' ? '年线MA250' : k}</span>)}
        <span style={{ color: '#999', fontSize: 12 }}>红涨绿跌 · 日K · 最近80日</span>
      </Space>
      <svg viewBox={`0 0 ${width} ${height}`} style={{ width: '100%', minWidth: 680, background: '#fafafa' }}>
        {[0, 0.25, 0.5, 0.75, 1].map((p, i) => {
          const yy = pad.top + p * plotH
          const price = max - p * range
          return <g key={i}>
            <line x1={pad.left} y1={yy} x2={width - pad.right} y2={yy} stroke="#e8e8e8" />
            <text x={pad.left - 6} y={yy + 4} textAnchor="end" fontSize="11" fill="#888">{price.toFixed(2)}</text>
          </g>
        })}
        {data.map((d, i) => {
          const open = numOrNull(d.open); const close = numOrNull(d.close)
          const high = numOrNull(d.high); const low = numOrNull(d.low)
          if (open == null || close == null || high == null || low == null) return null
          const color = close >= open ? '#cf1322' : '#389e0d'
          const top = y(Math.max(open, close))
          const bodyH = Math.max(1, Math.abs(y(open) - y(close)))
          return <g key={d.date || i}>
            <line x1={x(i)} y1={y(high)} x2={x(i)} y2={y(low)} stroke={color} />
            <rect x={x(i) - bodyW / 2} y={top} width={bodyW} height={bodyH}
              fill={close >= open ? color : '#fff'} stroke={color} />
          </g>
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
  const [priceRefreshing, setPriceRefreshing] = useState(false)
  const [stockModal, setStockModal] = useState(false)
  const [stockEditing, setStockEditing] = useState(null)
  const [stockForm] = Form.useForm()
  const [indicatorsModal, setIndicatorsModal] = useState(false)
  const [indicatorsData, setIndicatorsData] = useState(null)
  const [indicatorsLoading, setIndicatorsLoading] = useState(false)
  const [indicatorsCode, setIndicatorsCode] = useState('')
  const [indicatorsName, setIndicatorsName] = useState('')
  const [indicatorsHits, setIndicatorsHits] = useState([])

  const loadWatchlist = () => {
    setWatchlistLoading(true)
    stocksApi.watchlist()
      .then(res => setWatchlist(res?.list || res || []))
      .catch(() => message.error('加载自选股失败'))
      .finally(() => setWatchlistLoading(false))
  }

  useEffect(() => { loadWatchlist() }, [])

  // === 全部股票 ===
  const [universe, setUniverse] = useState({ list: [], total: 0, active_total: 0, last_refresh_at: '' })
  const [universeLoading, setUniverseLoading] = useState(false)
  const [universeRefreshing, setUniverseRefreshing] = useState(false)
  const [universePage, setUniversePage] = useState(1)
  const [universeFilters, setUniverseFilters] = useState({ q: '', board: undefined, sort: 'code' })

  const loadUniverse = (page = universePage, filters = universeFilters) => {
    setUniverseLoading(true)
    stocksApi.universe({
      page,
      pageSize: 20,
      q: filters.q || undefined,
      board: filters.board || undefined,
      sort: filters.sort || 'code',
      active: 1,
    })
      .then(res => {
        setUniverse(res || { list: [], total: 0 })
        setUniversePage(page)
      })
      .catch(() => message.error('加载全部股票失败'))
      .finally(() => setUniverseLoading(false))
  }

  useEffect(() => {
    if (activeTab === 'universe') loadUniverse(1, universeFilters)
  }, [activeTab])

  const handleRefreshUniverse = () => {
    setUniverseRefreshing(true)
    stocksApi.refreshUniverse()
      .then(res => {
        message.success(res?.message || '全市场已同步')
        loadUniverse(1, universeFilters)
      })
      .catch(err => message.error(err?.error || err?.message || '同步失败'))
      .finally(() => setUniverseRefreshing(false))
  }

  const handleAddUniverseToWatchlist = (row) => {
    stocksApi.addStock({
      stock_code: row.code,
      stock_name: row.name,
      list_type: 'watch',
      buy_price: row.price || 0,
      notes: '来自全部股票',
    }).then(() => {
      message.success(`已加入自选：${row.name || row.code}`)
      loadWatchlist()
    }).catch(err => message.error(err?.error || '加入自选失败'))
  }

  const universeColumns = [
    { title: '代码', dataIndex: 'code', width: 100 },
    { title: '名称', dataIndex: 'name', width: 120 },
    { title: '市场', dataIndex: 'market', width: 70 },
    { title: '板块', dataIndex: 'board', width: 100 },
    {
      title: '现价', dataIndex: 'price', width: 90,
      render: v => (v == null ? '-' : Number(v).toFixed(2)),
    },
    {
      title: '涨跌幅', dataIndex: 'pct_chg', width: 90,
      render: v => {
        if (v == null || v === '') return '-'
        const n = Number(v)
        const color = n > 0 ? '#cf1322' : n < 0 ? '#3f8600' : '#666'
        return <span style={{ color }}>{n > 0 ? '+' : ''}{n.toFixed(2)}%</span>
      },
    },
    {
      title: '成交额', dataIndex: 'amount', width: 110,
      render: v => {
        if (v == null) return '-'
        const n = Number(v)
        if (n >= 1e8) return `${(n / 1e8).toFixed(2)}亿`
        if (n >= 1e4) return `${(n / 1e4).toFixed(1)}万`
        return String(n)
      },
    },
    {
      title: '更新时间', dataIndex: 'refreshed_at', width: 160,
      render: v => formatDateTime(v),
    },
    {
      title: '操作', key: 'action', width: 180, fixed: 'right',
      render: (_, r) => (
        <Space size="small">
          <Button size="small" onClick={() => handleViewIndicators(r)}>K线</Button>
          <Button size="small" type="primary" ghost onClick={() => handleAddUniverseToWatchlist(r)}>
            加自选
          </Button>
        </Space>
      ),
    },
  ]

  const handleRefreshPrices = () => {
    setPriceRefreshing(true)
    stocksApi.refreshPrices()
      .then((res) => {
        message.success(res?.message || '现价已刷新')
        loadWatchlist()
      })
      .catch((err) => message.error(err?.error || err?.message || '刷新现价失败'))
      .finally(() => setPriceRefreshing(false))
  }

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

  const handleViewIndicators = (codeOrRow, maybeName) => {
    const code = typeof codeOrRow === 'object' ? (codeOrRow.code || codeOrRow.stock_code) : codeOrRow
    const name = typeof codeOrRow === 'object'
      ? (codeOrRow.name || codeOrRow.stock_name || '')
      : (maybeName || '')
    const hits = typeof codeOrRow === 'object' ? (codeOrRow.hits || []) : []
    setIndicatorsCode(code)
    setIndicatorsName(name)
    setIndicatorsHits(hits)
    setIndicatorsModal(true)
    setIndicatorsLoading(true)
    setIndicatorsData(null)
    if (!code) {
      setIndicatorsLoading(false)
      message.error('股票代码为空，无法获取指标')
      return
    }
    stocksApi.indicators(code)
      .then(data => {
        if (data?.error) {
          message.error(data.error)
          setIndicatorsData({ indicators: {}, bars: [], note: data.error })
          return
        }
        setIndicatorsData(data)
      })
      .catch((err) => {
        const msg = err?.error || err?.message || '获取指标失败'
        message.error(typeof msg === 'string' ? msg : '获取指标失败')
        setIndicatorsData({ indicators: {}, bars: [], note: String(msg) })
      })
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
      title: '目标价', dataIndex: 'target_price', width: 90,
      render: (v) => (v == null || v === '' || Number(v) === 0 ? '-' : Number(v).toFixed(2)),
    },
    {
      title: '现价', dataIndex: 'current_price', width: 100,
      render: (v) => (v == null || v === '' ? '-' : Number(v).toFixed(2)),
    },
    {
      title: '盈亏', key: 'pnl', width: 140,
      render: (_, r) => {
        const buy = Number(r.buy_price)
        const cur = Number(r.current_price)
        if (!buy || !cur) return <span style={{ color: '#999' }}>-</span>
        const pct = (cur - buy) / buy * 100
        const qty = Number(r.quantity) || 0
        const amt = qty ? (cur - buy) * qty : null
        const color = pct > 0 ? '#cf1322' : pct < 0 ? '#3f8600' : '#666'
        return (
          <span style={{ color }}>
            {pct > 0 ? '+' : ''}{pct.toFixed(2)}%
            {amt != null ? ` / ${amt > 0 ? '+' : ''}${amt.toFixed(0)}` : ''}
          </span>
        )
      },
    },
    { title: '数量', dataIndex: 'quantity', width: 80, render: v => v ?? '-' },
    { title: '备注', dataIndex: 'notes', width: 160, ellipsis: true, render: v => v || '-' },
    { title: '添加时间', dataIndex: 'added_at', width: 160, render: v => formatDateTime(v) },
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
  const [patternRules, setPatternRules] = useState(screeningConditionsFallback)
  const [selectedConditions, setSelectedConditions] = useState([])
  const [matchMode, setMatchMode] = useState('and')
  const [minHits, setMinHits] = useState(1)
  const [maxStocks, setMaxStocks] = useState(300)
  const [screeningLoading, setScreeningLoading] = useState(false)
  const [screeningHistory, setScreeningHistory] = useState([])
  const [screeningResult, setScreeningResult] = useState(null)
  const [historyLoading, setHistoryLoading] = useState(false)
  const [activeScreeningId, setActiveScreeningId] = useState(null)
  const [ruleEditing, setRuleEditing] = useState(null)
  const [ruleParamsForm] = Form.useForm()
  const [activeStrategies, setActiveStrategies] = useState([])
  const [selectedStrategyId, setSelectedStrategyId] = useState(null)
  const [screenConfigOpen, setScreenConfigOpen] = useState(false)
  const [screenResultOpen, setScreenResultOpen] = useState(false)
  const screeningPollRef = useRef(null)
  const viewingResultIdRef = useRef(null)
  const ruleGroups = useMemo(() => groupPatternRules(patternRules), [patternRules])

  const toggleCondition = (label) => {
    setSelectedStrategyId(null)
    setSelectedConditions(prev => (
      prev.includes(label) ? prev.filter(x => x !== label) : [...prev, label]
    ))
  }

  const openRuleParams = (rule) => {
    const values = {}
    Object.entries(rule.params || {}).forEach(([key, value]) => {
      values[key] = Array.isArray(value) ? value.join(',') : value
    })
    setRuleEditing(rule)
    ruleParamsForm.setFieldsValue(values)
  }

  const saveRuleParams = () => {
    ruleParamsForm.validateFields().then(values => {
      const params = {}
      Object.entries(values).forEach(([key, value]) => {
        const original = ruleEditing?.params?.[key]
        if (Array.isArray(original)) {
          params[key] = String(value || '').split(',').map(x => Number(x.trim())).filter(Number.isFinite)
        } else {
          params[key] = value
        }
      })
      setPatternRules(list => list.map(r => r.key === ruleEditing.key ? { ...r, params } : r))
      setRuleEditing(null)
      message.success('参数已更新；点“保存为默认”可长期保存')
    })
  }

  const loadPatternRules = () => {
    stocksApi.patternRules()
      .then(res => {
        const rules = res?.rules || screeningConditionsFallback
        setPatternRules(rules)
        const enabled = rules.filter(r => r.enabled !== false).map(r => r.label || r.key)
        if (selectedConditions.length === 0) setSelectedConditions(enabled)
        if (res?.match_mode_default) setMatchMode(res.match_mode_default)
        if (res?.max_stocks_default) setMaxStocks(Number(res.max_stocks_default) || 300)
        if (res?.min_hits_default) setMinHits(Number(res.min_hits_default) || 1)
      })
      .catch(() => {})
  }

  const loadActiveStrategies = () => {
    stocksApi.activeStrategies()
      .then(res => setActiveStrategies(res?.list || []))
      .catch(() => setActiveStrategies([]))
  }

  const applyStrategyToScreening = (strategy, { switchTab = false } = {}) => {
    if (!strategy) {
      setSelectedStrategyId(null)
      return
    }
    const screenRules = strategy.screen_rules || []
    if (!screenRules.length && !(strategy.matched_labels || []).length) {
      message.warning(strategy.unmatched_hint || '该策略未识别出可用筛选条件，请先编辑补充关键词')
      return
    }
    if (screenRules.length) {
      setPatternRules(list => {
        const byKey = Object.fromEntries(screenRules.map(r => [r.key, r]))
        return list.map(r => {
          const hit = byKey[r.key]
          if (!hit) return { ...r, enabled: false }
          return {
            ...r,
            enabled: true,
            params: { ...(r.params || {}), ...(hit.params || {}) },
            label: hit.label || r.label,
          }
        })
      })
      setSelectedConditions(screenRules.map(r => r.label || r.key))
    } else {
      setSelectedConditions(strategy.matched_labels || [])
    }
    if (strategy.screen_match_mode) setMatchMode(strategy.screen_match_mode)
    if (strategy.screen_min_hits) setMinHits(Number(strategy.screen_min_hits) || 1)
    setSelectedStrategyId(strategy.id)
    message.success(`已应用策略「${strategy.name}」到筛选条件`)
    if (switchTab) {
      setActiveTab('screening')
      setScreenConfigOpen(true)
    }
  }

  const loadScreeningHistory = (opts = {}) => {
    const silent = !!opts.silent
    if (!silent) setHistoryLoading(true)
    stocksApi.screeningHistory()
      .then(res => setScreeningHistory(res?.list || res || []))
      .catch(() => {})
      .finally(() => { if (!silent) setHistoryLoading(false) })
  }

  const stopScreeningPoll = () => {
    if (screeningPollRef.current) {
      clearTimeout(screeningPollRef.current)
      screeningPollRef.current = null
    }
  }

  /** 后台轮询任务状态；仅当结果弹窗正查看同一任务时更新弹窗内容 */
  const pollScreening = (id) => {
    stopScreeningPoll()
    setActiveScreeningId(id)
    const tick = () => {
      stocksApi.getScreening(id).then(res => {
        if (viewingResultIdRef.current === id) {
          setScreeningResult(res)
        }
        if (res.status === 'running' || res.status === 'pending') {
          loadScreeningHistory({ silent: true })
          screeningPollRef.current = setTimeout(tick, 2500)
        } else {
          setScreeningLoading(false)
          setActiveScreeningId(prev => (prev === id ? null : prev))
          loadScreeningHistory({ silent: true })
          if (res.status === 'completed') {
            message.success(res.message || `筛选完成，命中 ${(res.results || []).length} 只`)
          } else if (res.status === 'cancelled') {
            message.info(res.message || '筛选已取消')
          } else {
            message.error(res.message || '筛选失败')
          }
        }
      }).catch(() => {
        setScreeningLoading(false)
        setActiveScreeningId(prev => (prev === id ? null : prev))
        message.error('轮询筛选结果失败')
      })
    }
    tick()
  }

  const closeScreenResult = () => {
    setScreenResultOpen(false)
    viewingResultIdRef.current = null
    setScreeningLoading(false)
  }

  const openScreeningResult = (id) => {
    viewingResultIdRef.current = id
    setScreenResultOpen(true)
    setScreeningResult(null)
    setScreeningLoading(true)
    stocksApi.getScreening(id).then(res => {
      setScreeningResult(res)
      setScreeningLoading(false)
      if (res.status === 'running' || res.status === 'pending') {
        pollScreening(id)
      }
    }).catch(() => {
      setScreeningLoading(false)
      message.error('加载筛选结果失败')
    })
  }

  const handleScreening = () => {
    // 不选条件 = 用后端默认启用规则
    const strategy = activeStrategies.find(s => s.id === selectedStrategyId)
    const scanLimit = maxStocks == null || maxStocks === '' ? 300 : Number(maxStocks)
    setScreenConfigOpen(false)
    setScreeningLoading(false)
    message.loading({ content: '正在提交筛选任务…', key: 'screen-submit', duration: 0 })
    stocksApi.screening({
      name: strategy ? `策略·${strategy.name}` : '技术面筛选',
      conditions: selectedConditions,
      rules: selectedConditions.length ? patternRules.map(r => ({
        ...r,
        enabled: selectedConditions.includes(r.label || r.key),
      })) : null,
      match_mode: matchMode,
      min_hits: minHits == null ? 1 : minHits,
      max_stocks: Number.isFinite(scanLimit) ? scanLimit : 300,
    })
      .then(res => {
        message.destroy('screen-submit')
        loadScreeningHistory()
        if (res.status === 'completed' && res.results) {
          message.success(res.message || '筛选完成')
        } else if (res.id) {
          message.info('筛选已在后台运行，可在历史中查看进度')
          pollScreening(res.id)
        }
      })
      .catch(err => {
        message.destroy('screen-submit')
        message.error(err?.error || '筛选失败')
      })
  }

  useEffect(() => () => stopScreeningPoll(), [])

  const addResultToWatch = (row) => {
    stocksApi.addStock({
      stock_code: row.code,
      stock_name: row.name,
      list_type: 'watch',
      current_price: row.close,
      notes: `筛选命中: ${(row.hits || []).join('、')}`,
    }).then(() => {
      message.success(`已加入自选 ${row.code}`)
      loadWatchlist()
    }).catch(() => message.error('加入自选失败'))
  }

  const noteFromStock = (row) => {
    stocksApi.note({
      stock_code: row.code,
      stock_name: row.name,
      content: `形态命中：${(row.hits || []).join('、')}\n收盘：${row.close} 涨跌：${row.pct_chg}%`,
    }).then(() => message.success('已写入知识库')).catch(err => message.error(err?.error || '写入失败'))
  }

  const screeningHistoryColumns = [
    { title: 'ID', dataIndex: 'id', width: 60 },
    { title: '名称', dataIndex: 'name', width: 140, ellipsis: true, render: v => v || '-' },
    {
      title: '条件', dataIndex: 'condition_labels', width: 280, ellipsis: true,
      render: (v, r) => (v && v.length ? v.join('、') : (r.message || '-')),
    },
    {
      title: '命中', dataIndex: 'matched', width: 80,
      render: v => (v != null ? <Tag color={v > 0 ? 'green' : 'default'}>{v}</Tag> : '-'),
    },
    {
      title: '状态', dataIndex: 'status', width: 90,
      render: v => (
        <Tag color={v === 'completed' ? 'green' : v === 'running' || v === 'pending' ? 'processing' : v === 'failed' ? 'red' : 'blue'}>
          {v === 'completed' ? '完成' : v === 'running' || v === 'pending' ? '扫描中' : v === 'failed' ? '失败' : (v || '-')}
        </Tag>
      ),
    },
    { title: '时间', dataIndex: 'created_at', width: 160, render: v => formatDateTime(v) },
    {
      title: '操作', width: 100, fixed: 'right',
      render: (_, r) => (
        <Button size="small" type="link" onClick={() => openScreeningResult(r.id)}>
          查看结果
        </Button>
      ),
    },
  ]

  const resultColumns = [
    { title: '代码', dataIndex: 'code', width: 90,
      render: (v, r) => <a onClick={() => handleViewIndicators(r)} style={{ color: '#1677ff' }}>{v}</a> },
    { title: '名称', dataIndex: 'name', width: 90 },
    { title: '收盘', dataIndex: 'close', width: 80 },
    {
      title: '涨跌%', dataIndex: 'pct_chg', width: 80,
      render: v => <span style={{ color: v > 0 ? '#cf1322' : v < 0 ? '#3f8600' : '#666' }}>{v}</span>,
    },
    { title: 'MA5', dataIndex: 'ma5', width: 72, render: v => v ?? '-' },
    { title: 'MA10', dataIndex: 'ma10', width: 72, render: v => v ?? '-' },
    { title: 'MA20', dataIndex: 'ma20', width: 72, render: v => v ?? '-' },
    { title: 'MA30', dataIndex: 'ma30', width: 72, render: v => v ?? '-' },
    { title: 'MA60', dataIndex: 'ma60', width: 72, render: v => v ?? '-' },
    { title: '年线', dataIndex: 'ma250', width: 80, render: v => v ?? '-' },
    {
      title: '命中形态', dataIndex: 'hits', width: 260,
      render: v => (
        <Space size={[4, 4]} wrap>
          {(v || []).length
            ? (v || []).map(h => <Tag key={h} color="blue" style={{ margin: 0 }}>{h}</Tag>)
            : '-'}
        </Space>
      ),
    },
    { title: '命中数', dataIndex: 'hit_count', width: 70 },
    {
      title: '操作', width: 180, fixed: 'right',
      render: (_, r) => (
        <Space size="small">
          <Button size="small" onClick={() => addResultToWatch(r)}>自选</Button>
          <Button size="small" onClick={() => noteFromStock(r)}>笔记</Button>
          <Button size="small" type="link" onClick={() => handleViewIndicators(r)}>K线/指标</Button>
        </Space>
      ),
    },
  ]

  // === Tab 3: AI策略 ===
  const [strategies, setStrategies] = useState([])
  const [strategiesLoading, setStrategiesLoading] = useState(true)
  const [strategyModal, setStrategyModal] = useState(false)
  const [strategyEditing, setStrategyEditing] = useState(null)
  const [strategyForm] = Form.useForm()
  const [strategyParsePreview, setStrategyParsePreview] = useState(null)

  const loadStrategies = () => {
    setStrategiesLoading(true)
    stocksApi.strategies()
      .then(res => setStrategies(res?.list || res || []))
      .catch(() => message.error('加载策略失败'))
      .finally(() => setStrategiesLoading(false))
  }

  useEffect(() => {
    loadPatternRules()
    loadScreeningHistory()
    loadActiveStrategies()
  }, [])

  useEffect(() => {
    if (activeTab === 'strategy') loadStrategies()
    if (activeTab === 'screening') {
      loadScreeningHistory()
      loadActiveStrategies()
    }
  }, [activeTab])

  const previewStrategyText = (text) => {
    const t = (text || '').trim()
    if (!t) {
      setStrategyParsePreview(null)
      return
    }
    stocksApi.parseStrategy({ text: t })
      .then(res => setStrategyParsePreview(res))
      .catch(() => setStrategyParsePreview(null))
  }

  const handleStrategySave = () => {
    strategyForm.validateFields().then(values => {
      const payload = {
        ...values,
        rules_text: (values.rules_text || '').trim(),
      }
      delete payload.rules_text
      // 仍传 rules_text 给后端编译
      payload.rules_text = (values.rules_text || '').trim()
      const req = strategyEditing
        ? stocksApi.updateStrategy(strategyEditing.id, payload)
        : stocksApi.createStrategy(payload)
      req.then((res) => {
        message.success(strategyEditing ? '策略已更新' : '策略已创建')
        setStrategyModal(false)
        loadStrategies()
        loadActiveStrategies()
        const st = res?.strategy
        if (st && !(st.matched_labels || []).length) {
          message.warning(st.unmatched_hint || '未识别到筛选条件，启用后暂无法用于选股')
        } else if (st?.matched_labels?.length) {
          message.info(`已识别筛选条件：${st.matched_labels.join('、')}`)
        }
      }).catch(() => message.error('保存失败'))
    })
  }

  const openStrategyModal = (record = null) => {
    setStrategyEditing(record)
    if (record) {
      const text = record.rules_text || rulesToText(record.rules_json)
      strategyForm.setFieldsValue({
        ...record,
        rules_text: text,
      })
      previewStrategyText(text)
    } else {
      strategyForm.resetFields()
      strategyForm.setFieldsValue({ strategy_type: 'trend', status: 'active' })
      setStrategyParsePreview(null)
    }
    setStrategyModal(true)
  }

  const strategyColumns = [
    { title: 'ID', dataIndex: 'id', width: 60 },
    { title: '名称', dataIndex: 'name', width: 140, ellipsis: true },
    {
      title: '类型', dataIndex: 'strategy_type', width: 80,
      render: v => <Tag color={strategyTypeColors[v]}>{strategyTypeLabels[v] || v}</Tag>,
    },
    {
      title: '文字规则', dataIndex: 'rules_json', width: 220, ellipsis: true,
      render: (v, r) => <Tooltip title={<span style={{ whiteSpace: 'pre-wrap' }}>{r.rules_text || rulesToText(v) || '-'}</span>}>
        <span>{rulesPreview(r.rules_text || v)}</span>
      </Tooltip>,
    },
    {
      title: '对应筛选条件', dataIndex: 'matched_labels', width: 220,
      render: (v, r) => {
        const labels = matchedLabelsOf(r)
        if (!labels.length) return <span style={{ color: '#999' }}>未识别</span>
        return labels.map(l => <Tag key={l} color="blue">{l}</Tag>)
      },
    },
    {
      title: '状态', dataIndex: 'status', width: 80,
      render: v => <Tag color={v === 'active' ? 'green' : 'default'}>{v === 'active' ? '启用' : '停用'}</Tag>,
    },
    {
      title: '操作', key: 'action', width: 220, fixed: 'right',
      render: (_, r) => (
        <Space size="small">
          <Button size="small" type="link" disabled={r.status !== 'active' || !matchedLabelsOf(r).length}
            onClick={() => applyStrategyToScreening(r, { switchTab: true })}>
            去筛选
          </Button>
          <Tooltip title="编辑">
            <Button size="small" icon={<EditOutlined />} onClick={() => openStrategyModal(r)} />
          </Tooltip>
          <Popconfirm title="确认删除？" onConfirm={() => {
            stocksApi.deleteStrategy(r.id).then(() => {
              message.success('已删除'); loadStrategies(); loadActiveStrategies()
            }).catch(() => message.error('删除失败'))
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
    // 允许只基于系统持仓复盘；有文字更好
    setReviewLoading(true)
    stocksApi.review({ input: reviewText })
      .then(res => {
        message.success('AI复盘完成')
        setReviewResult(res?.review || res)
      })
      .catch((err) => message.error(err?.error || '复盘失败'))
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
              <Space>
                <Button icon={<ReloadOutlined />} onClick={() => loadWatchlist()}>刷新列表</Button>
                <Tooltip title="拉取最新行情，更新现价与盈亏（交易日 15:00 也会自动刷新）">
                  <Button
                    type="primary"
                    ghost
                    icon={<ReloadOutlined />}
                    loading={priceRefreshing}
                    onClick={handleRefreshPrices}
                  >
                    刷新现价
                  </Button>
                </Tooltip>
              </Space>
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
              <Row gutter={16}>
                <Col span={12}>
                  <Form.Item name="target_price" label="目标价（预警）">
                    <InputNumber style={{ width: '100%' }} precision={2} placeholder="跌到此价提醒" />
                  </Form.Item>
                </Col>
                <Col span={12}>
                  <Form.Item name="alert_below_cost" label="跌破成本提醒" valuePropName="checked" initialValue={true}>
                    <Switch checkedChildren="开" unCheckedChildren="关" />
                  </Form.Item>
                </Col>
              </Row>
              <Form.Item name="alert_on_target" label="触及目标价提醒" valuePropName="checked" initialValue={true}>
                <Switch checkedChildren="开" unCheckedChildren="关" />
              </Form.Item>
              <Form.Item name="notes" label="备注">
                <Input.TextArea rows={2} placeholder="添加备注信息..." />
              </Form.Item>
            </Form>
          </Modal>
        </div>
      ),
    },

    // Tab: 全部股票
    {
      key: 'universe',
      label: <span><UnorderedListOutlined /> 全部股票</span>,
      children: (
        <div>
          <Alert
            type="info"
            showIcon
            style={{ marginBottom: 12 }}
            message={`全市场 A 股库（活跃 ${universe.active_total || universe.total || 0} 只）`}
            description={
              <span>
                交易日默认 18:00 自动全量同步：更新行情、新股自动入库。
                {universe.last_refresh_at ? ` 上次同步：${universe.last_refresh_at}` : ' 尚未同步，请点「立即同步」。'}
              </span>
            }
          />
          <div className="table-toolbar" style={{ marginBottom: 16 }}>
            <div className="table-toolbar-left">
              <Space wrap>
                <Input.Search
                  placeholder="代码/名称"
                  allowClear
                  style={{ width: 200 }}
                  value={universeFilters.q}
                  onChange={e => setUniverseFilters({ ...universeFilters, q: e.target.value })}
                  onSearch={v => {
                    const next = { ...universeFilters, q: v }
                    setUniverseFilters(next)
                    loadUniverse(1, next)
                  }}
                />
                <Select
                  allowClear
                  placeholder="板块"
                  style={{ width: 130 }}
                  value={universeFilters.board}
                  onChange={v => {
                    const next = { ...universeFilters, board: v }
                    setUniverseFilters(next)
                    loadUniverse(1, next)
                  }}
                  options={[
                    { value: '沪市主板', label: '沪市主板' },
                    { value: '深市主板', label: '深市主板' },
                    { value: '创业板', label: '创业板' },
                    { value: '科创板', label: '科创板' },
                  ]}
                />
                <Select
                  style={{ width: 130 }}
                  value={universeFilters.sort || 'code'}
                  onChange={v => {
                    const next = { ...universeFilters, sort: v }
                    setUniverseFilters(next)
                    loadUniverse(1, next)
                  }}
                  options={[
                    { value: 'code', label: '按代码' },
                    { value: 'pct', label: '按涨跌幅' },
                    { value: 'amount', label: '按成交额' },
                    { value: 'price', label: '按现价' },
                    { value: 'time', label: '按更新时间' },
                  ]}
                />
                <Button icon={<ReloadOutlined />} onClick={() => loadUniverse(universePage, universeFilters)}>
                  刷新列表
                </Button>
              </Space>
            </div>
            <Tooltip title="从东财拉取全部 A 股并入库（新股会自动添加，可能需要 1～2 分钟）">
              <Button
                type="primary"
                icon={<ReloadOutlined />}
                loading={universeRefreshing}
                onClick={handleRefreshUniverse}
              >
                立即同步全市场
              </Button>
            </Tooltip>
          </div>
          <Table
            columns={universeColumns}
            dataSource={universe.list || []}
            rowKey="code"
            loading={universeLoading || universeRefreshing}
            scroll={{ x: 1000 }}
            size="middle"
            pagination={{
              current: universePage,
              total: universe.total || 0,
              pageSize: 20,
              showTotal: t => `共 ${t} 条`,
              onChange: p => loadUniverse(p, universeFilters),
            }}
          />
        </div>
      ),
    },

    // Tab 2: 条件筛选 — 主界面为历史；配置与结果用弹窗
    {
      key: 'screening',
      label: <span><SearchOutlined /> 条件筛选</span>,
      children: (
        <div className="stocks-screen">
          <div className="table-toolbar" style={{ marginBottom: 0 }}>
            <div className="table-toolbar-left">
              <Button icon={<ReloadOutlined />} onClick={loadScreeningHistory}>刷新</Button>
              {activeScreeningId ? (
                <Tag color="processing">任务 #{activeScreeningId} 扫描中</Tag>
              ) : (
                <span style={{ color: '#64748b', fontSize: 13 }}>
                  历史记录一览；点「查看结果」打开详情，点右侧开始新筛选
                </span>
              )}
            </div>
            <Space>
              {activeScreeningId && (
                <Button size="small" danger onClick={() => {
                  stocksApi.cancelScreening(activeScreeningId).then(() => {
                    message.info('已取消')
                    stopScreeningPoll()
                    setScreeningLoading(false)
                    setActiveScreeningId(null)
                    loadScreeningHistory()
                  }).catch(() => message.error('取消失败'))
                }}>取消任务</Button>
              )}
              <Button
                type="primary"
                icon={<FundOutlined />}
                onClick={() => {
                  loadPatternRules()
                  loadActiveStrategies()
                  setScreenConfigOpen(true)
                }}
              >
                技术面筛选
              </Button>
            </Space>
          </div>

          <div className="stocks-screen-panel">
            <div className="stocks-screen-panel-bd" style={{ paddingTop: 12 }}>
              <Table
                columns={screeningHistoryColumns}
                dataSource={screeningHistory}
                rowKey="id"
                loading={historyLoading}
                scroll={{ x: 900 }}
                size="middle"
                pagination={{ pageSize: 15, showTotal: (t) => `共 ${t} 条` }}
                locale={{ emptyText: <Empty description="暂无筛选历史，点击右上角「技术面筛选」开始" /> }}
              />
            </div>
          </div>

          {/* 技术面筛选配置弹窗 */}
          <Modal
            title="技术面筛选"
            open={screenConfigOpen}
            onCancel={() => setScreenConfigOpen(false)}
            width={720}
            destroyOnClose={false}
            className="stocks-screen-modal"
            footer={
              <div className="stocks-screen-footer">
                <Space wrap>
                  <Button onClick={() => {
                    setSelectedConditions(['多周期均线全部朝上', '近1个月有涨停'])
                    setMatchMode('and')
                    setMinHits(2)
                  }}>趋势+涨停</Button>
                  <Button onClick={() => {
                    const enabled = patternRules.filter(r => r.enabled !== false).map(r => r.label || r.key)
                    setSelectedConditions(enabled)
                  }}>恢复默认</Button>
                  <Button onClick={() => {
                    const next = patternRules.map(r => ({
                      ...r,
                      enabled: selectedConditions.includes(r.label || r.key),
                    }))
                    const scanLimit = maxStocks == null ? 300 : Number(maxStocks)
                    stocksApi.savePatternRules({
                      rules: next,
                      match_mode: matchMode,
                      min_hits: minHits == null ? 1 : minHits,
                      max_stocks: Number.isFinite(scanLimit) ? scanLimit : 300,
                    }).then(() => {
                      setPatternRules(next)
                      if (maxStocks == null) setMaxStocks(300)
                      message.success('已保存为默认')
                    }).catch(() => message.error('保存失败'))
                  }}>保存默认</Button>
                  <Button type="link" onClick={() => setSelectedConditions([])}>清空条件</Button>
                </Space>
                <Button type="primary" icon={<SearchOutlined />} onClick={handleScreening}>
                  开始筛选
                </Button>
              </div>
            }
          >
            <div className="stocks-screen-modal-body">
              <div className="stocks-screen-form">
                <div className="stocks-screen-field">
                  <label>匹配方式</label>
                  <Select
                    value={matchMode}
                    onChange={setMatchMode}
                    options={[
                      { value: 'or', label: '命中任一（初筛）' },
                      { value: 'min', label: '至少 N 条' },
                      { value: 'and', label: '全部命中（精筛）' },
                    ]}
                  />
                </div>
                {matchMode === 'min' && (
                  <div className="stocks-screen-field stocks-screen-field-sm">
                    <label>最少命中</label>
                    <InputNumber
                      min={1}
                      max={12}
                      value={minHits}
                      onChange={v => setMinHits(v)}
                      onBlur={() => { if (minHits == null) setMinHits(1) }}
                      style={{ width: '100%' }}
                    />
                  </div>
                )}
                <div className="stocks-screen-field stocks-screen-field-sm">
                  <label>扫描上限</label>
                  <InputNumber
                    min={0}
                    max={6000}
                    step={50}
                    value={maxStocks}
                    onChange={v => setMaxStocks(v)}
                    onBlur={() => { if (maxStocks == null) setMaxStocks(300) }}
                    placeholder="300"
                    style={{ width: '100%' }}
                  />
                  <span className="hint">0 = 全市场（较慢）；可清空后改数字</span>
                </div>
                <div className="stocks-screen-field stocks-screen-field-grow">
                  <label>AI 策略（可选）</label>
                  <Space.Compact style={{ width: '100%' }}>
                    <Select
                      allowClear
                      placeholder={activeStrategies.length ? '选择已启用策略' : '暂无启用策略'}
                      style={{ width: '100%' }}
                      value={selectedStrategyId}
                      options={activeStrategies.map(s => ({
                        value: s.id,
                        label: `${s.name}${matchedLabelsOf(s).length ? `（${matchedLabelsOf(s).join('、')}）` : ''}`,
                        disabled: !matchedLabelsOf(s).length,
                      }))}
                      onChange={(id) => {
                        if (!id) {
                          setSelectedStrategyId(null)
                          return
                        }
                        applyStrategyToScreening(activeStrategies.find(s => s.id === id))
                      }}
                    />
                    <Button onClick={() => {
                      setScreenConfigOpen(false)
                      setActiveTab('strategy')
                    }}>管理</Button>
                  </Space.Compact>
                </div>
              </div>

              <div className="stocks-screen-conditions-hd">
                <span>筛选条件</span>
                <Tag>{selectedConditions.length} 条已选</Tag>
              </div>

              {ruleGroups.map(group => (
                <div key={group.key} className="stocks-rule-group">
                  <div className="stocks-rule-group-title">{group.title}</div>
                  <div className="stocks-rule-list">
                    {group.items.map(c => {
                      const label = c.label || c.key
                      const on = selectedConditions.includes(label)
                      return (
                        <div
                          key={c.key || label}
                          className={`stocks-rule-row${on ? ' is-on' : ''}`}
                          onClick={() => toggleCondition(label)}
                        >
                          <Checkbox checked={on} onClick={e => e.stopPropagation()} onChange={() => toggleCondition(label)} />
                          <div className="stocks-rule-row-main">
                            <div className="name">{label}</div>
                            {c.desc ? <div className="desc">{c.desc}</div> : null}
                          </div>
                          {Object.keys(c.params || {}).length > 0 && (
                            <Tooltip title="调整参数">
                              <Button
                                size="small"
                                type="text"
                                icon={<SettingOutlined />}
                                onClick={(e) => {
                                  e.stopPropagation()
                                  openRuleParams(c)
                                }}
                              />
                            </Tooltip>
                          )}
                        </div>
                      )
                    })}
                  </div>
                </div>
              ))}
            </div>
          </Modal>

          <Modal
            title={`调整规则参数 - ${ruleEditing?.label || ''}`}
            open={!!ruleEditing}
            onOk={saveRuleParams}
            onCancel={() => setRuleEditing(null)}
            destroyOnClose
            zIndex={1100}
          >
            <Form form={ruleParamsForm} layout="vertical" style={{ marginTop: 16 }}>
              {Object.entries(ruleEditing?.params || {}).map(([key, value]) => (
                <Form.Item key={key} name={key} label={paramLabels[key] || key}
                  rules={[{ required: true, message: '不能为空' }]}>
                  {Array.isArray(value)
                    ? <Input placeholder="例如：5,10,20,30,60,250" />
                    : <InputNumber style={{ width: '100%' }} precision={Number.isInteger(value) ? 0 : 3} />}
                </Form.Item>
              ))}
            </Form>
            <div style={{ color: '#888' }}>{ruleEditing?.desc}</div>
          </Modal>

          {/* 筛选结果弹窗 */}
          <Modal
            title={
              <Space>
                <ThunderboltOutlined style={{ color: '#f59e0b' }} />
                <span>筛选结果</span>
                {screeningResult && (
                  <Tag color={(screeningResult.results || []).length ? 'green' : 'default'}>
                    {(screeningResult.results || []).length} 只
                  </Tag>
                )}
              </Space>
            }
            open={screenResultOpen}
            onCancel={closeScreenResult}
            width={1100}
            footer={
              <Button type="primary" onClick={closeScreenResult}>关闭</Button>
            }
            destroyOnClose={false}
            className="stocks-screen-modal"
            maskClosable
          >
            {!screeningResult ? (
              <Empty description="加载中…" />
            ) : (
              <div>
                <div style={{ marginBottom: 12, color: '#64748b', fontSize: 13 }}>
                  {screeningResult.message || screeningResult.status || ''}
                  {screeningResult.name ? ` · ${screeningResult.name}` : ''}
                </div>
                <div className="stocks-result-summary">
                  <div className="stat">
                    <div className="k">命中股票</div>
                    <div className="v">{(screeningResult.results || []).length}</div>
                  </div>
                  <div className="stat">
                    <div className="k">状态</div>
                    <div className="v" style={{ fontSize: 14, paddingTop: 4 }}>
                      {screeningResult.status === 'completed' ? '完成'
                        : (screeningResult.status === 'running' || screeningResult.status === 'pending') ? '扫描中'
                          : (screeningResult.status || '-')}
                    </div>
                  </div>
                </div>
                {!!(screeningResult.rule_stats || []).length && (
                  <div className="stocks-hit-tags">
                    {(screeningResult.rule_stats || []).map(s => (
                      <Tag key={s.key} color={s.hits > 0 ? 'blue' : 'default'}>
                        {s.label} · {s.hits}
                      </Tag>
                    ))}
                  </div>
                )}
                <Table
                  columns={resultColumns}
                  dataSource={screeningResult.results || []}
                  rowKey={(r) => r.code || r.id}
                  size="small"
                  scroll={{ x: 1100, y: 420 }}
                  pagination={{ pageSize: 20, showTotal: t => `共 ${t} 条` }}
                  locale={{
                    emptyText: (screeningResult.status === 'running' || screeningResult.status === 'pending')
                      ? '扫描中'
                      : '暂无命中',
                  }}
                />
              </div>
            )}
          </Modal>
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
              <span style={{ color: '#888', marginLeft: 12 }}>
                用白话写选股经验 → 自动识别筛选条件；启用后可在「条件筛选」里选用
              </span>
            </div>
            <Button type="primary" icon={<PlusOutlined />} onClick={() => openStrategyModal()}>
              创建策略
            </Button>
          </div>

          <Table
            columns={strategyColumns}
            dataSource={strategies}
            rowKey="id"
            loading={strategiesLoading}
            scroll={{ x: 1000 }}
            size="middle"
            pagination={{ pageSize: 15, showTotal: (t) => `共 ${t} 条` }}
          />

          <Modal
            title={strategyEditing ? '编辑策略' : '创建策略'}
            open={strategyModal}
            onOk={handleStrategySave}
            onCancel={() => setStrategyModal(false)}
            width={680}
            okText="保存"
          >
            <Form form={strategyForm} layout="vertical" style={{ marginTop: 16 }}>
              <Row gutter={16}>
                <Col span={12}>
                  <Form.Item name="name" label="策略名称" rules={[{ required: true, message: '请输入策略名称' }]}>
                    <Input placeholder="如：均线多头放量突破" />
                  </Form.Item>
                </Col>
                <Col span={12}>
                  <Form.Item name="strategy_type" label="策略类型" initialValue="trend">
                    <Select options={strategyTypeOptions} />
                  </Form.Item>
                </Col>
              </Row>
              <Form.Item name="description" label="一句话说明">
                <Input.TextArea rows={2} placeholder="例如：适合趋势行情，回撤可控后再加仓" />
              </Form.Item>
              <Form.Item
                name="rules_text"
                label="策略规则（文字描述）"
                rules={[{ required: true, message: '请用文字写清楚买卖/选股规则' }]}
                extra="尽量包含关键词：均线多头、放量、突破、涨停、MACD金叉、KDJ金叉、RSI低位、布林下轨、回踩支撑、多周期均线朝上"
              >
                <Input.TextArea
                  rows={9}
                  placeholder={STRATEGY_RULE_EXAMPLE}
                  style={{ fontFamily: 'inherit' }}
                  onChange={(e) => previewStrategyText(e.target.value)}
                />
              </Form.Item>
              <Space wrap style={{ marginBottom: 12 }}>
                <Button
                  type="link"
                  style={{ padding: 0 }}
                  onClick={() => {
                    strategyForm.setFieldsValue({ rules_text: STRATEGY_RULE_EXAMPLE })
                    previewStrategyText(STRATEGY_RULE_EXAMPLE)
                  }}
                >
                  填入示例规则
                </Button>
                <Button type="link" style={{ padding: 0 }} onClick={() => {
                  previewStrategyText(strategyForm.getFieldValue('rules_text'))
                }}>
                  预览识别结果
                </Button>
              </Space>
              {strategyParsePreview && (
                <Card size="small" style={{ marginBottom: 12, background: '#fafafa' }}
                  title="将用于筛选的条件">
                  {(strategyParsePreview.matched_labels || []).length ? (
                    <>
                      {(strategyParsePreview.matched_labels || []).map(l => (
                        <Tag key={l} color="blue">{l}</Tag>
                      ))}
                      <div style={{ marginTop: 8, color: '#666' }}>
                        匹配模式：{strategyParsePreview.match_mode === 'or' ? '命中任一'
                          : strategyParsePreview.match_mode === 'min' ? `至少${strategyParsePreview.min_hits}条`
                            : '全部命中'}
                      </div>
                    </>
                  ) : (
                    <span style={{ color: '#cf1322' }}>
                      {strategyParsePreview.unmatched_hint || '未识别到可用条件'}
                    </span>
                  )}
                </Card>
              )}
              <Form.Item name="status" label="状态" initialValue="active"
                extra="只有「启用」的策略才会出现在条件筛选里">
                <Select options={[
                  { value: 'active', label: '启用（可在筛选中使用）' },
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
              <Card title="复盘说明 / 持仓提问" size="small">
                <Input.TextArea
                  rows={8}
                  value={reviewText}
                  onChange={e => setReviewText(e.target.value)}
                  placeholder={'支持两种写法：\n1）今日买卖：买入/卖出代码、价格、理由\n2）持仓咨询：如“紫光国微浮亏30%，继续拿还是减？”\n\n也可先把股票加到自选「持仓」，再直接点复盘。'}
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
                    {reviewResult.situation_summary ? (
                      <ReviewFieldText value={reviewResult.situation_summary} />
                    ) : (
                      <div style={{ color: '#888', fontSize: 13 }}>已生成分析结果，见下方分项</div>
                    )}
                  </Card>
                  {reviewResult.position_view && (
                    <Card title="持仓看法" size="small" style={{ marginBottom: 12 }}>
                      <ReviewFieldText value={reviewResult.position_view} />
                    </Card>
                  )}
                  {reviewResult.next_actions && (
                    <Card title="下一步怎么操作" size="small" style={{ marginBottom: 12 }}>
                      <ReviewFieldText value={reviewResult.next_actions} />
                    </Card>
                  )}
                  {reviewResult.risk_warning && (
                    <Card title="风险提示" size="small" style={{ marginBottom: 12 }}>
                      <ReviewFieldText value={reviewResult.risk_warning} danger />
                    </Card>
                  )}
                  {reviewResult.success_trades && (
                    <Card title="成功交易" size="small" style={{ marginBottom: 12 }}>
                      <ReviewFieldText value={reviewResult.success_trades} />
                    </Card>
                  )}
                  {reviewResult.failure_trades && (
                    <Card title="失败交易" size="small" style={{ marginBottom: 12 }}>
                      <ReviewFieldText value={reviewResult.failure_trades} />
                    </Card>
                  )}
                  {reviewResult.reason_analysis && (
                    <Card title="原因分析" size="small" style={{ marginBottom: 12 }}>
                      <ReviewFieldText value={reviewResult.reason_analysis} />
                    </Card>
                  )}
                  {reviewResult.strategy_suggestions && (
                    <Card title="策略建议" size="small" style={{ marginBottom: 12 }}>
                      <ReviewFieldText value={reviewResult.strategy_suggestions} />
                    </Card>
                  )}
                  {reviewResult.win_rate_trend && (
                    <Card title="后续观察" size="small" style={{ marginBottom: 12 }}>
                      <ReviewFieldText value={reviewResult.win_rate_trend} />
                    </Card>
                  )}
                </div>
              ) : (
                <Card size="small" style={{ minHeight: 240, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                  <Empty description={'可写持仓问题或今日交易，然后点"AI复盘"'} />
                </Card>
              )}
            </Col>
          </Row>
        </div>
      ),
    },
  ]

  return (
    <div className="stocks-page">
      <div className="page-title">股票研究</div>
      <div className="page-desc">
        自选跟踪、全市场浏览、技术筛选与 AI 策略复盘，辅助研究判断（不构成投资建议）。
      </div>
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
          {!!indicatorsHits.length && (
            <div style={{ marginBottom: 12 }}>
              <span style={{ color: '#888', marginRight: 8 }}>筛选命中：</span>
              {indicatorsHits.map(h => <Tag key={h} color="blue">{h}</Tag>)}
            </div>
          )}
          {Object.keys(indicatorsData?.indicators || {}).length > 0 ? (
            <div>
              {indicatorsData.close != null && (
                <div style={{ marginBottom: 12, fontSize: 15 }}>
                  收盘 <b>{indicatorsData.close}</b>
                  <span style={{
                    marginLeft: 12,
                    color: (indicatorsData.pct_hint || 0) > 0 ? '#cf1322'
                      : (indicatorsData.pct_hint || 0) < 0 ? '#3f8600' : '#666',
                  }}>
                    {indicatorsData.pct_hint > 0 ? '+' : ''}{indicatorsData.pct_hint}%
                  </span>
                </div>
              )}
              <KLineChart bars={indicatorsData.bars || []} />
              <Divider>最新技术指标</Divider>
              {Object.entries(indicatorsData.indicators).map(([key, value]) => (
                <Row key={key} gutter={16} style={{ marginBottom: 10 }}>
                  <Col span={4} style={{ fontWeight: 600 }}>{INDICATOR_LABELS[key] || key}</Col>
                  <Col span={20}>
                    {typeof value === 'object'
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
            <Empty description={indicatorsData?.note || '暂无指标数据，请稍后重试'} style={{ padding: 32 }} />
          ) : null}
        </Spin>
      </Modal>
    </div>
  )
}
