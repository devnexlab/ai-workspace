// src/features/pet/PetChat.jsx
import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import api from "../../api/client";
import { API_LONG_TIMEOUT } from "../../config";
import ZhiZaiAvatar from "./ZhiZaiAvatar";
var MODE_HINT = {
  data: "\u53EA\u67E5\u672C\u5730\u5E93\xB7\u4E0D\u8054\u7F51",
  web: "\u53EA\u8054\u7F51\u641C\u7D22\xB7\u4E0D\u67E5\u5E93"
};
var SUGGESTS = [
  "\u5E2E\u6211\u628A\u70ED\u70B9\u548C\u80A1\u7968\u7B80\u62A5\u66F4\u65B0\u4E00\u4E0B",
  "\u6700\u8FD1\u89C6\u9891\u505A\u5230\u54EA\u4E86\uFF1F",
  "\u5E2E\u6211\u5B89\u6392\u6BCF\u5929\u65E9\u4E0A\u81EA\u52A8\u65E5\u66F4\u51FA\u7247",
  "\u6839\u636E\u77E5\u8BC6\u5E93\u5199\u4E00\u6761\u517B\u8001\u91D1\u53E3\u64AD\u5F00\u5934",
  "\u4ECA\u5929\u5317\u5411\u8D44\u91D1\u600E\u4E48\u6837\uFF1F"
];
var WELCOME = "\u4F60\u597D\uFF0C\u6211\u662F\u667A\u4ED4\u3002\u4F60\u968F\u4FBF\u8BF4\u5C31\u884C\u3002\u82E5\u6211\u4E0D\u592A\u786E\u5B9A\u4F60\u60F3\u505A\u4EC0\u4E48\uFF0C\u4F1A\u5148\u7ED9\u4F60\u51E0\u4E2A\u9009\u9879\u786E\u8BA4\uFF0C\u518D\u52A8\u624B\u2014\u2014\u907F\u514D\u641E\u9519\u3002";
var SKIN_KEY = "pet_chat_skin";
var POS_KEY = "pet_chat_pos";
var SESSION_KEY = "pet_chat_session_id";
var PET_SIZE = 72;
var DRAG_THRESHOLD = 6;
var SKINS = [
  { key: "violet", label: "\u7D2B\u7F57\u5170", fab: "linear-gradient(145deg, #7d7dff, #5b5bd6 55%, #4a4ab8)", primary: "#5b5bd6", soft: "#eef0ff", glow: "rgba(91,91,214,.35)" },
  { key: "teal", label: "\u9752\u77F3", fab: "linear-gradient(145deg, #4fd1c5, #0d9488 55%, #0f766e)", primary: "#0d9488", soft: "#e6f7f5", glow: "rgba(13,148,136,.35)" },
  { key: "coral", label: "\u73CA\u745A", fab: "linear-gradient(145deg, #fb923c, #ea580c 55%, #c2410c)", primary: "#ea580c", soft: "#fff4ed", glow: "rgba(234,88,12,.35)" },
  { key: "sky", label: "\u6674\u7A7A", fab: "linear-gradient(145deg, #60a5fa, #2563eb 55%, #1d4ed8)", primary: "#2563eb", soft: "#eff6ff", glow: "rgba(37,99,235,.35)" },
  { key: "slate", label: "\u58A8\u7070", fab: "linear-gradient(145deg, #94a3b8, #475569 55%, #334155)", primary: "#475569", soft: "#f1f5f9", glow: "rgba(71,85,105,.35)" }
];
function welcomeMsg() {
  return { id: `w-${Date.now()}`, role: "bot", content: WELCOME };
}
function loadSkin() {
  try {
    const k = localStorage.getItem(SKIN_KEY);
    if (SKINS.some((s) => s.key === k)) return k;
  } catch {
  }
  return "violet";
}
function loadPos() {
  try {
    const raw = localStorage.getItem(POS_KEY);
    if (!raw) return { right: 20, bottom: 20 };
    const p = JSON.parse(raw);
    if (typeof p?.right === "number" && typeof p?.bottom === "number") {
      return { right: p.right, bottom: p.bottom };
    }
  } catch {
  }
  return { right: 20, bottom: 20 };
}
function loadSavedSessionId() {
  try {
    const v = localStorage.getItem(SESSION_KEY);
    if (!v) return null;
    const n = Number(v);
    return Number.isFinite(n) && n > 0 ? n : null;
  } catch {
    return null;
  }
}
function saveSessionId(id) {
  try {
    if (id) localStorage.setItem(SESSION_KEY, String(id));
    else localStorage.removeItem(SESSION_KEY);
  } catch {
  }
}
function clampPos(right, bottom) {
  const maxRight = Math.max(8, window.innerWidth - PET_SIZE - 8);
  const maxBottom = Math.max(8, window.innerHeight - PET_SIZE - 8);
  return {
    right: Math.min(maxRight, Math.max(8, right)),
    bottom: Math.min(maxBottom, Math.max(8, bottom))
  };
}
function fmtSessionTime(s) {
  if (!s) return "";
  const t = String(s).replace("T", " ").slice(0, 16);
  return t;
}
function PetChat() {
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [express, setExpress] = useState("idle");
  const [showTip, setShowTip] = useState(true);
  const [showBadge, setShowBadge] = useState(true);
  const [showSkins, setShowSkins] = useState(false);
  const [showHistory, setShowHistory] = useState(false);
  const [sessions, setSessions] = useState([]);
  const [sessionsLoading, setSessionsLoading] = useState(false);
  const [skin, setSkin] = useState(loadSkin);
  const [pos, setPos] = useState(loadPos);
  const [dragging, setDragging] = useState(false);
  const [netOn, setNetOn] = useState(false);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [restoring, setRestoring] = useState(true);
  const [sessionId, setSessionId] = useState(null);
  const [messages, setMessages] = useState([welcomeMsg()]);
  const bodyRef = useRef(null);
  const textareaRef = useRef(null);
  const dragRef = useRef(null);
  const restoredRef = useRef(false);
  const skinMeta = SKINS.find((s) => s.key === skin) || SKINS[0];
  const applySessionId = (id) => {
    setSessionId(id);
    saveSessionId(id);
  };
  const restoreSession = async (id) => {
    if (!id) {
      setMessages([welcomeMsg()]);
      applySessionId(null);
      return;
    }
    try {
      const res = await api.get(`/pet-chat/sessions/${id}`);
      const list = res?.messages || [];
      if (!list.length) {
        setMessages([welcomeMsg()]);
        applySessionId(id);
        return;
      }
      setMessages(list);
      applySessionId(id);
    } catch {
      setMessages([welcomeMsg()]);
      applySessionId(null);
    }
  };
  const loadSessionList = async () => {
    setSessionsLoading(true);
    try {
      const res = await api.get("/pet-chat/sessions");
      setSessions(res?.sessions || []);
    } catch {
      setSessions([]);
    } finally {
      setSessionsLoading(false);
    }
  };
  useEffect(() => {
    if (restoredRef.current) return;
    restoredRef.current = true;
    const sid = loadSavedSessionId();
    (async () => {
      setRestoring(true);
      if (sid) await restoreSession(sid);
      setRestoring(false);
    })();
  }, []);
  useEffect(() => {
    if (!bodyRef.current) return;
    bodyRef.current.scrollTop = bodyRef.current.scrollHeight;
  }, [messages, open]);
  useEffect(() => {
    try {
      localStorage.setItem(SKIN_KEY, skin);
    } catch {
    }
  }, [skin]);
  useEffect(() => {
    try {
      localStorage.setItem(POS_KEY, JSON.stringify(pos));
    } catch {
    }
  }, [pos]);
  useEffect(() => {
    const onResize = () => setPos((p) => clampPos(p.right, p.bottom));
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);
  const toggleOpen = () => {
    setOpen((v) => {
      const next = !v;
      if (next) {
        setShowTip(false);
        setShowBadge(false);
      } else {
        setShowSkins(false);
        setShowHistory(false);
      }
      return next;
    });
  };
  const onFabPointerDown = (e) => {
    if (e.button != null && e.button !== 0) return;
    e.currentTarget.setPointerCapture?.(e.pointerId);
    dragRef.current = {
      pointerId: e.pointerId,
      startX: e.clientX,
      startY: e.clientY,
      startRight: pos.right,
      startBottom: pos.bottom,
      moved: false
    };
  };
  const onFabPointerMove = (e) => {
    const d = dragRef.current;
    if (!d || d.pointerId !== e.pointerId) return;
    const dx = e.clientX - d.startX;
    const dy = e.clientY - d.startY;
    if (!d.moved && Math.hypot(dx, dy) < DRAG_THRESHOLD) return;
    d.moved = true;
    setDragging(true);
    setShowTip(false);
    setPos(clampPos(d.startRight - dx, d.startBottom - dy));
  };
  const endFabPointer = (e) => {
    const d = dragRef.current;
    if (!d || e.pointerId != null && d.pointerId !== e.pointerId) return;
    const wasDrag = d.moved;
    dragRef.current = null;
    setDragging(false);
    if (!wasDrag) toggleOpen();
  };
  const clearChat = () => {
    applySessionId(null);
    setMessages([welcomeMsg()]);
    setShowHistory(false);
  };
  const openHistory = () => {
    setShowSkins(false);
    setShowHistory((v) => {
      const next = !v;
      if (next) loadSessionList();
      return next;
    });
  };
  const pickSession = async (id) => {
    setShowHistory(false);
    setBusy(true);
    try {
      await restoreSession(id);
    } finally {
      setBusy(false);
    }
  };
  const pickSkin = (key) => {
    setSkin(key);
    setShowSkins(false);
  };
  const send = async (text) => {
    const q = (text ?? input).trim();
    if (!q || busy) return;
    setInput("");
    setBusy(true);
    setShowHistory(false);
    const userMsg = { id: `u-${Date.now()}`, role: "user", content: q };
    const typingId = `t-${Date.now()}`;
    setMessages((prev) => [
      ...prev,
      userMsg,
      {
        id: typingId,
        role: "bot",
        typing: true,
        steps: [
          { text: "\u8BFB\u53D6\u5BF9\u8BDD\u4E0A\u4E0B\u6587\u2026", state: "run" },
          { text: "\u89C4\u5212\u5E76\u6267\u884C\u2026", state: "run" }
        ]
      }
    ]);
    try {
      const res = await api.post(
        "/pet-chat",
        { message: q, source: netOn ? "web" : "data", session_id: sessionId },
        { timeout: API_LONG_TIMEOUT }
      );
      if (res?.session_id) applySessionId(res.session_id);
      setMessages(
        (prev) => prev.filter((m) => m.id !== typingId).concat({
          id: `b-${Date.now()}`,
          role: "bot",
          content: res?.answer || "\uFF08\u65E0\u56DE\u7B54\uFF09",
          steps: res?.steps || [],
          cites: res?.cites || [],
          choices: res?.choices || []
        })
      );
      setExpress("happy");
      setTimeout(() => setExpress("idle"), 1400);
    } catch (err) {
      const msg = err?.error || err?.message || (typeof err === "string" ? err : "\u8BF7\u6C42\u5931\u8D25");
      setMessages(
        (prev) => prev.filter((m) => m.id !== typingId).concat({
          id: `e-${Date.now()}`,
          role: "bot",
          content: `\u51FA\u9519\u4E86\uFF1A${msg}`,
          steps: [{ text: "\u8BF7\u6C42\u5931\u8D25", state: "ok" }]
        })
      );
    } finally {
      setBusy(false);
      textareaRef.current?.focus();
    }
  };
  const onKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  };
  const onCite = (cite) => {
    if (cite?.path) navigate(cite.path);
  };
  const mood = busy ? "thinking" : express;
  const wrapStyle = {
    "--pet-primary": skinMeta.primary,
    "--pet-soft": skinMeta.soft,
    "--pet-fab": skinMeta.fab,
    "--pet-glow": skinMeta.glow,
    right: pos.right,
    bottom: pos.bottom,
    left: "auto",
    top: "auto"
  };
  return /* @__PURE__ */ React.createElement(
    "div",
    {
      className: `pet-wrap${dragging ? " is-dragging" : ""}`,
      style: wrapStyle,
      "data-skin": skin
    },
    /* @__PURE__ */ React.createElement("div", { className: `pet-chat${open ? " open" : ""}`, id: "pet-chat-panel" }, /* @__PURE__ */ React.createElement("div", { className: "pet-chat-head" }, /* @__PURE__ */ React.createElement("div", { className: "pet-chat-avatar" }, /* @__PURE__ */ React.createElement(ZhiZaiAvatar, { size: 30, mood: "idle", skin: skinMeta })), /* @__PURE__ */ React.createElement("div", { className: "pet-chat-head-text" }, /* @__PURE__ */ React.createElement("h3", null, "\u667A\u4ED4 \xB7 \u8FD0\u8425\u603B\u63A7"), /* @__PURE__ */ React.createElement("p", null, sessionId ? `\u4F1A\u8BDD #${sessionId} \xB7 \u5E26\u4E0A\u4E0B\u6587\u7EED\u804A` : "\u65B0\u4F1A\u8BDD \xB7 \u5411\u91CF\u68C0\u7D22 \xB7 \u5BF9\u8BDD\u64CD\u4F5C")), /* @__PURE__ */ React.createElement("div", { className: "pet-chat-head-actions" }, /* @__PURE__ */ React.createElement(
      "button",
      {
        className: `pet-icon-btn${showHistory ? " active" : ""}`,
        type: "button",
        title: "\u5386\u53F2\u5BF9\u8BDD",
        "aria-label": "\u5386\u53F2\u5BF9\u8BDD",
        onClick: openHistory
      },
      "\u2261"
    ), /* @__PURE__ */ React.createElement(
      "button",
      {
        className: `pet-icon-btn${showSkins ? " active" : ""}`,
        type: "button",
        title: "\u5916\u89C2",
        "aria-label": "\u81EA\u5B9A\u4E49\u684C\u5BA0\u5916\u89C2",
        onClick: () => {
          setShowHistory(false);
          setShowSkins((v) => !v);
        }
      },
      "\u25D0"
    ), /* @__PURE__ */ React.createElement(
      "button",
      {
        className: "pet-icon-btn",
        type: "button",
        title: "\u65B0\u4F1A\u8BDD",
        onClick: clearChat
      },
      "\u21BA"
    ), /* @__PURE__ */ React.createElement(
      "button",
      {
        className: "pet-icon-btn",
        type: "button",
        title: "\u5173\u95ED",
        onClick: () => {
          setShowSkins(false);
          setShowHistory(false);
          setOpen(false);
        }
      },
      "\u2715"
    ))), showHistory && /* @__PURE__ */ React.createElement("div", { className: "pet-history", role: "listbox", "aria-label": "\u5386\u53F2\u5BF9\u8BDD" }, /* @__PURE__ */ React.createElement("div", { className: "pet-history-bar" }, /* @__PURE__ */ React.createElement("span", null, "\u5386\u53F2\u5BF9\u8BDD"), /* @__PURE__ */ React.createElement("button", { type: "button", className: "pet-history-new", onClick: clearChat }, "\u65B0\u5EFA")), sessionsLoading ? /* @__PURE__ */ React.createElement("div", { className: "pet-history-empty" }, "\u52A0\u8F7D\u4E2D\u2026") : sessions.length === 0 ? /* @__PURE__ */ React.createElement("div", { className: "pet-history-empty" }, "\u6682\u65E0\u5386\u53F2\uFF0C\u53D1\u4E00\u6761\u6D88\u606F\u540E\u5C31\u4F1A\u4FDD\u5B58") : /* @__PURE__ */ React.createElement("div", { className: "pet-history-list" }, sessions.map((s) => /* @__PURE__ */ React.createElement(
      "button",
      {
        key: s.id,
        type: "button",
        className: `pet-history-item${sessionId === s.id ? " active" : ""}`,
        onClick: () => pickSession(s.id),
        disabled: busy
      },
      /* @__PURE__ */ React.createElement("span", { className: "pet-history-title" }, s.preview || s.title || `\u4F1A\u8BDD #${s.id}`),
      /* @__PURE__ */ React.createElement("span", { className: "pet-history-meta" }, "#", s.id, " \xB7 ", s.msg_count || 0, " \u6761 \xB7 ", fmtSessionTime(s.updated_at))
    )))), showSkins && /* @__PURE__ */ React.createElement("div", { className: "pet-skins", role: "listbox", "aria-label": "\u684C\u5BA0\u5916\u89C2" }, /* @__PURE__ */ React.createElement("span", { className: "pet-skins-label" }, "\u5916\u89C2"), SKINS.map((s) => /* @__PURE__ */ React.createElement(
      "button",
      {
        key: s.key,
        type: "button",
        className: `pet-skin-swatch${skin === s.key ? " active" : ""}`,
        title: s.label,
        "aria-label": s.label,
        style: { background: s.fab },
        onClick: () => pickSkin(s.key)
      }
    ))), /* @__PURE__ */ React.createElement("div", { className: "pet-chat-body", ref: bodyRef }, restoring ? /* @__PURE__ */ React.createElement("div", { className: "pet-msg bot" }, /* @__PURE__ */ React.createElement("div", { className: "pet-msg-bubble" }, /* @__PURE__ */ React.createElement("div", { className: "pet-msg-text" }, "\u6B63\u5728\u6062\u590D\u4E0A\u6B21\u5BF9\u8BDD\u2026"))) : null, !restoring && messages.map((m) => /* @__PURE__ */ React.createElement(
      "div",
      {
        key: m.id,
        className: `pet-msg ${m.role === "user" ? "user" : "bot"}`
      },
      /* @__PURE__ */ React.createElement("div", { className: "pet-msg-bubble" }, m.typing ? /* @__PURE__ */ React.createElement(React.Fragment, null, /* @__PURE__ */ React.createElement("span", { className: "pet-typing" }, /* @__PURE__ */ React.createElement("i", null), /* @__PURE__ */ React.createElement("i", null), /* @__PURE__ */ React.createElement("i", null)), m.steps?.length > 0 && /* @__PURE__ */ React.createElement("div", { className: "pet-agent-steps" }, m.steps.map((s, i) => /* @__PURE__ */ React.createElement("div", { className: "pet-step", key: i }, /* @__PURE__ */ React.createElement("span", { className: `pet-dot ${s.state || "run"}` }), /* @__PURE__ */ React.createElement("span", null, s.text))))) : /* @__PURE__ */ React.createElement(React.Fragment, null, /* @__PURE__ */ React.createElement("div", { className: "pet-msg-text" }, m.content), m.choices?.length > 0 && /* @__PURE__ */ React.createElement("div", { className: "pet-choices" }, m.choices.map((c, i) => /* @__PURE__ */ React.createElement(
        "button",
        {
          key: c.id || i,
          type: "button",
          className: "pet-choice",
          disabled: busy,
          onClick: () => send(c.message || c.label)
        },
        c.label || c.message
      ))), m.steps?.length > 0 && /* @__PURE__ */ React.createElement("div", { className: "pet-agent-steps" }, m.steps.map((s, i) => /* @__PURE__ */ React.createElement("div", { className: "pet-step", key: i }, /* @__PURE__ */ React.createElement("span", { className: `pet-dot ${s.state || "ok"}` }), /* @__PURE__ */ React.createElement("span", null, s.text)))), m.cites?.length > 0 && /* @__PURE__ */ React.createElement("div", { className: "pet-cites" }, m.cites.map((c, i) => /* @__PURE__ */ React.createElement(
        "button",
        {
          key: i,
          type: "button",
          className: "pet-cite",
          onClick: () => onCite(c)
        },
        /* @__PURE__ */ React.createElement("span", { className: "pet-cite-score" }, c.score),
        /* @__PURE__ */ React.createElement("span", { className: "pet-cite-body" }, /* @__PURE__ */ React.createElement("span", { className: "pet-cite-title" }, c.title), /* @__PURE__ */ React.createElement("span", { className: "pet-cite-meta" }, c.meta))
      )))))
    ))), /* @__PURE__ */ React.createElement("div", { className: "pet-chat-foot" }, /* @__PURE__ */ React.createElement("div", { className: "pet-suggests" }, SUGGESTS.map((s) => /* @__PURE__ */ React.createElement(
      "button",
      {
        key: s,
        type: "button",
        className: "pet-sug",
        disabled: busy,
        onClick: () => send(s)
      },
      s
    ))), /* @__PURE__ */ React.createElement("div", { className: "pet-composer" }, /* @__PURE__ */ React.createElement("div", { className: "pet-composer-input" }, /* @__PURE__ */ React.createElement(
      "textarea",
      {
        ref: textareaRef,
        rows: 1,
        placeholder: "\u7EE7\u7EED\u95EE\uFF0C\u6216\u70B9 \u2261 \u67E5\u770B\u5386\u53F2\u2026",
        value: input,
        disabled: busy || restoring,
        onChange: (e) => setInput(e.target.value),
        onKeyDown
      }
    ), /* @__PURE__ */ React.createElement("div", { className: "pet-source" }, /* @__PURE__ */ React.createElement(
      "div",
      {
        className: `pet-source-switch${netOn ? " on" : ""}`,
        role: "switch",
        "aria-checked": netOn,
        tabIndex: 0,
        title: netOn ? MODE_HINT.web : MODE_HINT.data,
        onClick: () => setNetOn((v) => !v),
        onKeyDown: (e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            setNetOn((v) => !v);
          }
        }
      },
      /* @__PURE__ */ React.createElement("span", { className: "pet-source-text" }, netOn ? "\u8054\u7F51" : "\u672C\u5730"),
      /* @__PURE__ */ React.createElement("span", { className: "pet-source-thumb" })
    ))), /* @__PURE__ */ React.createElement(
      "button",
      {
        className: "pet-send",
        type: "button",
        disabled: busy || restoring || !input.trim(),
        onClick: () => send()
      },
      "\u53D1\u9001"
    )), /* @__PURE__ */ React.createElement("div", { className: "pet-foot-note" }, "\u540C\u4F1A\u8BDD\u81EA\u52A8\u5E26\u4E0A\u4E0B\u6587\uFF1B\u5237\u65B0\u9875\u9762\u4F1A\u6062\u590D\u4E0A\u6B21\u5BF9\u8BDD\u3002\u70B9 \u2261 \u53EF\u5207\u6362\u5386\u53F2\u3002"))),
    showTip && !open && !dragging && /* @__PURE__ */ React.createElement("div", { className: "pet-tip" }, "\u70B9\u6211\u63D0\u95EE \xB7 \u6309\u4F4F\u53EF\u62D6\u52A8"),
    /* @__PURE__ */ React.createElement(
      "button",
      {
        className: `pet-fab${open ? " open" : ""}${dragging ? " dragging" : ""}`,
        type: "button",
        title: "\u667A\u4ED4 \xB7 \u6570\u636E\u95EE\u7B54\uFF08\u6309\u4F4F\u62D6\u52A8\uFF09",
        "aria-label": "\u6253\u5F00\u6570\u636E\u95EE\u7B54\uFF0C\u6309\u4F4F\u53EF\u62D6\u52A8",
        onPointerDown: onFabPointerDown,
        onPointerMove: onFabPointerMove,
        onPointerUp: endFabPointer,
        onPointerCancel: endFabPointer,
        onClick: (e) => e.preventDefault()
      },
      showBadge && !open && /* @__PURE__ */ React.createElement("span", { className: "pet-badge" }, "1"),
      /* @__PURE__ */ React.createElement(ZhiZaiAvatar, { size: 46, mood, skin: skinMeta })
    )
  );
}
export {
  PetChat as default
};
