import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Button, Drawer, Input, Select, Space, Spin, Tag, message, Empty, Pagination, Switch, Tooltip,
} from 'antd'
import {
  ReloadOutlined, RocketOutlined, LinkOutlined, SyncOutlined,
  AppstoreOutlined, EyeOutlined, LikeOutlined, MessageOutlined,
  ShareAltOutlined, StarOutlined, QuestionCircleOutlined,
} from '@ant-design/icons'
import { publishApi } from '../../api'
import { API_LONG_TIMEOUT } from '../../config'
import { formatDateTime } from '../../utils/date'
import './ContentWorkbench.css'

const PLAT_CLASS = {
  shipinhao: 'shipin',
  douyin: 'douyin',
  xiaohongshu: 'xhs',
}

const PLAT_SHORT = {
  shipinhao: '视',
  douyin: '抖',
  xiaohongshu: '红',
}

const DIAG_TAG_COLOR = {
  ok: 'success',
  hot: 'error',
  warn: 'warning',
  err: 'error',
  '': 'default',
}

function fmtNum(n) {
  const v = Number(n) || 0
  if (!v) return '—'
  if (v >= 10000) return `${(v / 10000).toFixed(1)}万`
  if (v >= 1000) return `${(v / 1000).toFixed(1)}k`
  return String(v)
}

function fmtPubDate(s) {
  if (!s) return '—'
  const t = formatDateTime(s)
  if (!t || t === '-') return '—'
  return t.length >= 16 ? t.slice(5, 16) : t
}

function fmtSyncAt(s) {
  if (!s) return '尚未同步'
  return fmtPubDate(s)
}

export default function ContentWorkbench() {
  const navigate = useNavigate()
  const [loading, setLoading] = useState(true)
  const [syncing, setSyncing] = useState(false)
  const [loginKey, setLoginKey] = useState(null)
  const [rowSyncing, setRowSyncing] = useState(null)
  const [data, setData] = useState({
    list: [],
    total: 0,
    kpi: { total: 0, warn: 0, consult: 0, pending: 0, last_synced_at: '' },
    platforms: [],
    prefs: {
      official_auto_reply_shipinhao: false,
      sync_auto_enabled: false,
      sync_run_hour: 3,
      sync_last_run: '',
    },
  })
  const [prefsSaving, setPrefsSaving] = useState(false)
  const [tab, setTab] = useState('all')
  const [search, setSearch] = useState('')
  const [q, setQ] = useState('')
  const [diag, setDiag] = useState('all')
  const [range, setRange] = useState('all')
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [sort, setSort] = useState('date')
  const [sortDir, setSortDir] = useState('desc')
  const [drawer, setDrawer] = useState(null)

  const load = useCallback((overrides = {}) => {
    setLoading(true)
    const nextTab = overrides.tab ?? tab
    const nextPage = overrides.page ?? page
    const nextPageSize = overrides.pageSize ?? pageSize
    const params = {
      platform: nextTab === 'all' ? '' : nextTab,
      q: overrides.q ?? q,
      diag: overrides.diag ?? diag,
      range: overrides.range ?? range,
      sort: overrides.sort ?? sort,
      sortDir: overrides.sortDir ?? sortDir,
      page: nextPage,
      pageSize: nextPageSize,
    }
    return publishApi.workbench(params)
      .then((res) => {
        setData({
          list: res.list || [],
          total: res.total || 0,
          kpi: res.kpi || {},
          platforms: res.platforms || [],
          prefs: res.prefs || {},
        })
      })
      .catch((err) => message.error(err?.error || err?.message || '加载工作台失败'))
      .finally(() => setLoading(false))
  }, [tab, q, diag, range, sort, sortDir, page, pageSize])

  useEffect(() => {
    load()
  }, [load])

  useEffect(() => {
    const t = setTimeout(() => {
      setPage(1)
      setQ(search.trim())
    }, 280)
    return () => clearTimeout(t)
  }, [search])

  const platformMap = useMemo(
    () => Object.fromEntries((data.platforms || []).map((p) => [p.key, p])),
    [data.platforms],
  )

  const tabs = useMemo(() => {
    const allCount = data.kpi?.total ?? 0
    return [
      { key: 'all', label: '全部', count: allCount },
      ...(data.platforms || []).map((p) => ({
        key: p.key,
        label: p.label,
        count: p.count || 0,
      })),
    ]
  }, [data.platforms, data.kpi])

  const totalPages = Math.max(1, Math.ceil((data.total || 0) / pageSize))

  const handleBatchSync = async (platformKey = '') => {
    const plat = platformKey || (tab === 'all' ? '' : tab)
    if (plat && platformMap[plat] && !platformMap[plat].ready) {
      message.warning(`请先点「${platformMap[plat].label}」旁的登录，在弹出的系统浏览器扫码`)
      return
    }
    setSyncing(true)
    try {
      const res = await publishApi.workbenchSync({
        platform: plat,
        limit: plat ? 80 : 40,
      })
      message.success(res.message || '同步完成')
      setPage(1)
      await load({ page: 1 })
    } catch (err) {
      message.error(err?.error || err?.message || '同步失败：请先点平台「登录」并在弹出的系统浏览器扫码')
      await load()
    } finally {
      setSyncing(false)
    }
  }

  const handleRowSync = async (id) => {
    setRowSyncing(id)
    try {
      const res = await publishApi.sync(id)
      message.success(res.message || '同步完成')
      const next = await publishApi.workbench({
        platform: tab === 'all' ? '' : tab,
        q,
        diag,
        range,
        sort,
        sortDir,
        page,
        pageSize,
      })
      setData({
        list: next.list || [],
        total: next.total || 0,
        kpi: next.kpi || {},
        platforms: next.platforms || [],
        prefs: next.prefs || {},
      })
      const updated = (next.list || []).find((x) => x.id === id)
      if (updated) setDrawer(updated)
      else if (res.task) setDrawer((d) => (d?.id === id ? { ...d, ...res.task, plays: res.plays ?? res.task.plays } : d))
    } catch (err) {
      message.error(err?.error || err?.message || '同步失败')
    } finally {
      setRowSyncing(null)
    }
  }

  const openLogin = async (key) => {
    const p = platformMap[key]
    if (!p) return
    setLoginKey(key)
    try {
      const res = await publishApi.workbenchLogin({ platform: key })
      if (res.logged_in) {
        message.success(res.message || `${p.label} 已登录`)
      } else {
        message.info({
          content: res.message || `已打开系统浏览器，请在弹出窗口扫码登录${p.label}（日常 Chrome 登录无效）`,
          duration: 10,
        })
      }
      await load()
      let n = 0
      const timer = setInterval(async () => {
        n += 1
        try {
          const next = await publishApi.workbench({
            platform: tab === 'all' ? '' : tab,
            q, diag, range, sort, sortDir, page, pageSize,
          })
          setData({
            list: next.list || [],
            total: next.total || 0,
            kpi: next.kpi || {},
            platforms: next.platforms || [],
            prefs: next.prefs || {},
          })
          const ok = (next.platforms || []).find((x) => x.key === key)?.ready
          if (ok || n >= 20) clearInterval(timer)
        } catch {
          if (n >= 20) clearInterval(timer)
        }
      }, 3000)
    } catch (err) {
      message.error(err?.error || err?.message || '打开登录浏览器失败')
    } finally {
      setLoginKey(null)
    }
  }

  const onPageChange = (p, size) => {
    const nextSize = size || pageSize
    if (nextSize !== pageSize) {
      setPageSize(nextSize)
      setPage(1)
    } else {
      setPage(p)
    }
  }

  const savePrefs = async (patch) => {
    setPrefsSaving(true)
    try {
      const res = await publishApi.updateWorkbenchPrefs(patch)
      setData((d) => ({ ...d, prefs: res.prefs || { ...d.prefs, ...patch } }))
      message.success(res.message || '已保存')
    } catch (err) {
      message.error(err?.error || err?.message || '保存失败')
    } finally {
      setPrefsSaving(false)
    }
  }

  const kpi = data.kpi || {}
  const prefs = data.prefs || {}

  return (
    <div className="wb-page">
      <div className="wb-hero">
        <div>
          <h1>内容工作台</h1>
          <p>多平台作品卡片一览。筛选、排序、分页定位；诊断与同步基于创作者后台导入及本系统发布任务。</p>
        </div>
        <Space wrap>
          <Button icon={<SyncOutlined />} loading={syncing} onClick={() => handleBatchSync('')}>
            同步全部
          </Button>
          <Button type="primary" icon={<RocketOutlined />} onClick={() => navigate('/publish')}>
            去发布
          </Button>
        </Space>
      </div>

      <div className="wb-login-strip">
        {(data.platforms || []).map((p) => (
          <div className="wb-login-chip" key={p.key} title="同步/发布使用本系统专用浏览器，与日常 Chrome 登录态不互通">
            <span className={`wb-login-dot ${PLAT_CLASS[p.key] || ''}`}>
              {PLAT_SHORT[p.key] || (p.label || '?').slice(0, 1)}
            </span>
            <span>{p.label}</span>
            <span className={p.ready ? 'ok' : 'warn'}>
              {p.ready ? '已登录' : '未登录'}
            </span>
            <button type="button" disabled={loginKey === p.key} onClick={() => openLogin(p.key)}>
              {loginKey === p.key ? '打开中…' : (p.ready ? '重登' : '登录')}
            </button>
          </div>
        ))}
      </div>

      <div className="wb-safe-bar">
        <div className="wb-safe-item">
          <span className="wb-safe-label">
            视频号官方关注后回复
            <Tooltip title="视频号官方「关注后自动回复」并非全量开放，个人号通常需绑定企业微信客服或获得灰度资格才可见入口；若已在官方开启，可在此勾选。本系统不会代发私信。">
              <QuestionCircleOutlined className="wb-safe-help" />
            </Tooltip>
          </span>
          <Switch
            size="small"
            checked={!!prefs.official_auto_reply_shipinhao}
            loading={prefsSaving}
            onChange={(v) => savePrefs({ official_auto_reply_shipinhao: v })}
            checkedChildren="已开"
            unCheckedChildren="未开"
          />
        </div>
        <div className="wb-safe-item">
          <span className="wb-safe-label">
            每日自动同步作品
            <Tooltip title="只读创作者后台自己的作品数据，默认关闭；开启后每天最多同步一次，建议凌晨时段。">
              <QuestionCircleOutlined className="wb-safe-help" />
            </Tooltip>
          </span>
          <Switch
            size="small"
            checked={!!prefs.sync_auto_enabled}
            loading={prefsSaving}
            onChange={(v) => savePrefs({ sync_auto_enabled: v })}
            checkedChildren="开"
            unCheckedChildren="关"
          />
          <Select
            size="small"
            className="wb-safe-hour"
            value={Number(prefs.sync_run_hour ?? 3)}
            disabled={!prefs.sync_auto_enabled || prefsSaving}
            options={Array.from({ length: 24 }, (_, h) => ({
              value: h,
              label: `${String(h).padStart(2, '0')}:00`,
            }))}
            onChange={(h) => savePrefs({ sync_run_hour: h })}
          />
        </div>
      </div>

      <div className="wb-kpi-row">
        <div className="wb-kpi">
          <div className="wb-kpi-label">作品总数</div>
          <div className="wb-kpi-value">{kpi.total ?? '—'}</div>
          <div className="wb-kpi-sub">已发布累计</div>
        </div>
        <div className="wb-kpi">
          <div className="wb-kpi-label">需关注</div>
          <div className="wb-kpi-value warn">{kpi.warn ?? '—'}</div>
          <div className="wb-kpi-sub">互动弱 / 掉量</div>
        </div>
        <div className="wb-kpi">
          <div className="wb-kpi-label">有咨询</div>
          <div className="wb-kpi-value ok">{kpi.consult ?? '—'}</div>
          <div className="wb-kpi-sub">互动标记</div>
        </div>
        <div className="wb-kpi">
          <div className="wb-kpi-label">待发布</div>
          <div className="wb-kpi-value">{kpi.pending ?? '—'}</div>
          <div className="wb-kpi-sub">跨平台队列</div>
        </div>
        <div className="wb-kpi">
          <div className="wb-kpi-label">上次同步</div>
          <div className="wb-kpi-value sync">{fmtSyncAt(kpi.last_synced_at)}</div>
          <div className="wb-kpi-sub">可批量自动同步</div>
        </div>
      </div>

      <div className="wb-panel">
        <div className="wb-tabs">
          {tabs.map((t) => (
            <button
              key={t.key}
              type="button"
              className={`wb-tab${tab === t.key ? ' active' : ''}`}
              onClick={() => {
                setTab(t.key)
                setPage(1)
              }}
            >
              {t.label}
              <span className="wb-tab-count">{t.count}</span>
            </button>
          ))}
        </div>

        <div className="wb-toolbar">
          <Input.Search
            allowClear
            placeholder="搜索标题…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            style={{ maxWidth: 260 }}
          />
          <Select
            value={diag}
            style={{ width: 120 }}
            onChange={(v) => { setDiag(v); setPage(1) }}
            options={[
              { value: 'all', label: '全部状态' },
              { value: 'warn', label: '有问题' },
              { value: 'consult', label: '有咨询' },
              { value: 'hot', label: '热门' },
              { value: 'normal', label: '正常' },
            ]}
          />
          <Select
            value={range}
            style={{ width: 120 }}
            onChange={(v) => { setRange(v); setPage(1) }}
            options={[
              { value: 'all', label: '全部时间' },
              { value: '7', label: '近 7 天' },
              { value: '30', label: '近 30 天' },
              { value: '90', label: '近 90 天' },
            ]}
          />
          <Select
            value={sort}
            style={{ width: 120 }}
            onChange={(v) => { setSort(v); setPage(1) }}
            options={[
              { value: 'date', label: '按发布时间' },
              { value: 'plays', label: '按播放' },
              { value: 'likes', label: '按点赞' },
              { value: 'comments', label: '按评论' },
              { value: 'shares', label: '按转发' },
              { value: 'favorites', label: '按收藏' },
            ]}
          />
          <Select
            value={sortDir}
            style={{ width: 100 }}
            onChange={(v) => { setSortDir(v); setPage(1) }}
            options={[
              { value: 'desc', label: '降序' },
              { value: 'asc', label: '升序' },
            ]}
          />
          <Button
            size="small"
            icon={<ReloadOutlined />}
            loading={syncing}
            onClick={() => handleBatchSync(tab === 'all' ? '' : tab)}
          >
            同步当前平台
          </Button>
          <span className="wb-toolbar-meta">
            共 {data.total} 条 · 第 {page}/{totalPages} 页
          </span>
        </div>

        <div className="wb-cards-wrap">
          <Spin spinning={loading}>
            {!loading && !(data.list || []).length ? (
              <div className="wb-empty">
                <Empty
                  image={<AppstoreOutlined style={{ fontSize: 36, color: '#9b9bb0' }} />}
                  description="暂无作品。先登录平台后点「同步当前平台」，或去发布中心确认发布。"
                >
                  <Space>
                    <Button onClick={() => handleBatchSync(tab === 'all' ? '' : tab)}>同步当前平台</Button>
                    <Button type="primary" onClick={() => navigate('/publish')}>去发布中心</Button>
                  </Space>
                </Empty>
              </div>
            ) : (
              <div className="wb-card-grid">
                {(data.list || []).map((item) => {
                  const warn = ['low_eng', 'drop'].includes(item.diag)
                  const plat = platformMap[item.platform]
                  return (
                    <button
                      key={item.id}
                      type="button"
                      className={`wb-card${warn ? ' warn' : ''}`}
                      onClick={() => setDrawer(item)}
                    >
                      <div className="wb-card-cover">
                        {item.cover_url ? (
                          <img src={item.cover_url} alt="" loading="lazy" referrerPolicy="no-referrer" />
                        ) : (
                          <div className="wb-card-cover-empty">暂无封面</div>
                        )}
                        <span className={`wb-plat ${PLAT_CLASS[item.platform] || ''}`}>
                          {plat?.label || item.platform || '—'}
                        </span>
                        <Tag className="wb-card-diag" color={DIAG_TAG_COLOR[item.diag_cls] || 'default'}>
                          {item.diag_tag || '正常'}
                        </Tag>
                      </div>
                      <div className="wb-card-body">
                        <div className="wb-card-title" title={item.title || item.video_title}>
                          {item.title || item.video_title || '（无标题）'}
                        </div>
                        <div className="wb-card-meta">
                          <span><EyeOutlined /> {fmtNum(item.plays)}</span>
                          <span><LikeOutlined /> {fmtNum(item.likes)}</span>
                          <span><MessageOutlined /> {fmtNum(item.comments)}</span>
                          <span><ShareAltOutlined /> {fmtNum(item.shares)}</span>
                          <span><StarOutlined /> {fmtNum(item.favorites)}</span>
                        </div>
                        <div className="wb-card-date">{fmtPubDate(item.published_at)}</div>
                      </div>
                    </button>
                  )
                })}
              </div>
            )}
          </Spin>
        </div>

        <div className="wb-pager">
          <Pagination
            current={page}
            pageSize={pageSize}
            total={data.total || 0}
            showSizeChanger
            pageSizeOptions={['12', '20', '40', '60']}
            showQuickJumper
            showTotal={(total, range) => (total ? `${range[0]}-${range[1]} / ${total} 条` : '0 条')}
            onChange={onPageChange}
            onShowSizeChange={onPageChange}
            disabled={loading}
          />
        </div>
      </div>

      <Drawer
        open={!!drawer}
        onClose={() => setDrawer(null)}
        width={420}
        title={drawer?.title || drawer?.video_title || '作品详情'}
        destroyOnClose
      >
        {drawer ? (
          <div className="wb-drawer">
            <div className="wb-drawer-meta">
              <span className={`wb-plat ${PLAT_CLASS[drawer.platform] || ''}`}>
                {platformMap[drawer.platform]?.label || drawer.platform}
              </span>
              <span className="wb-muted">
                发布于 {fmtPubDate(drawer.published_at)}
              </span>
            </div>
            <div className="wb-drawer-section">
              <h4>封面</h4>
              {drawer.cover_url ? (
                <img className="wb-drawer-cover" src={drawer.cover_url} alt="" referrerPolicy="no-referrer" />
              ) : (
                <div className="wb-card-cover-empty" style={{ height: 160 }}>无封面</div>
              )}
            </div>
            <div className="wb-drawer-section">
              <h4>数据</h4>
              <div className="wb-metric-grid">
                <div className="wb-metric"><div className="v">{fmtNum(drawer.plays)}</div><div className="l">播放</div></div>
                <div className="wb-metric"><div className="v">{fmtNum(drawer.likes)}</div><div className="l">点赞</div></div>
                <div className="wb-metric"><div className="v">{fmtNum(drawer.comments)}</div><div className="l">评论</div></div>
                <div className="wb-metric"><div className="v">{fmtNum(drawer.shares)}</div><div className="l">转发</div></div>
                <div className="wb-metric"><div className="v">{fmtNum(drawer.favorites)}</div><div className="l">收藏</div></div>
              </div>
            </div>
            <div className="wb-drawer-section">
              <h4>诊断 · {drawer.diag_tag || '正常'}</h4>
              <ul className="wb-diag-list">
                {(drawer.diag_tips || ['数据表现正常，可继续观察']).map((tip) => (
                  <li
                    key={tip}
                    className={drawer.diag === 'hot' || drawer.diag === 'consult' ? 'ok' : ''}
                  >
                    {tip}
                  </li>
                ))}
              </ul>
            </div>
            <Space wrap>
              {drawer.publish_url ? (
                <Button
                  type="primary"
                  icon={<LinkOutlined />}
                  href={drawer.publish_url}
                  target="_blank"
                  rel="noreferrer"
                >
                  在平台查看
                </Button>
              ) : null}
              <Button
                icon={<SyncOutlined />}
                loading={rowSyncing === drawer.id}
                onClick={() => handleRowSync(drawer.id)}
              >
                同步本条
              </Button>
            </Space>
            {drawer.engagement_synced_at ? (
              <p className="wb-drawer-sync">上次同步 {formatDateTime(drawer.engagement_synced_at)}</p>
            ) : null}
          </div>
        ) : null}
      </Drawer>

      <p className="wb-note">
        数据来自平台导入与本系统发布任务。登录/同步使用本系统专用浏览器（与日常 Chrome 不互通）。
        超时约 {Math.round(API_LONG_TIMEOUT / 1000)}s。
      </p>
    </div>
  )
}
