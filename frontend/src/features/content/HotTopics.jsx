import { useState, useEffect, useCallback } from 'react'
import {
  Table, Tag, Button, Input, Select, Space, Modal, message, Popconfirm,
  Tooltip, Row, Col, Card, Statistic, Form, Alert, Badge, Progress,
} from 'antd'
import {
  DeleteOutlined, SearchOutlined, ReloadOutlined, ThunderboltOutlined,
  FileTextOutlined, FireOutlined, EyeOutlined, GlobalOutlined,
  TeamOutlined, CloudDownloadOutlined, BarChartOutlined,
} from '@ant-design/icons'
import { Link } from 'react-router-dom'
import { hotTopicsApi, settingsApi } from '../../api'
import { formatDateTime } from '../../utils/date'

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

export default function HotTopics() {
  const [data, setData] = useState({ list: [], total: 0, stats: {}, ageStats: {} })
  const [loading, setLoading] = useState(true)
  const [page, setPage] = useState(1)
  const [filters, setFilters] = useState({ sort: 'time' })
  const [refreshing, setRefreshing] = useState(false)
  const [generating, setGenerating] = useState(null)
  const [batching, setBatching] = useState(false)
  const [viewModal, setViewModal] = useState(false)
  const [viewing, setViewing] = useState(null)
  const [refreshModal, setRefreshModal] = useState(false)
  const [meta, setMeta] = useState({ platforms: [], age_bands: [] })
  const [form] = Form.useForm()

  const loadMeta = () => {
    hotTopicsApi.meta().then(setMeta).catch(() => {})
  }

  const loadData = useCallback((p = page, f = filters) => {
    setLoading(true)
    hotTopicsApi.list({ page: p, pageSize: 15, ...f })
      .then(res => { setData(res); setPage(p) })
      .finally(() => setLoading(false))
  }, [page, filters])

  useEffect(() => {
    loadData(1)
    loadMeta()
  }, [])

  const platformLabel = (key) => {
    const p = (meta.platforms || []).find(x => x.key === key)
    if (p) return p.label
    const map = {
      douyin: '抖音',
      xiaohongshu: '小红书',
      shipinhao: '视频号',
      weibo_hot: '微博热搜',
      baidu_hot: '百度热搜',
      toutiao_hot: '头条热榜',
      zhihu_hot: '知乎热榜',
      web_ai: 'AI热点',
      julang: '巨量算数',
      chanmama: '蝉妈妈',
      xinbang: '新榜',
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

  const doRefresh = (mode) => {
    const values = form.getFieldsValue()
    setRefreshing(true)
    setRefreshModal(false)
    // 刷新后清掉来源/平台筛选，避免热榜入库了却因筛选看起来「没有数据」
    const nextFilters = { sort: 'time' }
    setFilters(nextFilters)
    setPage(1)
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
        const total = res.total_fetched ?? 0
        if (n > 0) {
          message.success(res.message || `已同步 ${n} 条（新增 ${res.inserted || 0} / 覆盖 ${res.updated || 0}）`)
        } else if (total > 0) {
          message.info(res.message || `抓取 ${total} 条，无变更`)
        } else {
          message.warning(res.message || '未抓到选题：平台采集默认关闭，请用「只刷全网热点」或配置官方数据台')
        }
        loadData(1, nextFilters)
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
      .then(() => message.success('已生成口播文案（含品牌收口），去文案中心查看'))
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
      title: '互动分', dataIndex: 'engagement_score', width: 110,
      render: (v, r) => (
        <div>
          <div style={{ fontWeight: 600 }}>{Math.round(v || 0)}</div>
          <Progress
            percent={Math.min(100, r.engagement_rate || 0)}
            size="small"
            showInfo={false}
            strokeColor="#5b6eff"
          />
        </div>
      ),
    },
    {
      title: '点赞', dataIndex: 'likes', width: 80,
      render: v => (v > 10000 ? `${(v / 10000).toFixed(1)}万` : (v || 0)),
    },
    {
      title: '收藏', dataIndex: 'favorites', width: 70,
      render: v => v || 0,
    },
    {
      title: '适合度', dataIndex: 'ai_score', width: 70,
      render: v => v ? (
        <span style={{ color: v >= 80 ? '#ff4d4f' : v >= 60 ? '#faad14' : '#999' }}>
          {Number(v).toFixed(0)}
        </span>
      ) : '-',
    },
    { title: '时间', dataIndex: 'created_at', width: 160, render: v => formatDateTime(v) },
    {
      title: '操作', key: 'action', width: 160, fixed: 'right',
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
            hotTopicsApi.delete(r.id).then(() => { message.success('已删除'); loadData() })
          }}>
            <Button size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ]

  const notReady = (meta.platforms || []).filter(p => p.enabled && !p.cookies_ready)

  return (
    <div>
      <div className="page-title">内容情报</div>
      <div className="page-desc">
        推荐用全网实时热点或「官方数据台」API 做选题；平台登录态口播采集默认关闭（易封号）。
      </div>

      <Alert
        type="warning"
        showIcon
        style={{ marginBottom: 12 }}
        message="平台自动采集有封号风险，已默认关闭"
        description={
          <span>
            日更与刷新默认采公开热榜；商业榜单请到{' '}
            <Link to="/settings/commercial">系统设置 · 官方数据台</Link> 配置 API 后拉取。
            若仍要开抖音/小红书 Cookie 采集，请到{' '}
            <Link to="/settings/collectors">采集平台</Link> 自行开启（不推荐）。
          </span>
        }
      />

      {notReady.length > 0 && (
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 12 }}
          message="以下平台采集已开启但未配 Cookies，采集时会跳过"
          description={notReady.map(p => p.label).join('、')}
        />
      )}

      {/* 平台状态 */}
      <Row gutter={10} style={{ marginBottom: 12 }}>
        {(meta.platforms || []).map(p => (
          <Col key={p.key} flex="1">
            <Card size="small" style={{ textAlign: 'center' }}>
              <div style={{ fontWeight: 600 }}>{p.label}</div>
              <div style={{ marginTop: 4 }}>
                {p.ready
                  ? <Badge status="success" text="可采集" />
                  : p.enabled
                    ? <Badge status="warning" text="缺Cookie" />
                    : <Badge status="default" text="已关闭" />}
              </div>
            </Card>
          </Col>
        ))}
        <Col flex="1">
          <Card size="small" style={{ textAlign: 'center' }}>
            <Statistic title="情报总量" value={data.total} prefix={<FireOutlined />} valueStyle={{ fontSize: 20 }} />
          </Card>
        </Col>
        <Col flex="1">
          <Card size="small" style={{ textAlign: 'center' }}>
            <Statistic title="全网热点" value={data.stats?.hotspot || 0} prefix={<GlobalOutlined />} valueStyle={{ fontSize: 20, color: '#fa541c' }} />
          </Card>
        </Col>
        <Col flex="1">
          <Card size="small" style={{ textAlign: 'center' }}>
            <Statistic title="口播素材" value={data.stats?.platform || 0} prefix={<TeamOutlined />} valueStyle={{ fontSize: 20, color: '#1677ff' }} />
          </Card>
        </Col>
        <Col flex="1">
          <Card size="small" style={{ textAlign: 'center' }}>
            <Statistic title="官方数据台" value={data.stats?.commercial || 0} prefix={<BarChartOutlined />} valueStyle={{ fontSize: 20, color: '#2f54eb' }} />
          </Card>
        </Col>
      </Row>

      <div className="table-toolbar">
        <div className="table-toolbar-left">
          <Select
            placeholder="来源" allowClear style={{ width: 120 }}
            value={filters.source_type}
            onChange={v => setFilters({ ...filters, source_type: v })}
            options={[
              { value: 'hotspot', label: '全网热点' },
              { value: 'commercial', label: '官方数据台' },
              { value: 'platform', label: '平台口播' },
            ]}
          />
          <Select
            placeholder="平台" allowClear style={{ width: 140 }}
            value={filters.platform}
            onChange={v => setFilters({ ...filters, platform: v })}
            options={[
              ...(meta.platforms || []).map(p => ({ value: p.key, label: p.label })),
              { value: 'weibo_hot', label: '微博热搜' },
              { value: 'baidu_hot', label: '百度热搜' },
              { value: 'toutiao_hot', label: '头条热榜' },
              { value: 'zhihu_hot', label: '知乎热榜' },
              { value: 'web_ai', label: 'AI热点' },
              { value: 'julang', label: '巨量算数' },
              { value: 'chanmama', label: '蝉妈妈' },
              { value: 'xinbang', label: '新榜' },
              { value: 'commercial_custom', label: '自定义数据源' },
            ]}
          />
          <Select
            placeholder="年龄段" allowClear style={{ width: 120 }}
            value={filters.age_band}
            onChange={v => setFilters({ ...filters, age_band: v })}
            options={(meta.age_bands || AGE_FALLBACK).map(a => ({ value: a.key, label: a.label }))}
          />
          <Select
            style={{ width: 130 }}
            value={filters.sort || 'time'}
            onChange={v => setFilters({ ...filters, sort: v })}
            options={[
              { value: 'time', label: '按时间' },
              { value: 'engagement', label: '按互动率' },
              { value: 'score', label: '按适合度' },
            ]}
          />
          <Input
            placeholder="搜索标题/关键词"
            allowClear style={{ width: 180 }}
            value={filters.q}
            onChange={e => setFilters({ ...filters, q: e.target.value })}
            onPressEnter={() => loadData(1, filters)}
          />
          <Button type="primary" icon={<SearchOutlined />} onClick={() => loadData(1, filters)}>搜索</Button>
          <Button icon={<ReloadOutlined />} onClick={() => { setFilters({ sort: 'time' }); loadData(1, { sort: 'time' }) }}>重置</Button>
        </div>
        <Space>
          <Button icon={<FileTextOutlined />} loading={batching} onClick={handleBatch}>Top5→文案</Button>
          <Button
            type="primary"
            icon={<ThunderboltOutlined />}
            loading={refreshing}
            onClick={() => setRefreshModal(true)}
          >
            刷新内容情报
          </Button>
        </Space>
      </div>

      <Table
        columns={columns}
        dataSource={data.list}
        rowKey="id"
        loading={loading || refreshing}
        scroll={{ x: 1100 }}
        pagination={{
          current: page, total: data.total, pageSize: 15,
          onChange: p => loadData(p),
          showTotal: t => `共 ${t} 条`,
        }}
        size="middle"
      />

      {/* 刷新配置 */}
      <Modal
        title="刷新内容情报"
        open={refreshModal}
        onCancel={() => setRefreshModal(false)}
        footer={null}
        width={560}
      >
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 16 }}
          message="公开热榜无需登录；官方数据台需先配置 API"
          description={
            <span>
              「全量刷新」= 公开热榜 + 已启用平台口播 + 已启用数据台。
              平台 Cookie 采集默认关闭，所以全量主要靠热榜；口播要另开采集平台（不推荐）。
              商业榜单请到 <Link to="/settings/commercial">设置 · 官方数据台</Link> 配置。
            </span>
          }
        />
        <Form form={form} layout="vertical" initialValues={{ count: 5, max_keywords: 8 }}>
          <Form.Item name="platforms" label="采集平台（不选=全部已启用）">
            <Select
              mode="multiple"
              allowClear
              options={(meta.platforms || []).map(p => ({
                value: p.key,
                label: `${p.label}${p.ready ? '' : '（未就绪）'}`,
              }))}
            />
          </Form.Item>
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
          <Form.Item name="age_bands" label="年龄段（不选=全年龄关键词）">
            <Select
              mode="multiple"
              allowClear
              options={(meta.age_bands || AGE_FALLBACK).filter(a => a.key !== 'all').map(a => ({
                value: a.key, label: a.label,
              }))}
            />
          </Form.Item>
          <Row gutter={12}>
            <Col span={12}>
              <Form.Item name="count" label="每词采集条数">
                <Select options={[3, 5, 8, 10].map(n => ({ value: n, label: String(n) }))} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="max_keywords" label="最多关键词数">
                <Select options={[6, 8, 12, 18].map(n => ({ value: n, label: String(n) }))} />
              </Form.Item>
            </Col>
          </Row>
        </Form>
        <Space style={{ width: '100%', justifyContent: 'flex-end' }} wrap>
          <Button icon={<GlobalOutlined />} loading={refreshing} onClick={() => doRefresh('hotspots')}>
            只刷全网热点
          </Button>
          <Button icon={<BarChartOutlined />} loading={refreshing} onClick={() => doRefresh('commercial')}>
            拉官方数据台
          </Button>
          <Button icon={<CloudDownloadOutlined />} loading={refreshing} onClick={() => doRefresh('platforms')}>
            只采平台口播
          </Button>
          <Button type="primary" icon={<ThunderboltOutlined />} loading={refreshing} onClick={() => doRefresh('full')}>
            全量刷新
          </Button>
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
            <p><Tag color={platformColor(viewing.platform)}>{platformLabel(viewing.platform)}</Tag>
              <Tag>{SOURCE_LABELS[viewing.source_type]}</Tag>
              <Tag>{ageLabel(viewing.age_band)}</Tag>
            </p>
            <h3>{viewing.title}</h3>
            <p>作者：{viewing.author || '-'}</p>
            <p>点赞 {viewing.likes} · 收藏 {viewing.favorites} · 评论 {viewing.comments} · 转发 {viewing.shares}</p>
            <p>互动分 {Math.round(viewing.engagement_score || 0)} · 适合度 {viewing.ai_score || '-'}</p>
            {viewing.analysis && <p style={{ color: '#666' }}>分析：{viewing.analysis}</p>}
            {viewing.url && <p><a href={viewing.url} target="_blank" rel="noreferrer">打开原链接</a></p>}
          </div>
        )}
      </Modal>
    </div>
  )
}
