import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import api from '../../api/client'
import { API_LONG_TIMEOUT } from '../../config'
import './PetChat.css'
import ZhiZaiAvatar from './ZhiZaiAvatar'

// 数据源开关提示：data=本地库，web=联网（两者都是取数后分析总结）
const MODE_HINT = {
  data: '本地库：理解问题→查对应业务表→分析总结',
  web: '联网：检索/行情取数→分析总结后回答',
}

const SUGGESTS = [
  '帮我把热点和股票简报更新一下',
  '最近视频做到哪了？',
  '帮我安排每天早上自动日更出片',
  '根据知识库写一条养老金口播开头',
  '今天北向资金怎么样？',
]

const WELCOME =
  '你好，我是智仔。你随便说就行。若我不太确定你想做什么，会先给你几个选项确认，再动手——避免搞错。'

const SKIN_KEY = 'pet_chat_skin'
const POS_KEY = 'pet_chat_pos'
const SESSION_KEY = 'pet_chat_session_id'
const PET_SIZE = 72
const DRAG_THRESHOLD = 6

const SKINS = [
  { key: 'violet', label: '紫罗兰', fab: 'linear-gradient(145deg, #7d7dff, #5b5bd6 55%, #4a4ab8)', primary: '#5b5bd6', soft: '#eef0ff', glow: 'rgba(91,91,214,.35)' },
  { key: 'teal', label: '青石', fab: 'linear-gradient(145deg, #4fd1c5, #0d9488 55%, #0f766e)', primary: '#0d9488', soft: '#e6f7f5', glow: 'rgba(13,148,136,.35)' },
  { key: 'coral', label: '珊瑚', fab: 'linear-gradient(145deg, #fb923c, #ea580c 55%, #c2410c)', primary: '#ea580c', soft: '#fff4ed', glow: 'rgba(234,88,12,.35)' },
  { key: 'sky', label: '晴空', fab: 'linear-gradient(145deg, #60a5fa, #2563eb 55%, #1d4ed8)', primary: '#2563eb', soft: '#eff6ff', glow: 'rgba(37,99,235,.35)' },
  { key: 'slate', label: '墨灰', fab: 'linear-gradient(145deg, #94a3b8, #475569 55%, #334155)', primary: '#475569', soft: '#f1f5f9', glow: 'rgba(71,85,105,.35)' },
]

function welcomeMsg() {
  return { id: `w-${Date.now()}`, role: 'bot', content: WELCOME }
}

function loadSkin() {
  try {
    const k = localStorage.getItem(SKIN_KEY)
    if (SKINS.some((s) => s.key === k)) return k
  } catch {
    /* ignore */
  }
  return 'violet'
}

function loadPos() {
  try {
    const raw = localStorage.getItem(POS_KEY)
    if (!raw) return { right: 20, bottom: 20 }
    const p = JSON.parse(raw)
    if (typeof p?.right === 'number' && typeof p?.bottom === 'number') {
      return { right: p.right, bottom: p.bottom }
    }
  } catch {
    /* ignore */
  }
  return { right: 20, bottom: 20 }
}

function loadSavedSessionId() {
  try {
    const v = localStorage.getItem(SESSION_KEY)
    if (!v) return null
    const n = Number(v)
    return Number.isFinite(n) && n > 0 ? n : null
  } catch {
    return null
  }
}

function saveSessionId(id) {
  try {
    if (id) localStorage.setItem(SESSION_KEY, String(id))
    else localStorage.removeItem(SESSION_KEY)
  } catch {
    /* ignore */
  }
}

function clampPos(right, bottom) {
  const maxRight = Math.max(8, window.innerWidth - PET_SIZE - 8)
  const maxBottom = Math.max(8, window.innerHeight - PET_SIZE - 8)
  return {
    right: Math.min(maxRight, Math.max(8, right)),
    bottom: Math.min(maxBottom, Math.max(8, bottom)),
  }
}

function fmtSessionTime(s) {
  if (!s) return ''
  const t = String(s).replace('T', ' ').slice(0, 16)
  return t
}

export default function PetChat() {
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)
  const [express, setExpress] = useState('idle')
  const [showTip, setShowTip] = useState(true)
  const [showBadge, setShowBadge] = useState(true)
  const [showSkins, setShowSkins] = useState(false)
  const [showHistory, setShowHistory] = useState(false)
  const [sessions, setSessions] = useState([])
  const [sessionsLoading, setSessionsLoading] = useState(false)
  const [skin, setSkin] = useState(loadSkin)
  const [pos, setPos] = useState(loadPos)
  const [dragging, setDragging] = useState(false)
  const [netOn, setNetOn] = useState(false) // false=本地库, true=联网；与角色模式相互独立
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [restoring, setRestoring] = useState(true)
  const [sessionId, setSessionId] = useState(null)
  const [messages, setMessages] = useState([welcomeMsg()])
  const bodyRef = useRef(null)
  const textareaRef = useRef(null)
  const dragRef = useRef(null)
  const restoredRef = useRef(false)

  const skinMeta = SKINS.find((s) => s.key === skin) || SKINS[0]

  const applySessionId = (id) => {
    setSessionId(id)
    saveSessionId(id)
  }

  const restoreSession = async (id) => {
    if (!id) {
      setMessages([welcomeMsg()])
      applySessionId(null)
      return
    }
    try {
      const res = await api.get(`/pet-chat/sessions/${id}`)
      const list = res?.messages || []
      if (!list.length) {
        setMessages([welcomeMsg()])
        applySessionId(id)
        return
      }
      setMessages(list)
      applySessionId(id)
    } catch {
      setMessages([welcomeMsg()])
      applySessionId(null)
    }
  }

  const loadSessionList = async () => {
    setSessionsLoading(true)
    try {
      const res = await api.get('/pet-chat/sessions')
      setSessions(res?.sessions || [])
    } catch {
      setSessions([])
    } finally {
      setSessionsLoading(false)
    }
  }

  useEffect(() => {
    if (restoredRef.current) return
    restoredRef.current = true
    const sid = loadSavedSessionId()
    ;(async () => {
      setRestoring(true)
      if (sid) await restoreSession(sid)
      setRestoring(false)
    })()
  }, [])

  useEffect(() => {
    if (!bodyRef.current) return
    bodyRef.current.scrollTop = bodyRef.current.scrollHeight
  }, [messages, open])

  useEffect(() => {
    try {
      localStorage.setItem(SKIN_KEY, skin)
    } catch {
      /* ignore */
    }
  }, [skin])

  useEffect(() => {
    try {
      localStorage.setItem(POS_KEY, JSON.stringify(pos))
    } catch {
      /* ignore */
    }
  }, [pos])

  useEffect(() => {
    const onResize = () => setPos((p) => clampPos(p.right, p.bottom))
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [])

  const toggleOpen = () => {
    setOpen((v) => {
      const next = !v
      if (next) {
        setShowTip(false)
        setShowBadge(false)
      } else {
        setShowSkins(false)
        setShowHistory(false)
      }
      return next
    })
  }

  const onFabPointerDown = (e) => {
    if (e.button != null && e.button !== 0) return
    e.currentTarget.setPointerCapture?.(e.pointerId)
    dragRef.current = {
      pointerId: e.pointerId,
      startX: e.clientX,
      startY: e.clientY,
      startRight: pos.right,
      startBottom: pos.bottom,
      moved: false,
    }
  }

  const onFabPointerMove = (e) => {
    const d = dragRef.current
    if (!d || d.pointerId !== e.pointerId) return
    const dx = e.clientX - d.startX
    const dy = e.clientY - d.startY
    if (!d.moved && Math.hypot(dx, dy) < DRAG_THRESHOLD) return
    d.moved = true
    setDragging(true)
    setShowTip(false)
    setPos(clampPos(d.startRight - dx, d.startBottom - dy))
  }

  const endFabPointer = (e) => {
    const d = dragRef.current
    if (!d || (e.pointerId != null && d.pointerId !== e.pointerId)) return
    const wasDrag = d.moved
    dragRef.current = null
    setDragging(false)
    if (!wasDrag) toggleOpen()
  }

  const clearChat = () => {
    applySessionId(null)
    setMessages([welcomeMsg()])
    setShowHistory(false)
  }

  const openHistory = () => {
    setShowSkins(false)
    setShowHistory((v) => {
      const next = !v
      if (next) loadSessionList()
      return next
    })
  }

  const pickSession = async (id) => {
    setShowHistory(false)
    setBusy(true)
    try {
      await restoreSession(id)
    } finally {
      setBusy(false)
    }
  }

  const pickSkin = (key) => {
    setSkin(key)
    setShowSkins(false)
  }

  const send = async (text) => {
    const q = (text ?? input).trim()
    if (!q || busy) return
    setInput('')
    setBusy(true)
    setShowHistory(false)
    const userMsg = { id: `u-${Date.now()}`, role: 'user', content: q }
    const typingId = `t-${Date.now()}`
    setMessages((prev) => [
      ...prev,
      userMsg,
      {
        id: typingId,
        role: 'bot',
        typing: true,
        steps: [
          { text: '读取对话上下文…', state: 'run' },
          { text: '规划并执行…', state: 'run' },
        ],
      },
    ])

    try {
      const res = await api.post(
        '/pet-chat',
        { message: q, source: netOn ? 'web' : 'data', session_id: sessionId },
        { timeout: API_LONG_TIMEOUT },
      )
      if (res?.session_id) applySessionId(res.session_id)
      setMessages((prev) =>
        prev
          .filter((m) => m.id !== typingId)
          .concat({
            id: `b-${Date.now()}`,
            role: 'bot',
            content: res?.answer || '（无回答）',
            steps: res?.steps || [],
            cites: res?.cites || [],
            choices: res?.choices || [],
          }),
      )
      setExpress('happy')
      setTimeout(() => setExpress('idle'), 1400)
    } catch (err) {
      const msg =
        err?.error || err?.message || (typeof err === 'string' ? err : '请求失败')
      setMessages((prev) =>
        prev
          .filter((m) => m.id !== typingId)
          .concat({
            id: `e-${Date.now()}`,
            role: 'bot',
            content: `出错了：${msg}`,
            steps: [{ text: '请求失败', state: 'ok' }],
          }),
      )
    } finally {
      setBusy(false)
      textareaRef.current?.focus()
    }
  }

  const onKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      send()
    }
  }

  const onCite = (cite) => {
    const path = cite?.path || ''
    if (/^https?:\/\//i.test(path)) {
      window.open(path, '_blank', 'noopener,noreferrer')
      return
    }
    if (path) navigate(path)
  }

  const mood = busy ? 'thinking' : express

  const wrapStyle = {
    '--pet-primary': skinMeta.primary,
    '--pet-soft': skinMeta.soft,
    '--pet-fab': skinMeta.fab,
    '--pet-glow': skinMeta.glow,
    right: pos.right,
    bottom: pos.bottom,
    left: 'auto',
    top: 'auto',
  }

  return (
    <div
      className={`pet-wrap${dragging ? ' is-dragging' : ''}`}
      style={wrapStyle}
      data-skin={skin}
    >
      <div className={`pet-chat${open ? ' open' : ''}`} id="pet-chat-panel">
        <div className="pet-chat-head">
          <div className="pet-chat-avatar">
            <ZhiZaiAvatar size={30} mood="idle" skin={skinMeta} />
          </div>
          <div className="pet-chat-head-text">
            <h3>智仔 · 运营总控</h3>
            <p>
              {sessionId
                ? `会话 #${sessionId} · 带上下文续聊`
                : '新会话 · 向量检索 · 对话操作'}
            </p>
          </div>
          <div className="pet-chat-head-actions">
            <button
              className={`pet-icon-btn${showHistory ? ' active' : ''}`}
              type="button"
              title="历史对话"
              aria-label="历史对话"
              onClick={openHistory}
            >
              ≡
            </button>
            <button
              className={`pet-icon-btn${showSkins ? ' active' : ''}`}
              type="button"
              title="外观"
              aria-label="自定义桌宠外观"
              onClick={() => {
                setShowHistory(false)
                setShowSkins((v) => !v)
              }}
            >
              ◐
            </button>
            <button
              className="pet-icon-btn"
              type="button"
              title="新会话"
              onClick={clearChat}
            >
              ↺
            </button>
            <button
              className="pet-icon-btn"
              type="button"
              title="关闭"
              onClick={() => {
                setShowSkins(false)
                setShowHistory(false)
                setOpen(false)
              }}
            >
              ✕
            </button>
          </div>
        </div>

        {showHistory && (
          <div className="pet-history" role="listbox" aria-label="历史对话">
            <div className="pet-history-bar">
              <span>历史对话</span>
              <button type="button" className="pet-history-new" onClick={clearChat}>
                新建
              </button>
            </div>
            {sessionsLoading ? (
              <div className="pet-history-empty">加载中…</div>
            ) : sessions.length === 0 ? (
              <div className="pet-history-empty">暂无历史，发一条消息后就会保存</div>
            ) : (
              <div className="pet-history-list">
                {sessions.map((s) => (
                  <button
                    key={s.id}
                    type="button"
                    className={`pet-history-item${sessionId === s.id ? ' active' : ''}`}
                    onClick={() => pickSession(s.id)}
                    disabled={busy}
                  >
                    <span className="pet-history-title">{s.preview || s.title || `会话 #${s.id}`}</span>
                    <span className="pet-history-meta">
                      #{s.id} · {s.msg_count || 0} 条 · {fmtSessionTime(s.updated_at)}
                    </span>
                  </button>
                ))}
              </div>
            )}
          </div>
        )}

        {showSkins && (
          <div className="pet-skins" role="listbox" aria-label="桌宠外观">
            <span className="pet-skins-label">外观</span>
            {SKINS.map((s) => (
              <button
                key={s.key}
                type="button"
                className={`pet-skin-swatch${skin === s.key ? ' active' : ''}`}
                title={s.label}
                aria-label={s.label}
                style={{ background: s.fab }}
                onClick={() => pickSkin(s.key)}
              />
            ))}
          </div>
        )}

        <div className="pet-chat-body" ref={bodyRef}>
          {restoring ? (
            <div className="pet-msg bot">
              <div className="pet-msg-bubble">
                <div className="pet-msg-text">正在恢复上次对话…</div>
              </div>
            </div>
          ) : null}
          {!restoring && messages.map((m) => (
            <div
              key={m.id}
              className={`pet-msg ${m.role === 'user' ? 'user' : 'bot'}`}
            >
              <div className="pet-msg-bubble">
                {m.typing ? (
                  <>
                    <span className="pet-typing">
                      <i /><i /><i />
                    </span>
                    {m.steps?.length > 0 && (
                      <div className="pet-agent-steps">
                        {m.steps.map((s, i) => (
                          <div className="pet-step" key={i}>
                            <span className={`pet-dot ${s.state || 'run'}`} />
                            <span>{s.text}</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </>
                ) : (
                  <>
                    <div className="pet-msg-text">{m.content}</div>
                    {m.choices?.length > 0 && (
                      <div className="pet-choices">
                        {m.choices.map((c, i) => (
                          <button
                            key={c.id || i}
                            type="button"
                            className="pet-choice"
                            disabled={busy}
                            onClick={() => send(c.message || c.label)}
                          >
                            {c.label || c.message}
                          </button>
                        ))}
                      </div>
                    )}
                    {m.steps?.length > 0 && (
                      <div className="pet-agent-steps">
                        {m.steps.map((s, i) => (
                          <div className="pet-step" key={i}>
                            <span className={`pet-dot ${s.state || 'ok'}`} />
                            <span>{s.text}</span>
                          </div>
                        ))}
                      </div>
                    )}
                    {m.cites?.length > 0 && (
                      <div className="pet-cites">
                        {m.cites.map((c, i) => (
                          <button
                            key={i}
                            type="button"
                            className="pet-cite"
                            onClick={() => onCite(c)}
                          >
                            <span className="pet-cite-score">{c.score}</span>
                            <span className="pet-cite-body">
                              <span className="pet-cite-title">{c.title}</span>
                              <span className="pet-cite-meta">{c.meta}</span>
                            </span>
                          </button>
                        ))}
                      </div>
                    )}
                  </>
                )}
              </div>
            </div>
          ))}
        </div>

        <div className="pet-chat-foot">
          <div className="pet-suggests">
            {SUGGESTS.map((s) => (
              <button
                key={s}
                type="button"
                className="pet-sug"
                disabled={busy}
                onClick={() => send(s)}
              >
                {s}
              </button>
            ))}
          </div>
          <div className="pet-composer">
            <div className="pet-composer-input">
              <textarea
                ref={textareaRef}
                rows={1}
                placeholder="继续问，或点 ≡ 查看历史…"
                value={input}
                disabled={busy || restoring}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={onKeyDown}
              />
              <div className="pet-source">
                <div
                  className={`pet-source-switch${netOn ? ' on' : ''}`}
                  role="switch"
                  aria-checked={netOn}
                  tabIndex={0}
                  title={netOn ? MODE_HINT.web : MODE_HINT.data}
                  onClick={() => setNetOn((v) => !v)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault()
                      setNetOn((v) => !v)
                    }
                  }}
                >
                <span className="pet-source-text">
                  {netOn ? '联网' : '本地'}
                </span>
                  <span className="pet-source-thumb" />
                </div>
              </div>
            </div>
            <button
              className="pet-send"
              type="button"
              disabled={busy || restoring || !input.trim()}
              onClick={() => send()}
            >
              发送
            </button>
          </div>
          <div className="pet-foot-note">
            本地=查业务库后分析；联网=检索/行情取数后分析。同会话带上下文，点 ≡ 可切换历史。
          </div>
        </div>
      </div>

      {showTip && !open && !dragging && (
        <div className="pet-tip">点我提问 · 按住可拖动</div>
      )}
      <button
        className={`pet-fab${open ? ' open' : ''}${dragging ? ' dragging' : ''}`}
        type="button"
        title="智仔 · 数据问答（按住拖动）"
        aria-label="打开数据问答，按住可拖动"
        onPointerDown={onFabPointerDown}
        onPointerMove={onFabPointerMove}
        onPointerUp={endFabPointer}
        onPointerCancel={endFabPointer}
        onClick={(e) => e.preventDefault()}
      >
        {showBadge && !open && <span className="pet-badge">1</span>}
        <ZhiZaiAvatar size={46} mood={mood} skin={skinMeta} />
      </button>
    </div>
  )
}
