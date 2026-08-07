import { useCallback, useEffect, useState } from 'react'
import { Button, Empty, Spin, Tag, Tooltip } from 'antd'
import {
  LoadingOutlined,
  ReloadOutlined,
  RightOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import { videosApi, publishApi, stocksApi, remindersApi } from '../../api'
import './LiveActivity.css'

const POLL_MS = 4000

const SESSION_LABEL = {
  need_login: '待登录',
  pending_review: '待确认',
  filling: '填写中',
  opening: '打开中',
  running: '进行中',
}

const REMINDER_TYPE = {
  birthday: '生日',
  policy_expiry: '保单到期',
  silent: '沉默',
  high_intent: '高意向',
  follow_up: '跟进',
  stock_alert: '股价预警',
  general: '提醒',
}

function formatElapsedSec(sec) {
  const n = Number(sec)
  if (!Number.isFinite(n) || n < 0) return null
  const s = Math.floor(n)
  if (s < 60) return `${s}秒`
  const m = Math.floor(s / 60)
  const r = s % 60
  if (m < 60) return r ? `${m}分${r}秒` : `${m}分`
  const h = Math.floor(m / 60)
  return `${h}小时${m % 60}分`
}

function isVideoProcessing(row) {
  return ['voice_status', 'subtitle_status', 'video_status', 'export_status']
    .some(k => row?.[k] === 'processing')
}

function isVideoFailed(row) {
  return ['voice_status', 'subtitle_status', 'video_status', 'export_status']
    .some(k => row?.[k] === 'failed')
}

function videoStage(row) {
  if (row.export_status === 'processing') return { label: '导出成片', pct: 85 }
  if (row.video_status === 'processing') return { label: '画面合成', pct: 65 }
  if (row.subtitle_status === 'processing') return { label: '字幕生成', pct: 40 }
  if (row.voice_status === 'processing') return { label: '配音生成', pct: 18 }
  if (row.export_status === 'failed' || row.video_status === 'failed') return { label: '合成失败', pct: 0 }
  if (row.subtitle_status === 'failed') return { label: '字幕失败', pct: 0 }
  if (row.voice_status === 'failed') return { label: '配音失败', pct: 0 }
  return { label: '制作中', pct: 10 }
}

function todayStr() {
  return new Date().toISOString().slice(0, 10)
}

function isDueReminder(item) {
  if (!item?.remind_date) return true
  return String(item.remind_date).slice(0, 10) <= todayStr()
}

export default function LiveActivity() {
  const navigate = useNavigate()
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [updatedAt, setUpdatedAt] = useState(null)
  const [videos, setVideos] = useState([])
  const [failedVideos, setFailedVideos] = useState([])
  const [sessions, setSessions] = useState([])
  const [screenings, setScreenings] = useState([])
  const [alerts, setAlerts] = useState([])

  const load = useCallback(async (silent = false) => {
    if (!silent) setLoading(true)
    else setRefreshing(true)

    const [videosRes, sessionsRes, screeningRes, remindersRes] = await Promise.allSettled([
      videosApi.list({ page: 1, pageSize: 40 }),
      publishApi.sessions(),
      stocksApi.screeningHistory(),
      remindersApi.list({ status: 'pending', scope: 'all' }),
    ])

    const videoList = videosRes.status === 'fulfilled' ? (videosRes.value?.list || []) : []
    const processing = videoList.filter(isVideoProcessing)
    const failed = videoList.filter(isVideoFailed).slice(0, 8)

    // 补充合成耗时（status 接口会算实时 elapsed）
    const enriched = await Promise.all(processing.slice(0, 8).map(async (row) => {
      try {
        const st = await videosApi.getStatus(row.id)
        return {
          ...row,
          voice_status: st.voice_status ?? row.voice_status,
          subtitle_status: st.subtitle_status ?? row.subtitle_status,
          video_status: st.video_status ?? row.video_status,
          export_status: st.export_status ?? row.export_status,
          compose_elapsed_sec: st.compose_elapsed_sec ?? row.compose_elapsed_sec,
          error_msg: st.error_msg ?? row.error_msg,
        }
      } catch {
        return row
      }
    }))
    // 若某任务已结束，从进行中列表剔除
    const stillRunning = enriched.filter(isVideoProcessing)
    const newlyFailed = enriched.filter(isVideoFailed)
    const history = screeningRes.status === 'fulfilled'
      ? (screeningRes.value?.list || screeningRes.value || [])
      : []
    const historyList = Array.isArray(history) ? history : []
    const activeScreenings = historyList.filter(s => s.status === 'running' || s.status === 'pending')

    const reminders = remindersRes.status === 'fulfilled' ? (remindersRes.value?.list || []) : []
    const alertItems = reminders
      .filter(r => r.type === 'stock_alert' || isDueReminder(r))
      .slice(0, 12)

    setVideos(stillRunning)
    setFailedVideos([...newlyFailed, ...failed.filter(f => !newlyFailed.some(n => n.id === f.id))].slice(0, 8))
    setSessions(sessionsRes.status === 'fulfilled' ? (sessionsRes.value?.list || []) : [])
    setScreenings(activeScreenings)
    setAlerts(alertItems)
    setUpdatedAt(new Date())
    setLoading(false)
    setRefreshing(false)
  }, [])

  useEffect(() => {
    load(false)
    const timer = setInterval(() => load(true), POLL_MS)
    return () => clearInterval(timer)
  }, [load])

  const jobCount = videos.length + sessions.length + screenings.length
  const alertCount = alerts.length + failedVideos.length

  const clock = updatedAt
    ? updatedAt.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
    : '--:--:--'

  if (loading) {
    return (
      <div className="live-page live-page-loading">
        <Spin size="large" tip="加载实时状态…" />
      </div>
    )
  }

  return (
    <div className="live-page">
      <div className="live-head">
        <div>
          <h1 className="live-title">实时动态</h1>
          <p className="live-desc">进行中的任务与即时告警。空闲时保持干净；有任务时在此盯进度。</p>
        </div>
        <div className="live-head-actions">
          <span className={`live-pulse${refreshing ? ' is-refreshing' : ''}`}>
            <i />
            每 {POLL_MS / 1000} 秒刷新 · {clock}
          </span>
          <Tooltip title="立即刷新">
            <Button
              type="text"
              className="live-refresh-btn"
              icon={<ReloadOutlined spin={refreshing} />}
              onClick={() => load(true)}
            />
          </Tooltip>
        </div>
      </div>

      <div className="live-summary">
        <div className="live-sum">
          <div className="live-sum-k">视频合成中</div>
          <div className="live-sum-v">{videos.length}</div>
        </div>
        <div className="live-sum">
          <div className="live-sum-k">发布会话</div>
          <div className={`live-sum-v${sessions.length ? ' warn' : ''}`}>{sessions.length}</div>
        </div>
        <div className="live-sum">
          <div className="live-sum-k">选股扫描</div>
          <div className="live-sum-v">{screenings.length}</div>
        </div>
        <div className="live-sum">
          <div className="live-sum-k">告警 / 失败</div>
          <div className={`live-sum-v${alertCount ? ' err' : ''}`}>{alertCount}</div>
        </div>
      </div>

      <div className="live-grid">
        <section className="live-card">
          <div className="live-card-h">
            <h3>进行中的任务</h3>
            <span className="live-card-meta">{jobCount ? `${jobCount} 项` : '空闲'}</span>
          </div>

          {!jobCount && (
            <Empty
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              description="当前没有进行中的任务"
              className="live-empty"
            />
          )}

          {videos.map(row => {
            const stage = videoStage(row)
            const elapsed = formatElapsedSec(row.compose_elapsed_sec)
            return (
              <button
                key={`v-${row.id}`}
                type="button"
                className="live-job"
                onClick={() => navigate(`/videos?focus=${row.id}&pending=1`)}
              >
                <div className="live-job-top">
                  <div>
                    <div className="live-job-title">视频合成 · {row.title || `#${row.id}`}</div>
                    <div className="live-job-sub">
                      阶段：{stage.label}
                      {elapsed ? ` · 已耗时 ${elapsed}` : ''}
                    </div>
                  </div>
                  <Tag color="processing" icon={<LoadingOutlined />}>合成中</Tag>
                </div>
                <div className="live-bar"><i style={{ width: `${stage.pct}%` }} /></div>
                <div className="live-job-meta">
                  <span>跳转视频生产</span>
                  <RightOutlined />
                </div>
              </button>
            )
          })}

          {sessions.map(s => (
            <button
              key={`s-${s.id}`}
              type="button"
              className="live-job"
              onClick={() => navigate(s.task_id ? `/publish?focus=${s.task_id}` : '/publish')}
            >
              <div className="live-job-top">
                <div>
                  <div className="live-job-title">发布会话 · {s.label || s.platform}</div>
                  <div className="live-job-sub">
                    {s.message || SESSION_LABEL[s.status] || s.status}
                    {s.detected_url ? ` · 已检测到页面` : ''}
                  </div>
                </div>
                <Tag color="warning">{SESSION_LABEL[s.status] || s.status || '进行中'}</Tag>
              </div>
              <div className="live-job-meta">
                <span>跳转发布中心</span>
                <RightOutlined />
              </div>
            </button>
          ))}

          {screenings.map(s => {
            const msg = s.message || ''
            const m = msg.match(/(\d+)\s*\/\s*(\d+)/)
            const pct = m && Number(m[2]) > 0
              ? Math.min(99, Math.round((Number(m[1]) / Number(m[2])) * 100))
              : 20
            return (
              <button
                key={`sc-${s.id}`}
                type="button"
                className="live-job"
                onClick={() => navigate('/stocks')}
              >
                <div className="live-job-top">
                  <div>
                    <div className="live-job-title">选股扫描 · {s.name || `#${s.id}`}</div>
                    <div className="live-job-sub">{msg || (s.status === 'pending' ? '排队中' : '扫描中')}</div>
                  </div>
                  <Tag color="processing" icon={<LoadingOutlined />}>扫描中</Tag>
                </div>
                <div className="live-bar"><i style={{ width: `${pct}%` }} /></div>
                <div className="live-job-meta">
                  <span>跳转市场概览</span>
                  <RightOutlined />
                </div>
              </button>
            )
          })}
        </section>

        <section className="live-card">
          <div className="live-card-h">
            <h3>即时告警</h3>
            <span className="live-card-meta">{alertCount ? `${alertCount} 条` : '暂无'}</span>
          </div>

          {!alertCount && (
            <Empty
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              description="暂无告警"
              className="live-empty"
            />
          )}

          {failedVideos.map(row => (
            <button
              key={`fv-${row.id}`}
              type="button"
              className="live-alert"
              onClick={() => navigate(`/videos?focus=${row.id}`)}
            >
              <span className="live-dot err" />
              <span className="live-alert-body">
                <span className="live-alert-title">视频合成失败 · {row.title || `#${row.id}`}</span>
                <span className="live-alert-meta">{videoStage(row).label}{row.error_msg ? ` · ${row.error_msg}` : ''}</span>
              </span>
              <Tag color="error">失败</Tag>
            </button>
          ))}

          {alerts.map(item => {
            const isStock = item.type === 'stock_alert'
            return (
              <button
                key={`a-${item.id}`}
                type="button"
                className="live-alert"
                onClick={() => navigate(isStock ? '/stocks/watchlist' : '/customers?tab=reminders')}
              >
                <span className={`live-dot ${isStock ? 'err' : 'warn'}`} />
                <span className="live-alert-body">
                  <span className="live-alert-title">
                    {isStock ? '股价预警' : (REMINDER_TYPE[item.type] || '提醒')}
                    {item.customer_name ? ` · ${item.customer_name}` : ''}
                  </span>
                  <span className="live-alert-meta">
                    {item.title}
                    {item.remind_date ? ` · ${String(item.remind_date).slice(0, 10)}` : ''}
                  </span>
                </span>
                <Tag color={isStock ? 'gold' : 'orange'}>{isStock ? '预警' : '到期'}</Tag>
              </button>
            )
          })}
        </section>
      </div>

      <div className="live-footnote">
        <ThunderboltOutlined />
        <span>数据来自视频合成、发布会话、选股任务与提醒接口的实时轮询，不做历史流水。</span>
      </div>
    </div>
  )
}
