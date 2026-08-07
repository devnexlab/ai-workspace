import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import api from '../../api/client'
import { API_LONG_TIMEOUT } from '../../config'
import './PetChat.css'

const MODES = [
  { key: 'auto', label: '智能 Agent' },
  { key: 'knowledge', label: '偏知识库' },
  { key: 'script', label: '偏文案' },
  { key: 'stock', label: '偏股票' },
]

const SUGGESTS = [
  '今日北向资金净流入多少？哪些行业流入最多？',
  '重疾险和医疗险有什么区别？',
  '根据知识库写一条养老金口播开头',
  '我的持仓里谁跌破成本了？',
]

const WELCOME =
  '你好，我是智仔。可以问知识库、文案、股票持仓等系统数据。我会先检索再回答，并标出引用。'

const SKIN_KEY = 'pet_chat_skin'

const SKINS = [
  { key: 'violet', label: '紫罗兰', fab: 'linear-gradient(145deg, #7d7dff, #5b5bd6 55%, #4a4ab8)', primary: '#5b5bd6', soft: '#eef0ff', glow: 'rgba(91,91,214,.35)' },
  { key: 'teal', label: '青石', fab: 'linear-gradient(145deg, #4fd1c5, #0d9488 55%, #0f766e)', primary: '#0d9488', soft: '#e6f7f5', glow: 'rgba(13,148,136,.35)' },
  { key: 'coral', label: '珊瑚', fab: 'linear-gradient(145deg, #fb923c, #ea580c 55%, #c2410c)', primary: '#ea580c', soft: '#fff4ed', glow: 'rgba(234,88,12,.35)' },
  { key: 'sky', label: '晴空', fab: 'linear-gradient(145deg, #60a5fa, #2563eb 55%, #1d4ed8)', primary: '#2563eb', soft: '#eff6ff', glow: 'rgba(37,99,235,.35)' },
  { key: 'slate', label: '墨灰', fab: 'linear-gradient(145deg, #94a3b8, #475569 55%, #334155)', primary: '#475569', soft: '#f1f5f9', glow: 'rgba(71,85,105,.35)' },
]

function loadSkin() {
  try {
    const k = localStorage.getItem(SKIN_KEY)
    if (SKINS.some((s) => s.key === k)) return k
  } catch {
    /* ignore */
  }
  return 'violet'
}

function PetFace({ mini = false }) {
  return (
    <span className={`pet-face${mini ? ' mini-face' : ''}`}>
      <span className="pet-eye l" />
      <span className="pet-eye r" />
      <span className="pet-blush l" />
      <span className="pet-blush r" />
      <span className="pet-mouth" />
    </span>
  )
}

export default function PetChat() {
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)
  const [showTip, setShowTip] = useState(true)
  const [showBadge, setShowBadge] = useState(true)
  const [showSkins, setShowSkins] = useState(false)
  const [skin, setSkin] = useState(loadSkin)
  const [mode, setMode] = useState('auto')
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [sessionId, setSessionId] = useState(null)
  const [messages, setMessages] = useState([
    { id: 'welcome', role: 'bot', content: WELCOME },
  ])
  const bodyRef = useRef(null)
  const textareaRef = useRef(null)

  const skinMeta = SKINS.find((s) => s.key === skin) || SKINS[0]

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

  const toggleOpen = () => {
    setOpen((v) => {
      const next = !v
      if (next) {
        setShowTip(false)
        setShowBadge(false)
      } else {
        setShowSkins(false)
      }
      return next
    })
  }

  const clearChat = () => {
    setSessionId(null)
    setMessages([{ id: `w-${Date.now()}`, role: 'bot', content: WELCOME }])
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
          { text: '规划检索路径…', state: 'run' },
          { text: '向量召回中…', state: 'run' },
        ],
      },
    ])

    try {
      const res = await api.post(
        '/pet-chat',
        { message: q, mode, session_id: sessionId },
        { timeout: API_LONG_TIMEOUT },
      )
      if (res?.session_id) setSessionId(res.session_id)
      setMessages((prev) =>
        prev
          .filter((m) => m.id !== typingId)
          .concat({
            id: `b-${Date.now()}`,
            role: 'bot',
            content: res?.answer || '（无回答）',
            steps: res?.steps || [],
            cites: res?.cites || [],
          }),
      )
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
    if (cite?.path) navigate(cite.path)
  }

  const wrapStyle = {
    '--pet-primary': skinMeta.primary,
    '--pet-soft': skinMeta.soft,
    '--pet-fab': skinMeta.fab,
    '--pet-glow': skinMeta.glow,
  }

  return (
    <div className="pet-wrap" style={wrapStyle} data-skin={skin}>
      <div className={`pet-chat${open ? ' open' : ''}`} id="pet-chat-panel">
        <div className="pet-chat-head">
          <div className="pet-chat-avatar">
            <PetFace mini />
          </div>
          <div className="pet-chat-head-text">
            <h3>智仔 · 数据问答</h3>
            <p>向量检索 · Agent 编排 · 引用来源</p>
          </div>
          <div className="pet-chat-head-actions">
            <button
              className={`pet-icon-btn${showSkins ? ' active' : ''}`}
              type="button"
              title="外观"
              aria-label="自定义桌宠外观"
              onClick={() => setShowSkins((v) => !v)}
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
                setOpen(false)
              }}
            >
              ✕
            </button>
          </div>
        </div>

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

        <div className="pet-chat-modes">
          {MODES.map((m) => (
            <button
              key={m.key}
              type="button"
              className={`pet-mode${mode === m.key ? ' active' : ''}`}
              onClick={() => setMode(m.key)}
            >
              {m.label}
            </button>
          ))}
        </div>

        <div className="pet-chat-body" ref={bodyRef}>
          {messages.map((m) => (
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
            <textarea
              ref={textareaRef}
              rows={1}
              placeholder="问系统里的知识、文案、股票…"
              value={input}
              disabled={busy}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={onKeyDown}
            />
            <button
              className="pet-send"
              type="button"
              disabled={busy || !input.trim()}
              onClick={() => send()}
            >
              发送
            </button>
          </div>
          <div className="pet-foot-note">
            回答基于向量召回与系统工具；请核对引用。股票相关不构成投资建议。
          </div>
        </div>
      </div>

      {showTip && !open && (
        <div className="pet-tip">点我，用系统数据问一问～</div>
      )}
      <button
        className={`pet-fab${open ? ' open' : ''}`}
        type="button"
        title="智仔 · 数据问答"
        aria-label="打开数据问答"
        onClick={toggleOpen}
      >
        {showBadge && !open && <span className="pet-badge">1</span>}
        <PetFace />
      </button>
    </div>
  )
}
