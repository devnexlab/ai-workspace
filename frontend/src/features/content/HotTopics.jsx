import { useState, useEffect, useCallback } from 'react'
import {
  Table, Tag, Button, Input, Select, Space, Modal, message, Popconfirm,
  Tooltip, Row, Col, Card, Statistic, Form, Alert, Progress, Tabs, Typography,
  Segmented, Empty,
} from 'antd'
import {
  DeleteOutlined, SearchOutlined, ReloadOutlined, ThunderboltOutlined,
  FileTextOutlined, FireOutlined, EyeOutlined, GlobalOutlined,
  TeamOutlined, CloudDownloadOutlined, BarChartOutlined, StockOutlined,
  RobotOutlined, ReadOutlined,
} from '@ant-design/icons'
import { Link } from 'react-router-dom'
import { hotTopicsApi, stocksApi } from '../../api'
import { formatDateTime } from '../../utils/date'
import BriefMarkdown from './BriefMarkdown'

const { Paragraph, Text } = Typography

const SOURCE_LABELS = {
  hotspot: '全网热点',
  platform: '平台口播',
  commercial: '官方数据台',
  manual: '手动',
}
const KIND_LABELS = { hotspot: '热点选题', koubo: '口播素材' }
const AGE_FALLBACK = [
  { key: '20s', label: '20-29岁' }, { key: '30s', label: '30-39岁' },
  { key: '40s', label: '40-49岁' }, { key: '50s', label: '50-59岁' },
  { key: '60s', label: '60-69岁' }, { key: '70s', label: '70-79岁' },
  { key: '80s', label: '80岁+' },
  { key: 'all', label: '全年龄' },
]

function StockIntelPanel() {
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState('')
  const [briefing, setBriefing] = useState(null)
  const [innerTab, setInnerTab] = useState('news')

  const load = useCallback(() => {
    setLoading(true)
    stocksApi.stockBriefingToday()
      .then(res => setBriefing(res))
      .catch(() => setBriefing(null))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => { load() }, [load])

  const run = (key, fn, okMsg, nextTab) => {
    setBusy(key)
    fn()
      .then(res => {
        if (res?.ok === false) throw new Error(res.error || '操作失败')
        setBriefing(prev => ({ ...prev, ...res, exists: true }))
        message.success(okMsg || res.message || '完成')
        if (nextTab) setInnerTab(nextTab)
      })
      .catch(err => message.error(err?.error || err?.message || '失败'))
      .finally(() => setBusy(''))
  }

  const news = briefing?.news || briefing?.list || []
  const hasBrief = Boolean((briefing?.brief_md || '').trim())
  const hasAnalysis = Boolean((briefing?.ai_analysis_md || '').trim())

  const newsColumns = [
    {
      title: '来源', dataIndex: 'source', width: 118,
      render: v => (
        <span className="stock-intel-chip" style={{ padding: '1px 8px', whiteSpace: 'nowrap' }}>
          {v || '资讯'}
        </span>
      ),
    },
    {
      title: '标题', dataIndex: 'title',
      ellipsis: true,
      render: (v, r) => (
        r.url
          ? <a href={r.url} target="_blank" rel="noreferrer" title={r.summary || v}>{v}</a>
          : <span title={r.summary || v}>{v}</span>
      ),
    },
    {
      title: '时间', dataIndex: 'publish_time', width: 148,
      render: v => <span style={{ fontSize: 12, color: '#64748b' }}>{v || '-'}</span>,
    },
  ]

  let pane = null
  if (innerTab === 'brief') {
    pane = (
      <BriefMarkdown
        text={briefing?.brief_md}
        placeholder="点击「获取财经新闻」后，简报会自动生成"
        variant="brief"
      />
    )
  } else if (innerTab === 'analysis') {
    pane = (
      <BriefMarkdown
        text={briefing?.ai_analysis_md}
        placeholder="点击右上角「开始分析」生成投研总结"
        variant="analysis"
      />
    )
  } else {
    pane = (
      <Table
        className="stock-intel-news-table"
        size="small"
        rowKey={(r, i) => `${r.title}-${i}`}
        columns={newsColumns}
        dataSource={news}
        loading={busy === 'refresh'}
        pagination={{ pageSize: 10, size: 'small', showTotal: t => `共 ${t} 条` }}
        scroll={{ y: 400 }}
        locale={{ emptyText: '暂无资讯' }}
      />
    )
  }

  return (
    <div className="stock-intel-panel">
      <div className="stock-intel-hero">
        <div className="stock-intel-hero-left">
          <h3 className="stock-intel-hero-title">股票情报工作台</h3>
          <div className="stock-intel-hero-sub">
            获取新闻后自动生成简报；需要时再做 AI 分析。仅供参考，不构成投资建议。
          </div>
          <div className="stock-intel-stats">
            <span className="stock-intel-chip">
              资讯 <strong>{news.length}</strong>
            </span>
            <span className="stock-intel-chip">
              简报 <strong>{hasBrief ? '已生成' : '待生成'}</strong>
            </span>
            <span className="stock-intel-chip">
              分析 <strong>{hasAnalysis ? '已完成' : '未分析'}</strong>
            </span>
            {briefing?.brief_date ? (
              <span className="stock-intel-chip">{briefing.brief_date}</span>
            ) : null}
          </div>
        </div>
        <div className="stock-intel-hero-actions">
          <Button
            type="primary"
            icon={<ReloadOutlined />}
            loading={busy === 'refresh'}
            onClick={() => run(
              'refresh',
              () => stocksApi.refreshStockNews(),
              '已获取新闻并生成股市简报',
              'news',
            )}
          >
            获取财经新闻
          </Button>
          <Button icon={<SearchOutlined />} onClick={load} loading={loading}>刷新</Button>
        </div>
      </div>

      <div className="stock-intel-shell">
        <div className="stock-intel-shell-bar">
          <Segmented
            value={innerTab}
            onChange={setInnerTab}
            options={[
              { label: `财经动态${news.length ? ` ${news.length}` : ''}`, value: 'news', icon: <StockOutlined /> },
              { label: '今日简报', value: 'brief', icon: <ReadOutlined /> },
              { label: 'AI 分析', value: 'analysis', icon: <RobotOutlined /> },
            ]}
          />
          {innerTab === 'analysis' ? (
            <Button
              type="primary"
              size="small"
              icon={<RobotOutlined />}
              loading={busy === 'analyze'}
              disabled={!news.length && busy !== 'analyze'}
              onClick={() => run(
                'analyze',
                () => stocksApi.analyzeStockBriefing({ force: true }),
                'AI 分析总结已完成',
                'analysis',
              )}
            >
              开始分析
            </Button>
          ) : (
            <Text type="secondary" ellipsis style={{ maxWidth: 280, fontSize: 12 }}>
              {briefing?.source_message || ' '}
            </Text>
          )}
        </div>
        <div
          className="stock-intel-shell-body"
          data-loading={(busy === 'refresh' && innerTab === 'brief') || (busy === 'analyze' && innerTab === 'analysis') || undefined}
        >
          {(loading && !briefing) ? (
            <div className="stock-intel-empty"><Empty description="加载中…" /></div>
          ) : pane}
        </div>
      </div>

      <div className="stock-intel-foot">
        早间自动获取可在
        {' '}
        <Link to="/settings/content">内容运营</Link>
        {' '}
        开启
      </div>
    </div>
  )
}

function VideoIntelPanel() {
  const [data, setData] = useState({ list: [], total: 0, stats: {}, hint: '' })
  const [loading, setLoading] = useState(true)
  const [page, setPage] = useState(1)
  const [filters, setFilters] = useState({ sort: 'engagement', q: '', source_type: '' })
  const [refreshing, setRefreshing] = useState(false)
  const [generating, setGenerating] = useState(null)
  const [batching, setBatching] = useState(false)
  const [viewModal, setViewModal] = useState(false)
  const [viewing, setViewing] = useState(null)
  const [refreshModal, setRefreshModal] = useState(false)
  const [meta, setMeta] = useState({ platforms: [], age_bands: [], commercial_providers: [] })
  const [form] = Form.useForm()

  const loadMeta = () => {
    hotTopicsApi.meta().then(setMeta).catch(() => {})
  }

  const loadData = useCallback((p = page, f = filters) => {
    setLoading(true)
    hotTopicsApi.list({
      page: p,
      pageSize: 15,
      // 合并后统一选题池：热榜 + 数据台，默认按互动排序
      sort: f.sort || 'engagement',
      q: f.q || undefined,
      platform: f.platform || undefined,
      source_type: f.source_type || undefined,
    })
      .then(res => { setData(res); setPage(p) })
      .finally(() => setLoading(false))
  }, [page, filters])

  useEffect(() => {
    loadMeta()
    loadData(1, filters)
  }, [])

  const platformLabel = (key) => {
    const p = (meta.platforms || []).find(x => x.key === key)
    if (p) return p.label
    const map = {
      douyin: '抖音', xiaohongshu: '小红书', shipinhao: '视频号',
      weibo_hot: '微博热搜', baidu_hot: '百度热搜', toutiao_hot: '头条热榜',
      zhihu_hot: '知乎热榜', web_ai: 'AI热点',
      julang: '巨量算数', chanmama: '蝉妈妈', xinbang: '新榜',
      commercial_custom: '自定义数据源',
    }
    return map[key] || key
  }

  const platformColor = (key) => {
    const p = (meta.platforms || []).find(x => x.key === key)
    return p?.color || (key.includes('hot') || key === 'web_ai' ? 'volcano' : 'default')
  }

  const ageLabel = (key) => {
    const a = (meta.age_bands || AGE_FALLBACK).find(x => x.key === key)
    return a?.label || key || '全年龄'
  }

  const applyFilters = (next) => {
    const merged = { ...filters, ...next }
    setFilters(merged)
    loadData(1, merged)
  }

  const doRefresh = (mode) => {
    const values = form.getFieldsValue()
    setRefreshing(true)
    setRefreshModal(false)
    hotTopicsApi.refresh({
      mode,
      platforms: values.platforms,
      age_bands: values.age_bands,
      commercial_providers: values.commercial_providers,
      count: values.count || 5,
      max_keywords: values.max_keywords || 8,
    })
      .then(res => {
        const n = res.collected ?? 0
        if (n > 0) message.success(res.message || `已同步 ${n} 条`)
        else message.warning(res.message || '未抓到新选题')
        loadData(1, filters)
        loadMeta()
      })
      .catch(err => message.error(err?.error || err?.message || '刷新失败'))
      .finally(() => setRefreshing(false))
  }

  const handleGenerate = (record) => {
    setGenerating(record.id)
    const content_type = record.content_kind === 'hotspot' && /保险|理赔|保单|保障/.test(record.title)
      ? 'insurance' : 'traffic'
    hotTopicsApi.generateScript(record.id, {
      content_type,
      age_band: record.age_band || 'all',
      duration: '60秒',
    })
      .then(() => message.success('已生成口播文案，去文案中心查看'))
      .catch(err => message.error(err?.error || '生成失败'))
      .finally(() => setGenerating(null))
  }

  const handleBatch = () => {
    setBatching(true)
    hotTopicsApi.batchGenerate({ limit: 5, content_type: 'traffic' })
      .then(res => message.success(res.message))
      .catch(err => message.error(err?.error || '批量失败'))
      .finally(() => setBatching(false))
  }

  const fmtNum = (v) => (v > 10000 ? `${(v / 10000).toFixed(1)}万` : (v || 0))
  const isHotIndex = (r) => r.source_type === 'hotspot' || r.source_type === 'commercial'
  const fmtHot = (v, r) => {
    if (!isHotIndex(r)) {
      return <span style={{ color: '#94a3b8' }} title="口播素材无热搜热度">—</span>
    }
    return fmtNum(v)
  }
  const fmtLikes = (v, r) => {
    // 热榜/多数数据台只有热度，没有真实点赞
    if (isHotIndex(r)) {
      return <span style={{ color: '#94a3b8' }} title="公开热榜无真实点赞，见「热度」列">—</span>
    }
    return fmtNum(v)
  }
  const fmtMetric = (v, r) => {
    if (isHotIndex(r) || !v) {
      return <span style={{ color: '#94a3b8' }} title="该来源不提供此项数据">—</span>
    }
    return fmtNum(v)
  }

  const columns = [
    {
      title: '来源', dataIndex: 'source_type', width: 90,
      render: (v, r) => (
        <Space direction="vertical" size={0}>
          <Tag color={v === 'hotspot' ? 'volcano' : v === 'commercial' ? 'geekblue' : 'blue'}>
            {SOURCE_LABELS[v] || v}
          </Tag>
          <Tag color={platformColor(r.platform)} style={{ marginTop: 2 }}>{platformLabel(r.platform)}</Tag>
        </Space>
      ),
    },
    {
      title: '标题 / 选题', dataIndex: 'title', ellipsis: true,
      render: (v, r) => (
        <div>
          <a onClick={() => { setViewing(r); setViewModal(true) }}>{v}</a>
          <div style={{ fontSize: 12, color: '#999' }}>
            {KIND_LABELS[r.content_kind] || r.content_kind} · {ageLabel(r.age_band)}
          </div>
        </div>
      ),
    },
    {
      title: '互动分', dataIndex: 'engagement_score', width: 100,
      render: (v, r) => (
        <div>
          <div style={{ fontWeight: 600 }}>{Math.round(v || 0)}</div>
          <Progress
            percent={Math.min(100, r.engagement_rate || 0)}
            size="small"
            showInfo={false}
            strokeColor="#5b5bd6"
          />
        </div>
      ),
    },
    {
      title: (
        <Tooltip title="公开热榜的热搜热度指数">
          热度
        </Tooltip>
      ),
      key: 'hot_index',
      dataIndex: 'likes',
      width: 90,
      render: fmtHot,
    },
    {
      title: (
        <Tooltip title="视频真实点赞；热榜来源通常无此数据">
          点赞
        </Tooltip>
      ),
      key: 'likes',
      dataIndex: 'likes',
      width: 80,
      render: fmtLikes,
    },
    {
      title: '转发', dataIndex: 'shares', width: 70,
      render: (v, r) => fmtMetric(v, r),
    },
    {
      title: '收藏', dataIndex: 'favorites', width: 70,
      render: (v, r) => fmtMetric(v, r),
    },
    {
      title: '适合度', dataIndex: 'ai_score', width: 70,
      render: v => v ? (
        <span style={{ color: v >= 80 ? '#ff4d4f' : v >= 60 ? '#faad14' : '#999' }}>
          {Number(v).toFixed(0)}
        </span>
      ) : '-',
    },
    { title: '时间', dataIndex: 'created_at', width: 150, render: v => formatDateTime(v) },
    {
      title: '操作', key: 'action', width: 150, fixed: 'right',
      render: (_, r) => (
        <Space size="small">
          <Tooltip title="详情">
            <Button size="small" icon={<EyeOutlined />} onClick={() => { setViewing(r); setViewModal(true) }} />
          </Tooltip>
          <Tooltip title="生成口播文案">
            <Button
              size="small" type="primary" ghost icon={<FileTextOutlined />}
              loading={generating === r.id}
              onClick={() => handleGenerate(r)}
            />
          </Tooltip>
          <Popconfirm title="删除？" onConfirm={() => {
            hotTopicsApi.delete(r.id).then(() => { message.success('已删除'); loadData(page, filters) })
          }}>
            <Button size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <div>
      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 12 }}
        message="视频号选题池：全网热榜 + 官方数据台，按互动排序；不做视频号登录采集"
        description={
          <span>
            公开热榜只有「热度」，没有真实转发/收藏（会显示为 —）。
            要更接近点赞/转发数据，请配置并拉取
            {' '}
            <Link to="/settings/commercial">官方数据台</Link>
            。
          </span>
        }
      />

      <div className="table-toolbar">
        <div className="table-toolbar-left">
          <Segmented
            value={filters.source_type || 'all'}
            onChange={v => applyFilters({ source_type: v === 'all' ? '' : v })}
            options={[
              { label: '全部选题', value: 'all' },
              { label: `热榜 ${data.stats?.hotspot || 0}`, value: 'hotspot' },
              { label: `数据台 ${data.stats?.commercial || 0}`, value: 'commercial' },
            ]}
          />
          <Select
            style={{ width: 130 }}
            value={filters.sort || 'engagement'}
            onChange={v => applyFilters({ sort: v })}
            options={[
              { value: 'engagement', label: '按互动分' },
              { value: 'likes', label: '按点赞' },
              { value: 'shares', label: '按转发' },
              { value: 'time', label: '按时间' },
              { value: 'score', label: '按适合度' },
            ]}
          />
          <Input
            placeholder="搜索标题"
            allowClear style={{ width: 180 }}
            value={filters.q}
            onChange={e => setFilters({ ...filters, q: e.target.value })}
            onPressEnter={() => loadData(1, filters)}
          />
          <Button type="primary" icon={<SearchOutlined />} onClick={() => loadData(1, filters)}>搜索</Button>
        </div>
        <Space wrap>
          <Button icon={<FileTextOutlined />} loading={batching} onClick={handleBatch}>Top5→文案</Button>
          <Button icon={<GlobalOutlined />} loading={refreshing} onClick={() => doRefresh('hotspots')}>
            刷全网热点
          </Button>
          <Button icon={<BarChartOutlined />} loading={refreshing} onClick={() => doRefresh('commercial')}>
            拉官方数据台
          </Button>
          <Button
            type="primary"
            icon={<ThunderboltOutlined />}
            loading={refreshing}
            onClick={() => setRefreshModal(true)}
          >
            更多选项
          </Button>
        </Space>
      </div>

      {!data.stats?.commercial && (
        <Alert
          type="warning"
          showIcon
          style={{ marginBottom: 12 }}
          message="尚未拉取官方数据台数据：当前列表主要是全网热榜。配置并「拉官方数据台」后，可用筛选查看高互动爆款。"
        />
      )}

      <Table
        columns={columns}
        dataSource={data.list}
        rowKey="id"
        loading={loading || refreshing}
        scroll={{ x: 1100 }}
        pagination={{
          current: page, total: data.total, pageSize: 15,
          onChange: p => loadData(p, filters),
          showTotal: t => `共 ${t} 条`,
        }}
        size="middle"
      />

      <Modal
        title="刷新视频号选题"
        open={refreshModal}
        onCancel={() => setRefreshModal(false)}
        footer={null}
        width={560}
      >
        <Form form={form} layout="vertical" initialValues={{ count: 5, max_keywords: 8 }}>
          <Form.Item name="commercial_providers" label="商业数据源（不选=全部已启用）">
            <Select
              mode="multiple"
              allowClear
              options={(meta.commercial_providers || []).map(p => ({
                value: p.key,
                label: `${p.label}${p.enabled ? (p.configured ? '' : '（未配齐）') : '（未启用）'}`,
              }))}
            />
          </Form.Item>
          <Form.Item name="age_bands" label="年龄段（平台口播用）">
            <Select
              mode="multiple"
              allowClear
              options={(meta.age_bands || AGE_FALLBACK).filter(a => a.key !== 'all').map(a => ({
                value: a.key, label: a.label,
              }))}
            />
          </Form.Item>
        </Form>
        <Space style={{ width: '100%', justifyContent: 'flex-end' }} wrap>
          <Button icon={<GlobalOutlined />} loading={refreshing} onClick={() => doRefresh('hotspots')}>只刷全网热点</Button>
          <Button icon={<BarChartOutlined />} loading={refreshing} onClick={() => doRefresh('commercial')}>拉官方数据台</Button>
          <Button icon={<CloudDownloadOutlined />} loading={refreshing} onClick={() => doRefresh('platforms')}>平台口播（不推荐）</Button>
          <Button type="primary" icon={<ThunderboltOutlined />} loading={refreshing} onClick={() => doRefresh('full')}>全量刷新</Button>
        </Space>
      </Modal>

      <Modal
        title="情报详情"
        open={viewModal}
        onCancel={() => setViewModal(false)}
        footer={[
          <Button key="close" onClick={() => setViewModal(false)}>关闭</Button>,
          <Button key="gen" type="primary" loading={generating === viewing?.id} onClick={() => viewing && handleGenerate(viewing)}>
            生成口播文案
          </Button>,
        ]}
        width={640}
      >
        {viewing && (
          <div>
            <p>
              <Tag color={platformColor(viewing.platform)}>{platformLabel(viewing.platform)}</Tag>
              <Tag>{SOURCE_LABELS[viewing.source_type]}</Tag>
              <Tag>{ageLabel(viewing.age_band)}</Tag>
            </p>
            <h3>{viewing.title}</h3>
            <p>作者：{viewing.author || '-'}</p>
            <p>
              {viewing.source_type === 'hotspot' || viewing.source_type === 'commercial'
                ? <>热度 {viewing.likes}（热搜/榜单热度）· 点赞 — · 收藏 — · 转发 —</>
                : <>点赞 {viewing.likes || 0} · 收藏 {viewing.favorites || 0} · 评论 {viewing.comments || 0} · 转发 {viewing.shares || 0}</>}
            </p>
            <p>互动分 {Math.round(viewing.engagement_score || 0)} · 适合度 {viewing.ai_score || '-'}</p>
            {viewing.analysis && <Paragraph type="secondary">分析：{viewing.analysis}</Paragraph>}
            {viewing.url && <p><a href={viewing.url} target="_blank" rel="noreferrer">打开原链接</a></p>}
          </div>
        )}
      </Modal>
    </div>
  )
}

export default function HotTopics() {
  return (
    <div>
      <div className="page-title">内容情报</div>
      <div className="page-desc">
        两大板块：股票（动态 / 简报 / AI 分析）· 视频号（热榜与数据台选题池）
      </div>

      <Tabs
        defaultActiveKey="stock"
        items={[
          {
            key: 'stock',
            label: (
              <span>
                <StockOutlined />
                {' '}
                股票情报
              </span>
            ),
            children: <StockIntelPanel />,
          },
          {
            key: 'video',
            label: (
              <span>
                <FireOutlined />
                {' '}
                热点选题
              </span>
            ),
            children: <VideoIntelPanel />,
          },
        ]}
      />
    </div>
  )
}
