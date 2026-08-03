import { useEffect, useState } from 'react'
import {
  Alert,
  Button,
  Card,
  Checkbox,
  Col,
  Divider,
  Empty,
  Form,
  Input,
  InputNumber,
  Modal,
  Popconfirm,
  Row,
  Select,
  Space,
  Spin,
  Table,
  Tabs,
  Tag,
  Tooltip,
  message,
} from 'antd'
import {
  AimOutlined,
  DeleteOutlined,
  EditOutlined,
  FundOutlined,
  LineChartOutlined,
  PlusOutlined,
  ReloadOutlined,
  RobotOutlined,
  SearchOutlined,
  SettingOutlined,
  StarOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons'
import { stocksApi } from '../../api'

const listTypeOptions = [
  { value: 'watch', label: '关注' },
  { value: 'observe', label: '观察' },
  { value: 'holding', label: '持仓' },
  { value: 'history', label: '历史' },
  { value: 'all', label: '全部' },
]

const listTypeColors = {
  holding: 'red',
  watch: 'blue',
  observe: 'orange',
  history: 'default',
  all: 'purple',
}

const listTypeLabels = {
  holding: '持仓',
  watch: '关注',
  observe: '观察',
  history: '历史',
  all: '全部',
}

const strategyTypeOptions = [
  { value: 'trend', label: '趋势' },
  { value: 'breakout', label: '突破' },
  { value: 'rebound', label: '反弹' },
  { value: 'leader', label: '龙头' },
]

const strategyTypeColors = {
  trend: 'blue',
  breakout: 'green',
  rebound: 'orange',
  leader: 'red',
}

const strategyTypeLabels = {
  trend: '趋势',
  breakout: '突破',
  rebound: '反弹',
  leader: '龙头',
}

const INDICATOR_LABELS = {
  MACD: 'MACD',
  KDJ: 'KDJ',
  RSI: 'RSI',
  MA: '均线',
  BOLL: '布林带',
  VOLUME: '成交量',
  TREND: '趋势',
}

const screeningConditionsFallback = [
  {
    key: 'ma_all_rising',
    label: '多周期均线全部朝上',
    enabled: true,
    params: { periods: [5, 10, 20, 30, 60, 250], slope_days: 3 },
    desc: 'MA5/10/20/30/60/年线均高于N个交易日前',
  },
  {
    key: 'recent_limit_up',
    label: '近1个月有涨停',
    enabled: true,
    params: { lookback: 22 },
    desc: '近N个交易日出现过涨停（自动区分5%/10%/20%）',
  },
  {
    key: 'macd_golden_cross',
    label: 'MACD金叉',
    alias: 'macd',
    enabled: false,
    params: {},
    desc: '昨日 DIF≤DEA，今日 DIF>DEA',
  },
  {
    key: 'ma_bullish',
    label: '均线多头排列',
    enabled: false,
    params: { fast: 5, mid: 10, slow: 20 },
    desc: 'MA快 > MA中 > MA慢',
  },
  {
    key: 'volume_increase',
    label: '成交量放大',
    alias: 'volume',
    enabled: false,
    params: { ratio: 1.5, base: 5 },
    desc: '今日量 > 近N日均量 × 倍数',
  },
  {
    key: 'breakthrough',
    label: '突破平台',
    enabled: false,
    params: { lookback: 20 },
    desc: '收盘创近 N 日新高',
  },
  {
    key: 'rsi_low',
    label: 'RSI低位',
    alias: 'rsi',
    enabled: false,
    params: { period: 6, threshold: 30 },
    desc: 'RSI 低于阈值（超卖区）',
  },
  {
    key: 'boll_lower',
    label: '触及布林下轨',
    alias: 'boll',
    enabled: false,
    params: {},
    desc: '收盘 ≤ 布林下轨',
  },
  {
    key: 'kdj_golden_cross',
    label: 'KDJ金叉',
    alias: 'kdj',
    enabled: false,
    params: {},
    desc: '昨日 K≤D，今日 K>D',
  },
  {
    key: 'pullback_support',
    label: '回踩支撑',
    alias: 'pullback',
    enabled: false,
    params: { ma: 20, tol: 0.02 },
    desc: '价格回踩均线附近且未有效跌破',
  },
]

function numOrNull(value) {
  // JSON null would become 0 through Number(null), which corrupts chart scaling.
  if (value === null || value === undefined || value === '') return null
  const num = Number(value)
  return Number.isFinite(num) ? num : null
}

function formatValue(value, digits = 2) {
  const num = numOrNull(value)
  return num == null ? '-' : num.toFixed(digits)
}

function normalizeList(response) {
  if (Array.isArray(response)) return response
  if (Array.isArray(response?.list)) return response.list
  if (Array.isArray(response?.data)) return response.data
  return []
}

function normalizeRules(rules) {
  const source = Array.isArray(rules) && rules.length ? rules : screeningConditionsFallback
  return source.map((rule) => ({
    key: rule.key || rule.value || rule.label,
    label: rule.label || rule.name || rule.key,
    enabled: Boolean(rule.enabled),
    params: rule.params && typeof rule.params === 'object' ? rule.params : {},
    desc: rule.desc || rule.description || '',
    alias: rule.alias,
  })).filter((rule) => rule.key)
}

function parseMaybeJson(value, fallback) {
  if (value == null || value === '') return fallback
  if (typeof value !== 'string') return value
  try {
    return JSON.parse(value)
  } catch {
    return fallback
  }
}

function stockCodeOf(row) {
  return row?.stock_code || row?.code || row?.symbol || ''
}

function stockNameOf(row) {
  return row?.stock_name || row?.name || ''
}

function KLineChart({ bars = [] }) {
  const maKeys = ['MA5', 'MA10', 'MA20', 'MA30', 'MA60', 'MA250']
  const maColors = {
    MA5: '#fa8c16',
    MA10: '#722ed1',
    MA20: '#1677ff',
    MA30: '#13c2c2',
    MA60: '#eb2f96',
    MA250: '#595959',
  }
  const raw = Array.isArray(bars) ? bars : []
  const data = raw
    .map((bar, index) => ({
      ...bar,
      __index: index,
      open: numOrNull(bar.open),
      high: numOrNull(bar.high),
      low: numOrNull(bar.low),
      close: numOrNull(bar.close),
      MA5: numOrNull(bar.MA5 ?? bar.ma5),
      MA10: numOrNull(bar.MA10 ?? bar.ma10),
      MA20: numOrNull(bar.MA20 ?? bar.ma20),
      MA30: numOrNull(bar.MA30 ?? bar.ma30),
      MA60: numOrNull(bar.MA60 ?? bar.ma60),
      MA250: numOrNull(bar.MA250 ?? bar.ma250),
    }))
    .filter((bar) => (
      bar.open != null
      && bar.high != null
      && bar.low != null
      && bar.close != null
      && bar.high >= bar.low
    ))
    .slice(-120)

  if (data.length < 2) {
    return <Empty description="K线数据不足" style={{ padding: 32 }} />
  }

  const prices = data.flatMap((bar) => [
    bar.open,
    bar.high,
    bar.low,
    bar.close,
    ...maKeys.map((key) => bar[key]),
  ]).filter((value) => value != null && Number.isFinite(value))

  if (prices.length < 2) {
    return <Empty description="K线价格字段无效" style={{ padding: 32 }} />
  }

  const width = 920
  const height = 380
  const padding = { top: 26, right: 18, bottom: 36, left: 58 }
  const plotWidth = width - padding.left - padding.right
  const plotHeight = height - padding.top - padding.bottom
  const minPrice = Math.min(...prices)
  const maxPrice = Math.max(...prices)
  const range = Math.max(maxPrice - minPrice, Math.abs(maxPrice) * 0.01, 0.01)
  const chartMin = minPrice - range * 0.04
  const chartMax = maxPrice + range * 0.04
  const chartRange = Math.max(chartMax - chartMin, 0.01)
  const step = plotWidth / data.length
  const bodyWidth = Math.max(2, Math.min(12, step * 0.58))
  const xOf = (index) => padding.left + step * (index + 0.5)
  const yOf = (value) => padding.top + ((chartMax - value) / chartRange) * plotHeight

  const linePath = (key) => {
    let started = false
    return data.map((bar, index) => {
      const value = bar[key]
      if (value == null || !Number.isFinite(value)) return ''
      const command = started ? 'L' : 'M'
      started = true
      return `${command}${xOf(index).toFixed(1)},${yOf(value).toFixed(1)}`
    }).filter(Boolean).join(' ')
  }

  return (
    <div style={{ overflowX: 'auto' }}>
      <Space wrap size={12} style={{ marginBottom: 8 }}>
        {maKeys.map((key) => (
          <span key={key} style={{ color: maColors[key], fontSize: 12, fontWeight: 600 }}>
            {key === 'MA250' ? '年线MA250' : key}
          </span>
        ))}
        <span style={{ color: '#8c8c8c', fontSize: 12 }}>红涨绿跌 · 日K · 最近{data.length}日</span>
      </Space>
      <svg
        viewBox={`0 0 ${width} ${height}`}
        style={{ width: '100%', minWidth: 720, display: 'block', background: '#fafafa', borderRadius: 8 }}
      >
        {[0, 0.25, 0.5, 0.75, 1].map((percent) => {
          const y = padding.top + percent * plotHeight
          const price = chartMax - percent * chartRange
          return (
            <g key={percent}>
              <line x1={padding.left} y1={y} x2={width - padding.right} y2={y} stroke="#e8e8e8" />
              <text x={padding.left - 8} y={y + 4} textAnchor="end" fontSize="11" fill="#8c8c8c">
                {price.toFixed(2)}
              </text>
            </g>
          )
        })}
        {data.map((bar, index) => {
          const rising = bar.close >= bar.open
          const color = rising ? '#cf1322' : '#389e0d'
          const centerX = xOf(index)
          const highY = yOf(bar.high)
          const lowY = yOf(bar.low)
          const bodyTop = Math.min(yOf(bar.open), yOf(bar.close))
          const bodyHeight = Math.max(1, Math.abs(yOf(bar.open) - yOf(bar.close)))
          return (
            <g key={`${bar.date || bar.trade_date || bar.__index}-${index}`}>
              <line x1={centerX} y1={highY} x2={centerX} y2={lowY} stroke={color} strokeWidth="1" />
              <rect
                x={centerX - bodyWidth / 2}
                y={bodyTop}
                width={bodyWidth}
                height={bodyHeight}
                fill={rising ? color : '#fff'}
                stroke={color}
                strokeWidth="1"
              />
            </g>
          )
        })}
        {maKeys.map((key) => {
          const path = linePath(key)
          return path ? (
            <path key={key} d={path} fill="none" stroke={maColors[key]} strokeWidth="1.4" />
          ) : null
        })}
        {[0, Math.floor(data.length / 2), data.length - 1].map((index) => (
          <text key={index} x={xOf(index)} y={height - 12} textAnchor="middle" fontSize="11" fill="#8c8c8c">
            {String(data[index]?.date || data[index]?.trade_date || '').slice(5) || index + 1}
          </text>
        ))}
      </svg>
    </div>
  )
}

export default function Stocks() {
  const [activeTab, setActiveTab] = useState('watchlist')

  const [watchlist, setWatchlist] = useState([])
  const [watchlistLoading, setWatchlistLoading] = useState(false)
  const [stockModalOpen, setStockModalOpen] = useState(false)
  const [stockEditing, setStockEditing] = useState(null)
  const [stockForm] = Form.useForm()

  const [patternRules, setPatternRules] = useState(screeningConditionsFallback)
  const [defaultRules, setDefaultRules] = useState(screeningConditionsFallback)
  const [selectedRuleKeys, setSelectedRuleKeys] = useState(
    screeningConditionsFallback.filter((rule) => rule.enabled).map((rule) => rule.key),
  )
  const [rulesLoading, setRulesLoading] = useState(false)
  const [ruleParamModalOpen, setRuleParamModalOpen] = useState(false)
  const [ruleEditing, setRuleEditing] = useState(null)
  const [ruleParamText, setRuleParamText] = useState('')
  const [matchMode, setMatchMode] = useState('and')
  const [minHits, setMinHits] = useState(1)
  const [maxStocks, setMaxStocks] = useState(300)
  const [screeningLoading, setScreeningLoading] = useState(false)
  const [screeningTaskId, setScreeningTaskId] = useState(null)
  const [screeningResult, setScreeningResult] = useState(null)
  const [screeningHistory, setScreeningHistory] = useState([])
  const [historyLoading, setHistoryLoading] = useState(false)

  const [strategies, setStrategies] = useState([])
  const [strategiesLoading, setStrategiesLoading] = useState(false)
  const [strategyModalOpen, setStrategyModalOpen] = useState(false)
  const [strategyEditing, setStrategyEditing] = useState(null)
  const [strategyForm] = Form.useForm()

  const [reviewText, setReviewText] = useState('')
  const [reviewLoading, setReviewLoading] = useState(false)
  const [reviewResult, setReviewResult] = useState(null)

  const [indicatorsModalOpen, setIndicatorsModalOpen] = useState(false)
  const [indicatorsLoading, setIndicatorsLoading] = useState(false)
  const [indicatorsData, setIndicatorsData] = useState(null)
  const [indicatorsRow, setIndicatorsRow] = useState(null)

  const loadWatchlist = () => {
    setWatchlistLoading(true)
    stocksApi.watchlist()
      .then((res) => setWatchlist(normalizeList(res)))
      .catch((err) => message.error(err?.error || '加载自选股失败'))
      .finally(() => setWatchlistLoading(false))
  }

  const loadPatternRules = () => {
    setRulesLoading(true)
    stocksApi.patternRules()
      .then((res) => {
        const loadedRules = normalizeRules(res?.rules)
        const loadedDefaults = normalizeRules(res?.defaults)
        setPatternRules(loadedRules)
        setDefaultRules(loadedDefaults)
        setSelectedRuleKeys(loadedRules.filter((rule) => rule.enabled).map((rule) => rule.key))
        setMatchMode(res?.match_mode_default || 'and')
        setMaxStocks(numOrNull(res?.max_stocks_default) ?? 300)
        setMinHits(numOrNull(res?.min_hits_default) ?? 1)
      })
      .catch(() => {
        setPatternRules(screeningConditionsFallback)
        setDefaultRules(screeningConditionsFallback)
        setSelectedRuleKeys(screeningConditionsFallback.filter((rule) => rule.enabled).map((rule) => rule.key))
        message.warning('规则接口不可用，已使用本地默认规则')
      })
      .finally(() => setRulesLoading(false))
  }

  const loadScreeningHistory = () => {
    setHistoryLoading(true)
    stocksApi.screeningHistory()
      .then((res) => setScreeningHistory(normalizeList(res)))
      .catch(() => {})
      .finally(() => setHistoryLoading(false))
  }

  const loadStrategies = () => {
    setStrategiesLoading(true)
    stocksApi.strategies()
      .then((res) => setStrategies(normalizeList(res)))
      .catch(() => message.error('加载策略失败'))
      .finally(() => setStrategiesLoading(false))
  }

  useEffect(() => {
    loadWatchlist()
    loadPatternRules()
    loadScreeningHistory()
    loadStrategies()
  }, [])

  useEffect(() => {
    if (!screeningTaskId || !screeningLoading) return undefined
    const poll = () => {
      stocksApi.getScreening(screeningTaskId)
        .then((res) => {
          setScreeningResult(res)
          if (['completed', 'failed', 'cancelled'].includes(res?.status)) {
            setScreeningLoading(false)
            setScreeningTaskId(null)
            loadScreeningHistory()
            if (res.status === 'completed') message.success('筛选完成')
            if (res.status === 'failed') message.error(res?.message || '筛选失败')
            if (res.status === 'cancelled') message.warning('筛选已取消')
          }
        })
        .catch(() => {
          setScreeningLoading(false)
          setScreeningTaskId(null)
          message.error('轮询筛选结果失败')
        })
    }
    poll()
    const timer = window.setInterval(poll, 2500)
    return () => window.clearInterval(timer)
  }, [screeningTaskId, screeningLoading])

  const openIndicators = (row) => {
    const code = typeof row === 'string' ? row : stockCodeOf(row)
    if (!code) {
      message.warning('缺少股票代码')
      return
    }
    setIndicatorsRow(typeof row === 'string' ? { code } : row)
    setIndicatorsData(null)
    setIndicatorsModalOpen(true)
    setIndicatorsLoading(true)
    stocksApi.indicators(code)
      .then((res) => setIndicatorsData(res || {}))
      .catch((err) => message.error(err?.error || '获取指标失败'))
      .finally(() => setIndicatorsLoading(false))
  }

  const buildRulesPayload = () => patternRules.map((rule) => ({
    key: rule.key,
    label: rule.label,
    desc: rule.desc,
    params: rule.params || {},
    enabled: selectedRuleKeys.includes(rule.key),
  }))

  const handleStartScreening = () => {
    if (!selectedRuleKeys.length) {
      message.warning('请至少选择一个筛选条件')
      return
    }
    const enabledLabels = patternRules
      .filter((rule) => selectedRuleKeys.includes(rule.key))
      .map((rule) => rule.label)
    setScreeningLoading(true)
    setScreeningResult({
      status: 'running',
      message: '筛选任务启动中…',
      results: [],
      rules: buildRulesPayload(),
    })
    stocksApi.screening({
      name: '技术面筛选',
      rules: buildRulesPayload(),
      conditions: enabledLabels,
      match_mode: matchMode,
      min_hits: minHits,
      max_stocks: maxStocks,
    }).then((res) => {
      setScreeningResult(res)
      if (res?.id && res?.status === 'running') {
        setScreeningTaskId(res.id)
        message.success('筛选已启动，正在轮询结果')
      } else {
        setScreeningLoading(false)
        setScreeningTaskId(null)
        loadScreeningHistory()
      }
    }).catch((err) => {
      setScreeningLoading(false)
      setScreeningTaskId(null)
      message.error(err?.error || '筛选失败')
    })
  }

  const handleCancelScreening = () => {
    if (!screeningTaskId) {
      setScreeningLoading(false)
      return
    }
    stocksApi.cancelScreening(screeningTaskId)
      .then(() => {
        message.success('已发送取消请求')
        setScreeningLoading(false)
        setScreeningTaskId(null)
        loadScreeningHistory()
      })
      .catch(() => message.error('取消失败'))
  }

  const handleSaveDefaultRules = () => {
    stocksApi.savePatternRules({
      rules: buildRulesPayload(),
      match_mode: matchMode,
      min_hits: minHits,
      max_stocks: maxStocks,
    }).then(() => {
      message.success('已保存为默认筛选配置')
      loadPatternRules()
    }).catch(() => message.error('保存默认配置失败'))
  }

  const handleOpenRuleParams = (rule) => {
    setRuleEditing(rule)
    setRuleParamText(JSON.stringify(rule.params || {}, null, 2))
    setRuleParamModalOpen(true)
  }

  const handleSaveRuleParams = () => {
    const parsed = parseMaybeJson(ruleParamText, null)
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
      message.warning('请输入合法的 JSON 对象')
      return
    }
    setPatternRules((rules) => rules.map((rule) => (
      rule.key === ruleEditing?.key ? { ...rule, params: parsed } : rule
    )))
    setRuleParamModalOpen(false)
    setRuleEditing(null)
  }

  const handleStockSave = () => {
    stockForm.validateFields().then((values) => {
      const request = stockEditing
        ? stocksApi.updateStock(stockEditing.id, values)
        : stocksApi.addStock(values)
      request.then(() => {
        message.success(stockEditing ? '已更新股票' : '已添加股票')
        setStockModalOpen(false)
        setStockEditing(null)
        loadWatchlist()
      }).catch(() => message.error(stockEditing ? '更新股票失败' : '添加股票失败'))
    })
  }

  const handleAddWatchStock = (row) => {
    const code = stockCodeOf(row)
    if (!code) return
    stocksApi.addStock({
      stock_code: code,
      stock_name: stockNameOf(row),
      list_type: 'watch',
      current_price: row?.close,
      notes: Array.isArray(row?.hits) ? `筛选命中：${row.hits.join('、')}` : '',
    }).then(() => {
      message.success('已加入自选')
      loadWatchlist()
    }).catch(() => message.error('加入自选失败'))
  }

  const handleCreateNote = (row) => {
    const code = stockCodeOf(row)
    const name = stockNameOf(row)
    stocksApi.note({
      stock_code: code,
      stock_name: name,
      title: `筛选笔记 ${name || code}`,
      content: [
        `${name || ''}(${code})`,
        `收盘：${row?.close ?? '-'}`,
        `涨跌幅：${row?.pct_chg ?? '-'}%`,
        `命中条件：${Array.isArray(row?.hits) ? row.hits.join('、') : row?.hits || '-'}`,
      ].join('\n'),
    }).then(() => message.success('已写入笔记'))
      .catch(() => message.error('写入笔记失败'))
  }

  const handleStrategySave = () => {
    strategyForm.validateFields().then((values) => {
      const rules = parseMaybeJson(values.rules_json, {})
      const payload = { ...values, rules }
      const request = strategyEditing
        ? stocksApi.updateStrategy(strategyEditing.id, payload)
        : stocksApi.createStrategy(payload)
      request.then(() => {
        message.success(strategyEditing ? '策略已更新' : '策略已创建')
        setStrategyModalOpen(false)
        setStrategyEditing(null)
        loadStrategies()
      }).catch(() => message.error(strategyEditing ? '更新策略失败' : '创建策略失败'))
    })
  }

  const handleReview = () => {
    if (!reviewText.trim()) {
      message.warning('请输入交易记录')
      return
    }
    setReviewLoading(true)
    stocksApi.review({ input: reviewText })
      .then((res) => {
        const result = res?.review || res?.result || res
        setReviewResult(result)
        message.success('AI复盘完成')
      })
      .catch(() => message.error('复盘失败'))
      .finally(() => setReviewLoading(false))
  }

  const watchlistColumns = [
    { title: 'ID', dataIndex: 'id', width: 70 },
    {
      title: '股票代码',
      dataIndex: 'stock_code',
      width: 120,
      render: (value, row) => (
        <a onClick={() => openIndicators(row)}>{value || row.code}</a>
      ),
    },
    { title: '股票名称', dataIndex: 'stock_name', width: 120, render: (value, row) => value || row.name || '-' },
    {
      title: '类型',
      dataIndex: 'list_type',
      width: 90,
      render: (value) => <Tag color={listTypeColors[value]}>{listTypeLabels[value] || value || '-'}</Tag>,
    },
    { title: '买入价', dataIndex: 'buy_price', width: 100, render: (value) => value ?? '-' },
    {
      title: '现价',
      dataIndex: 'current_price',
      width: 120,
      render: (value, row) => {
        if (value == null) return '-'
        const buy = numOrNull(row.buy_price)
        const current = numOrNull(value)
        const change = buy && current != null ? ((current - buy) / buy) * 100 : null
        return (
          <span style={{ color: change > 0 ? '#cf1322' : change < 0 ? '#389e0d' : undefined }}>
            {value}{change == null ? '' : ` (${change > 0 ? '+' : ''}${change.toFixed(2)}%)`}
          </span>
        )
      },
    },
    { title: '数量', dataIndex: 'quantity', width: 90, render: (value) => value ?? '-' },
    { title: '备注', dataIndex: 'notes', ellipsis: true, render: (value) => value || '-' },
    { title: '添加时间', dataIndex: 'added_at', width: 170, render: (value) => value || '-' },
    {
      title: '操作',
      key: 'actions',
      width: 130,
      fixed: 'right',
      render: (_, row) => (
        <Space size="small">
          <Tooltip title="编辑">
            <Button
              size="small"
              icon={<EditOutlined />}
              onClick={() => {
                setStockEditing(row)
                stockForm.setFieldsValue(row)
                setStockModalOpen(true)
              }}
            />
          </Tooltip>
          <Popconfirm
            title="确认删除？"
            onConfirm={() => {
              stocksApi.deleteStock(row.id)
                .then(() => {
                  message.success('已删除')
                  loadWatchlist()
                })
                .catch(() => message.error('删除失败'))
            }}
          >
            <Button size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ]

  const screeningRows = Array.isArray(screeningResult?.results) ? screeningResult.results : []
  const ruleStats = Array.isArray(screeningResult?.rule_stats)
    ? screeningResult.rule_stats
    : (Array.isArray(screeningResult?.conditions?.rule_stats) ? screeningResult.conditions.rule_stats : [])

  const screeningResultColumns = [
    {
      title: 'code',
      dataIndex: 'code',
      width: 105,
      fixed: 'left',
      render: (value, row) => <a onClick={() => openIndicators(row)}>{value || row.stock_code}</a>,
    },
    { title: 'name', dataIndex: 'name', width: 110, render: (value, row) => value || row.stock_name || '-' },
    { title: 'close', dataIndex: 'close', width: 90, render: (value) => formatValue(value) },
    {
      title: 'pct_chg',
      dataIndex: 'pct_chg',
      width: 95,
      render: (value) => {
        const num = numOrNull(value)
        if (num == null) return '-'
        return <span style={{ color: num > 0 ? '#cf1322' : num < 0 ? '#389e0d' : undefined }}>{num > 0 ? '+' : ''}{num.toFixed(2)}%</span>
      },
    },
    { title: 'ma5', dataIndex: 'ma5', width: 85, render: (value) => formatValue(value) },
    { title: 'ma10', dataIndex: 'ma10', width: 85, render: (value) => formatValue(value) },
    { title: 'ma20', dataIndex: 'ma20', width: 85, render: (value) => formatValue(value) },
    { title: 'ma30', dataIndex: 'ma30', width: 85, render: (value) => formatValue(value) },
    { title: 'ma60', dataIndex: 'ma60', width: 85, render: (value) => formatValue(value) },
    { title: 'ma250', dataIndex: 'ma250', width: 90, render: (value) => formatValue(value) },
    {
      title: 'hits',
      dataIndex: 'hits',
      width: 220,
      render: (value) => {
        const hits = Array.isArray(value) ? value : (value ? [value] : [])
        return hits.length ? hits.map((item) => <Tag color="blue" key={item}>{item}</Tag>) : '-'
      },
    },
    { title: 'hit_count', dataIndex: 'hit_count', width: 95, render: (value) => value ?? 0 },
    {
      title: 'actions',
      key: 'actions',
      width: 190,
      fixed: 'right',
      render: (_, row) => (
        <Space size="small">
          <Button size="small" icon={<StarOutlined />} onClick={() => handleAddWatchStock(row)}>自选</Button>
          <Button size="small" onClick={() => handleCreateNote(row)}>笔记</Button>
          <Button size="small" icon={<LineChartOutlined />} onClick={() => openIndicators(row)}>K线指标</Button>
        </Space>
      ),
    },
  ]

  const screeningHistoryColumns = [
    { title: 'ID', dataIndex: 'id', width: 70 },
    { title: '名称', dataIndex: 'name', width: 150, ellipsis: true, render: (value) => value || '-' },
    {
      title: '条件',
      dataIndex: 'condition_labels',
      ellipsis: true,
      render: (value, row) => {
        const labels = Array.isArray(value) && value.length
          ? value
          : parseMaybeJson(row.conditions_json, row.conditions_json)
        if (Array.isArray(labels)) return labels.join('、') || '-'
        if (labels && typeof labels === 'object') {
          const rules = labels.rules || labels.conditions || []
          return rules.map((item) => (typeof item === 'object' ? item.label || item.key : item)).filter(Boolean).join('、') || '-'
        }
        return labels ? String(labels) : '-'
      },
    },
    { title: '命中', dataIndex: 'matched', width: 90, render: (value) => value ?? '-' },
    {
      title: '状态',
      dataIndex: 'status',
      width: 100,
      render: (value) => {
        const color = value === 'completed' ? 'green' : value === 'failed' ? 'red' : value === 'cancelled' ? 'orange' : 'blue'
        return <Tag color={color}>{value || '-'}</Tag>
      },
    },
    { title: '消息', dataIndex: 'message', ellipsis: true, render: (value) => value || '-' },
    { title: '创建时间', dataIndex: 'created_at', width: 170, render: (value) => value || '-' },
    {
      title: '操作',
      key: 'actions',
      width: 90,
      render: (_, row) => (
        <Button
          size="small"
          onClick={() => {
            stocksApi.getScreening(row.id)
              .then((res) => {
                setScreeningResult(res)
                setActiveTab('screening')
              })
              .catch(() => message.error('加载历史详情失败'))
          }}
        >
          查看
        </Button>
      ),
    },
  ]

  const strategyColumns = [
    { title: 'ID', dataIndex: 'id', width: 70 },
    { title: '名称', dataIndex: 'name', width: 150, ellipsis: true },
    {
      title: '类型',
      dataIndex: 'strategy_type',
      width: 90,
      render: (value) => <Tag color={strategyTypeColors[value]}>{strategyTypeLabels[value] || value || '-'}</Tag>,
    },
    { title: '描述', dataIndex: 'description', ellipsis: true, render: (value) => value || '-' },
    {
      title: '得分',
      dataIndex: 'score',
      width: 80,
      render: (value) => value != null ? <b style={{ color: value >= 80 ? '#cf1322' : '#faad14' }}>{value}</b> : '-',
    },
    {
      title: '命中率',
      dataIndex: 'hit_rate',
      width: 90,
      render: (value) => {
        const num = numOrNull(value)
        return num == null ? '-' : `${(num * 100).toFixed(1)}%`
      },
    },
    { title: '总交易', dataIndex: 'total_trades', width: 90, render: (value) => value ?? '-' },
    { title: '胜场', dataIndex: 'winning_trades', width: 80, render: (value) => value ?? '-' },
    {
      title: '状态',
      dataIndex: 'status',
      width: 90,
      render: (value) => <Tag color={value === 'active' ? 'green' : 'default'}>{value === 'active' ? '启用' : value || '-'}</Tag>,
    },
    {
      title: '操作',
      key: 'actions',
      width: 130,
      fixed: 'right',
      render: (_, row) => (
        <Space size="small">
          <Tooltip title="编辑">
            <Button
              size="small"
              icon={<EditOutlined />}
              onClick={() => {
                setStrategyEditing(row)
                strategyForm.setFieldsValue({
                  ...row,
                  rules_json: row.rules_json
                    ? (typeof row.rules_json === 'string' ? row.rules_json : JSON.stringify(row.rules_json, null, 2))
                    : '',
                })
                setStrategyModalOpen(true)
              }}
            />
          </Tooltip>
          <Popconfirm
            title="确认删除？"
            onConfirm={() => {
              stocksApi.deleteStrategy(row.id)
                .then(() => {
                  message.success('已删除')
                  loadStrategies()
                })
                .catch(() => message.error('删除失败'))
            }}
          >
            <Button size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ]

  const indicatorCode = indicatorsData?.code || stockCodeOf(indicatorsRow)
  const indicatorName = stockNameOf(indicatorsRow)
  const indicators = indicatorsData?.indicators || {}
  const indicatorBars = Array.isArray(indicatorsData?.bars) ? indicatorsData.bars : []

  const tabItems = [
    {
      key: 'watchlist',
      label: <span><LineChartOutlined /> 自选股</span>,
      children: (
        <div>
          <div className="table-toolbar" style={{ marginBottom: 16 }}>
            <div className="table-toolbar-left">
              <Button icon={<ReloadOutlined />} onClick={loadWatchlist}>刷新</Button>
            </div>
            <Button
              type="primary"
              icon={<PlusOutlined />}
              onClick={() => {
                setStockEditing(null)
                stockForm.resetFields()
                stockForm.setFieldsValue({ list_type: 'watch' })
                setStockModalOpen(true)
              }}
            >
              添加股票
            </Button>
          </div>
          <Table
            columns={watchlistColumns}
            dataSource={watchlist}
            rowKey={(row) => row.id || stockCodeOf(row)}
            loading={watchlistLoading}
            scroll={{ x: 1180 }}
            pagination={{ pageSize: 15, showTotal: (total) => `共 ${total} 条` }}
          />
        </div>
      ),
    },
    {
      key: 'screening',
      label: <span><SearchOutlined /> 条件筛选</span>,
      children: (
        <div>
          <Card
            size="small"
            title={<span><FundOutlined /> 筛选规则</span>}
            extra={<Button size="small" icon={<ReloadOutlined />} onClick={loadPatternRules}>刷新规则</Button>}
            style={{ marginBottom: 16 }}
          >
            <Spin spinning={rulesLoading}>
              <Checkbox.Group value={selectedRuleKeys} onChange={setSelectedRuleKeys} style={{ width: '100%' }}>
                <Row gutter={[12, 12]}>
                  {patternRules.map((rule) => (
                    <Col key={rule.key} xs={24} sm={12} lg={8} xl={6}>
                      <Card
                        size="small"
                        bodyStyle={{ minHeight: 92, padding: 12 }}
                        style={{ borderColor: selectedRuleKeys.includes(rule.key) ? '#1677ff' : undefined }}
                      >
                        <Space align="start" style={{ width: '100%', justifyContent: 'space-between' }}>
                          <Checkbox value={rule.key}>
                            <div style={{ fontWeight: 600 }}>{rule.label}</div>
                          </Checkbox>
                          <Tooltip title="编辑参数">
                            <Button
                              size="small"
                              type="text"
                              icon={<SettingOutlined />}
                              onClick={(event) => {
                                event.preventDefault()
                                event.stopPropagation()
                                handleOpenRuleParams(rule)
                              }}
                            />
                          </Tooltip>
                        </Space>
                        <div style={{ marginTop: 6, color: '#8c8c8c', fontSize: 12, lineHeight: 1.5 }}>
                          {rule.desc || '暂无说明'}
                        </div>
                      </Card>
                    </Col>
                  ))}
                </Row>
              </Checkbox.Group>
            </Spin>
            <Divider />
            <Row gutter={[12, 12]} align="middle">
              <Col xs={24} sm={8} md={5}>
                <div style={{ marginBottom: 4 }}>匹配模式</div>
                <Select
                  value={matchMode}
                  onChange={setMatchMode}
                  style={{ width: '100%' }}
                  options={[
                    { value: 'and', label: 'and：全部命中' },
                    { value: 'min', label: 'min：至少N项' },
                    { value: 'or', label: 'or：任一命中' },
                  ]}
                />
              </Col>
              <Col xs={12} sm={8} md={4}>
                <div style={{ marginBottom: 4 }}>min_hits</div>
                <InputNumber min={1} max={Math.max(patternRules.length, 1)} value={minHits} onChange={(value) => setMinHits(value || 1)} style={{ width: '100%' }} />
              </Col>
              <Col xs={12} sm={8} md={4}>
                <div style={{ marginBottom: 4 }}>max_stocks</div>
                <InputNumber min={1} value={maxStocks} onChange={(value) => setMaxStocks(value || 300)} style={{ width: '100%' }} />
              </Col>
              <Col xs={24} md={11}>
                <Space wrap style={{ marginTop: 24 }}>
                  <Button type="primary" icon={<SearchOutlined />} loading={screeningLoading} onClick={handleStartScreening}>
                    开始筛选
                  </Button>
                  <Button onClick={() => setSelectedRuleKeys(defaultRules.filter((rule) => rule.enabled).map((rule) => rule.key))}>
                    恢复默认勾选
                  </Button>
                  <Button
                    icon={<ThunderboltOutlined />}
                    onClick={() => setSelectedRuleKeys(['ma_all_rising', 'recent_limit_up'])}
                  >
                    趋势+涨停初筛
                  </Button>
                  <Button onClick={handleSaveDefaultRules}>保存为默认</Button>
                  <Button onClick={() => setSelectedRuleKeys([])}>清空勾选</Button>
                  {screeningLoading && (
                    <Button danger onClick={handleCancelScreening}>取消</Button>
                  )}
                </Space>
              </Col>
            </Row>
          </Card>

          <Card
            size="small"
            title={<span><ThunderboltOutlined /> 筛选结果</span>}
            style={{ marginBottom: 16 }}
            extra={screeningResult?.status ? <Tag color={screeningResult.status === 'completed' ? 'green' : 'blue'}>{screeningResult.status}</Tag> : null}
          >
            {screeningResult?.message && (
              <Alert
                type={screeningResult.status === 'failed' ? 'error' : screeningResult.status === 'cancelled' ? 'warning' : 'info'}
                message={screeningResult.message}
                showIcon
                style={{ marginBottom: 12 }}
              />
            )}
            {ruleStats.length > 0 && (
              <div style={{ marginBottom: 12 }}>
                <Space wrap>
                  {ruleStats.map((item) => (
                    <Tag key={item.key || item.label} color={(item.hits || 0) > 0 ? 'blue' : 'default'}>
                      {item.label || item.key}: {item.hits ?? 0}
                    </Tag>
                  ))}
                </Space>
              </div>
            )}
            <Table
              columns={screeningResultColumns}
              dataSource={screeningRows}
              rowKey={(row) => row.code || row.stock_code}
              loading={screeningLoading && screeningRows.length === 0}
              scroll={{ x: 1380 }}
              size="small"
              pagination={{ pageSize: 20, showTotal: (total) => `共 ${total} 条` }}
              locale={{ emptyText: <Empty description="暂无筛选结果" /> }}
            />
          </Card>

          <Card size="small" title={<span><ReloadOutlined /> 筛选历史</span>}>
            <Table
              columns={screeningHistoryColumns}
              dataSource={screeningHistory}
              rowKey="id"
              loading={historyLoading}
              scroll={{ x: 980 }}
              size="small"
              pagination={{ pageSize: 10, showTotal: (total) => `共 ${total} 条` }}
              locale={{ emptyText: <Empty description="暂无筛选历史" /> }}
            />
          </Card>
        </div>
      ),
    },
    {
      key: 'strategy',
      label: <span><RobotOutlined /> 策略库</span>,
      children: (
        <div>
          <div className="table-toolbar" style={{ marginBottom: 16 }}>
            <div className="table-toolbar-left">
              <Button icon={<ReloadOutlined />} onClick={loadStrategies}>刷新</Button>
            </div>
            <Button
              type="primary"
              icon={<PlusOutlined />}
              onClick={() => {
                setStrategyEditing(null)
                strategyForm.resetFields()
                strategyForm.setFieldsValue({ strategy_type: 'trend', status: 'active' })
                setStrategyModalOpen(true)
              }}
            >
              创建策略
            </Button>
          </div>
          <Table
            columns={strategyColumns}
            dataSource={strategies}
            rowKey="id"
            loading={strategiesLoading}
            scroll={{ x: 1120 }}
            pagination={{ pageSize: 15, showTotal: (total) => `共 ${total} 条` }}
          />
        </div>
      ),
    },
    {
      key: 'review',
      label: <span><AimOutlined /> AI复盘</span>,
      children: (
        <Row gutter={24}>
          <Col xs={24} lg={12}>
            <Card title="交易记录" size="small">
              <Input.TextArea
                rows={10}
                value={reviewText}
                onChange={(event) => setReviewText(event.target.value)}
                placeholder="请输入今天的交易记录，包括买入/卖出的股票、价格、数量、操作理由等..."
                style={{ marginBottom: 16 }}
              />
              <Button type="primary" icon={<RobotOutlined />} loading={reviewLoading} onClick={handleReview} block size="large">
                AI复盘
              </Button>
            </Card>
          </Col>
          <Col xs={24} lg={12}>
            {reviewResult ? (
              <div>
                <Card title="复盘结果" size="small" style={{ marginBottom: 12 }} extra={<Tag color="green">AI 分析完成</Tag>}>
                  <Row gutter={[8, 8]}>
                    {reviewResult.success_trades != null && (
                      <Col span={12}>
                        <div style={{ background: '#f6ffed', padding: '12px 16px', borderRadius: 8, border: '1px solid #b7eb8f' }}>
                          <div style={{ fontSize: 12, color: '#52c41a', marginBottom: 4 }}>成功交易</div>
                          <div style={{ fontWeight: 700, color: '#52c41a', whiteSpace: 'pre-wrap' }}>
                            {Array.isArray(reviewResult.success_trades) ? reviewResult.success_trades.length : String(reviewResult.success_trades)}
                          </div>
                        </div>
                      </Col>
                    )}
                    {reviewResult.failure_trades != null && (
                      <Col span={12}>
                        <div style={{ background: '#fff2f0', padding: '12px 16px', borderRadius: 8, border: '1px solid #ffccc7' }}>
                          <div style={{ fontSize: 12, color: '#ff4d4f', marginBottom: 4 }}>失败交易</div>
                          <div style={{ fontWeight: 700, color: '#ff4d4f', whiteSpace: 'pre-wrap' }}>
                            {Array.isArray(reviewResult.failure_trades) ? reviewResult.failure_trades.length : String(reviewResult.failure_trades)}
                          </div>
                        </div>
                      </Col>
                    )}
                    {reviewResult.win_rate_trend != null && (
                      <Col span={24}>
                        胜率趋势：<b style={{ color: '#1677ff' }}>{String(reviewResult.win_rate_trend)}</b>
                      </Col>
                    )}
                  </Row>
                </Card>
                {reviewResult.reason_analysis && (
                  <Card title="原因分析" size="small" style={{ marginBottom: 12 }}>
                    <div style={{ whiteSpace: 'pre-wrap', lineHeight: 1.8 }}>{reviewResult.reason_analysis}</div>
                  </Card>
                )}
                {reviewResult.strategy_suggestions && (
                  <Card title="策略建议" size="small" style={{ marginBottom: 12 }}>
                    <div style={{ whiteSpace: 'pre-wrap', lineHeight: 1.8 }}>{reviewResult.strategy_suggestions}</div>
                  </Card>
                )}
              </div>
            ) : (
              <Card size="small" style={{ minHeight: 260, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <Empty description={'点击"AI复盘"按钮开始分析'} />
              </Card>
            )}
          </Col>
        </Row>
      ),
    },
  ]

  return (
    <div>
      <div className="page-title">股票研究系统</div>
      <Tabs activeKey={activeTab} onChange={setActiveTab} items={tabItems} size="large" />

      <Modal
        title={`K线/指标 - ${indicatorName ? `${indicatorName}(${indicatorCode})` : indicatorCode}`}
        open={indicatorsModalOpen}
        onCancel={() => setIndicatorsModalOpen(false)}
        footer={null}
        width={1000}
        destroyOnClose
      >
        <Spin spinning={indicatorsLoading}>
          {Object.keys(indicators || {}).length > 0 || indicatorBars.length > 0 ? (
            <div style={{ marginTop: 8 }}>
              {indicatorsData?.close != null && (
                <div style={{ marginBottom: 12, fontSize: 15 }}>
                  收盘 <b>{indicatorsData.close}</b>
                  {indicatorsData?.pct_hint != null && (
                    <span
                      style={{
                        marginLeft: 12,
                        color: indicatorsData.pct_hint > 0 ? '#cf1322' : indicatorsData.pct_hint < 0 ? '#389e0d' : '#666',
                      }}
                    >
                      {indicatorsData.pct_hint > 0 ? '+' : ''}{indicatorsData.pct_hint}%
                    </span>
                  )}
                </div>
              )}
              <KLineChart bars={indicatorBars} />
              <Divider>最新技术指标</Divider>
              {Object.entries(indicators).map(([key, value]) => (
                <Row key={key} gutter={16} style={{ marginBottom: 10 }}>
                  <Col span={4} style={{ fontWeight: 600 }}>{INDICATOR_LABELS[key] || key}</Col>
                  <Col span={20}>
                    {value && typeof value === 'object'
                      ? Object.entries(value).map(([itemKey, itemValue]) => (
                        <Tag key={itemKey} style={{ marginBottom: 4 }}>
                          {itemKey}: {String(itemValue ?? '-')}
                        </Tag>
                      ))
                      : <Tag>{String(value ?? '-')}</Tag>}
                  </Col>
                </Row>
              ))}
              {indicatorsData?.note && <div style={{ color: '#8c8c8c', marginTop: 8 }}>{indicatorsData.note}</div>}
            </div>
          ) : !indicatorsLoading ? (
            <Empty
              description={indicatorsData?.note || indicatorsData?.error || '暂无指标数据'}
              style={{ padding: 32 }}
            />
          ) : null}
        </Spin>
      </Modal>

      <Modal
        title={stockEditing ? '编辑股票' : '添加股票'}
        open={stockModalOpen}
        onOk={handleStockSave}
        onCancel={() => setStockModalOpen(false)}
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
                <InputNumber style={{ width: '100%' }} precision={2} />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="buy_price" label="买入价">
                <InputNumber style={{ width: '100%' }} precision={2} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="quantity" label="数量">
                <InputNumber style={{ width: '100%' }} min={0} precision={0} />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item name="notes" label="备注">
            <Input.TextArea rows={3} placeholder="添加备注信息..." />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title={`编辑规则参数 - ${ruleEditing?.label || ''}`}
        open={ruleParamModalOpen}
        onOk={handleSaveRuleParams}
        onCancel={() => setRuleParamModalOpen(false)}
        width={560}
      >
        <Alert
          type="info"
          showIcon
          message="参数必须是 JSON 对象，保存后点击“保存为默认”才会写入默认配置。"
          style={{ marginBottom: 12 }}
        />
        <Input.TextArea
          rows={8}
          value={ruleParamText}
          onChange={(event) => setRuleParamText(event.target.value)}
          placeholder='{"lookback": 22}'
        />
      </Modal>

      <Modal
        title={strategyEditing ? '编辑策略' : '创建策略'}
        open={strategyModalOpen}
        onOk={handleStrategySave}
        onCancel={() => setStrategyModalOpen(false)}
        width={640}
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
          <Form.Item name="rules_json" label="策略规则 (JSON)" extra="输入JSON格式的策略规则，如条件组合、指标参数等">
            <Input.TextArea rows={6} placeholder='{"conditions": ["MACD金叉", "均线多头"], "params": {"period": 20}}' />
          </Form.Item>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="score" label="得分">
                <InputNumber style={{ width: '100%' }} min={0} max={100} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="hit_rate" label="命中率" extra="输入小数，如0.68表示68%">
                <InputNumber style={{ width: '100%' }} min={0} max={1} step={0.01} />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="total_trades" label="总交易次数">
                <InputNumber style={{ width: '100%' }} min={0} precision={0} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="winning_trades" label="胜场数">
                <InputNumber style={{ width: '100%' }} min={0} precision={0} />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item name="status" label="状态" initialValue="active">
            <Select
              options={[
                { value: 'active', label: '启用' },
                { value: 'inactive', label: '停用' },
              ]}
            />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
