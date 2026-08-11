import { useId } from 'react'
import './ZhiZaiAvatar.css'

/**
 * 智仔 2.0 形象组件
 * 设计方向：参考「智仔 2.0」3D 角色规范
 * - 深色面罩 + 发光大眼
 * - 头顶能量触角 + 光球
 * - 向后飘逸的侧发/耳饰
 * - 小身体 + 披风 + 胸前徽章
 * - 颜色跟随 skin.primary / skin.soft 自动适配 5 套配色
 * - mood: idle（常态）/ thinking（思考）/ happy（开心）
 */
export default function ZhiZaiAvatar({
  skin,
  mood = 'idle',
  size = 44,
  className = '',
}) {
  const uid = useId().replace(/[:]/g, '')
  const primary = skin?.primary || '#5b5bd6'
  const soft = skin?.soft || '#eef0ff'
  const dark = '#1a1230' // 深色面罩底色（固定深紫黑，不随皮肤）

  return (
    <svg
      viewBox="0 0 120 120"
      width={size}
      height={size}
      className={`zhi-zai ${mood}${className ? ' ' + className : ''}`}
      role="img"
      aria-label="智仔"
    >
      <defs>
        <filter id={`zz-glow-${uid}`} x="-50%" y="-50%" width="200%" height="200%">
          <feGaussianBlur stdDeviation="2.5" result="blur" />
          <feComposite in="SourceGraphic" in2="blur" operator="over" />
        </filter>
        <filter id={`zz-soft-shadow-${uid}`} x="-50%" y="-50%" width="200%" height="200%">
          <feGaussianBlur stdDeviation="3" />
        </filter>

        <radialGradient id={`zz-head-${uid}`} cx="35%" cy="28%" r="85%">
          <stop offset="0%" stopColor="#ffffff" />
          <stop offset="35%" stopColor={soft} />
          <stop offset="85%" stopColor={primary} />
          <stop offset="100%" stopColor={primary} stopOpacity="0.95" />
        </radialGradient>

        <radialGradient id={`zz-face-${uid}`} cx="50%" cy="35%" r="75%">
          <stop offset="0%" stopColor="#3a2a6a" />
          <stop offset="60%" stopColor={dark} />
          <stop offset="100%" stopColor="#0d0818" />
        </radialGradient>

        <radialGradient id={`zz-face-highlight-${uid}`} cx="50%" cy="20%" r="60%">
          <stop offset="0%" stopColor="#ffffff" stopOpacity="0.18" />
          <stop offset="100%" stopColor="#ffffff" stopOpacity="0" />
        </radialGradient>

        <radialGradient id={`zz-eye-${uid}`} cx="40%" cy="35%" r="70%">
          <stop offset="0%" stopColor="#ffffff" />
          <stop offset="100%" stopColor="#e0e7ff" />
        </radialGradient>

        <linearGradient id={`zz-cape-${uid}`} x1="0%" y1="0%" x2="0%" y2="100%">
          <stop offset="0%" stopColor={primary} stopOpacity="0.95" />
          <stop offset="100%" stopColor={dark} stopOpacity="0.95" />
        </linearGradient>

        <linearGradient id={`zz-body-${uid}`} x1="30%" y1="0%" x2="70%" y2="100%">
          <stop offset="0%" stopColor={soft} />
          <stop offset="100%" stopColor={primary} />
        </linearGradient>

        <linearGradient id={`zz-antenna-${uid}`} x1="0%" y1="100%" x2="0%" y2="0%">
          <stop offset="0%" stopColor={primary} />
          <stop offset="100%" stopColor="#ffffff" />
        </linearGradient>

        <radialGradient id={`zz-antenna-ball-${uid}`} cx="35%" cy="30%" r="70%">
          <stop offset="0%" stopColor="#ffffff" />
          <stop offset="50%" stopColor={soft} />
          <stop offset="100%" stopColor={primary} />
        </radialGradient>
      </defs>

      {/* 地面投影 */}
      <ellipse
        cx="60"
        cy="104"
        rx="28"
        ry="7"
        fill={dark}
        opacity="0.16"
        filter={`url(#zz-soft-shadow-${uid})`}
      />

      {/* 披风（身体后面） */}
      <path
        d="M38 78 C30 82 26 92 28 102 C34 98 86 98 92 102 C94 92 90 82 82 78 C78 84 42 84 38 78 Z"
        fill={`url(#zz-cape-${uid})`}
        opacity="0.92"
      />
      <path
        d="M60 80 L60 100"
        stroke="#ffffff"
        strokeOpacity="0.12"
        strokeWidth="1.5"
      />

      {/* 脚 */}
      <ellipse cx="46" cy="100" rx="10" ry="6" fill={soft} stroke={primary} strokeOpacity="0.2" />
      <ellipse cx="74" cy="100" rx="10" ry="6" fill={soft} stroke={primary} strokeOpacity="0.2" />

      {/* 身体 */}
      <ellipse cx="60" cy="84" rx="22" ry="18" fill={`url(#zz-body-${uid})`} />
      <ellipse cx="60" cy="78" rx="18" ry="10" fill="#ffffff" opacity="0.22" />

      {/* 胸前徽章 */}
      <circle cx="60" cy="82" r="7" fill="#ffffff" opacity="0.18" />
      <path
        d="M60 78 L62 81 L66 81 L62.8 83.5 L64 87 L60 85 L56 87 L57.2 83.5 L54 81 L58 81 Z"
        fill="#ffffff"
        opacity="0.9"
      />

      {/* 侧发/耳饰（左） */}
      <path
        d="M30 48 C18 44 12 54 16 64 C20 72 28 70 32 64 C34 58 34 52 30 48 Z"
        fill={primary}
        opacity="0.85"
      />
      <path
        d="M28 52 C22 50 18 56 20 62 C22 66 26 65 28 62"
        fill="none"
        stroke="#ffffff"
        strokeOpacity="0.25"
        strokeWidth="1.5"
        strokeLinecap="round"
      />

      {/* 侧发/耳饰（右） */}
      <path
        d="M90 48 C102 44 108 54 104 64 C100 72 92 70 88 64 C86 58 86 52 90 48 Z"
        fill={primary}
        opacity="0.85"
      />
      <path
        d="M92 52 C98 50 102 56 100 62 C98 66 94 65 92 62"
        fill="none"
        stroke="#ffffff"
        strokeOpacity="0.25"
        strokeWidth="1.5"
        strokeLinecap="round"
      />

      {/* 头部主体 */}
      <circle cx="60" cy="48" r="36" fill={`url(#zz-head-${uid})`} />
      <circle
        cx="60"
        cy="48"
        r="36"
        fill="none"
        stroke={primary}
        strokeOpacity="0.18"
        strokeWidth="1"
      />

      {/* 深色面罩 */}
      <ellipse cx="60" cy="52" rx="29" ry="24" fill={`url(#zz-face-${uid})`} />
      <ellipse cx="60" cy="44" rx="24" ry="16" fill={`url(#zz-face-highlight-${uid})`} />

      {/* 面罩边缘发光 */}
      <ellipse
        cx="60"
        cy="52"
        rx="29"
        ry="24"
        fill="none"
        stroke={primary}
        strokeOpacity="0.35"
        strokeWidth="1.2"
      />

      {/* 能量触角 */}
      <path
        d="M60 18 Q64 8 72 6 Q74 5 74 3 Q74 1 72 1 Q70 1 70 3"
        fill="none"
        stroke={`url(#zz-antenna-${uid})`}
        strokeWidth="3.5"
        strokeLinecap="round"
        filter={`url(#zz-glow-${uid})`}
        className="zz-antenna"
      />
      <circle cx="72" cy="2" r="5" fill={`url(#zz-antenna-ball-${uid})`} filter={`url(#zz-glow-${uid})`} className="zz-antenna-ball" />

      {/* 表情 */}
      <Face mood={mood} uid={uid} primary={primary} />
    </svg>
  )
}

function Face({ mood, uid, primary }) {
  const eyeFilter = `url(#zz-glow-${uid})`

  if (mood === 'thinking') {
    return (
      <g className="zz-face-thinking">
        {/* 左眼眯起 */}
        <path d="M42 52 Q48 49 54 52" fill="none" stroke="#ffffff" strokeWidth="3" strokeLinecap="round" filter={eyeFilter} />
        {/* 右眼圆睁 */}
        <ellipse cx="74" cy="50" rx="7" ry="8" fill={`url(#zz-eye-${uid})`} filter={eyeFilter} />
        <circle cx="76" cy="48" r="2.2" fill="#0d0818" />
        <circle cx="72" cy="47" r="1.6" fill="#ffffff" opacity="0.9" />
        {/* 小嘴 */}
        <circle cx="60" cy="66" r="2.5" fill="#ffffff" opacity="0.8" />
      </g>
    )
  }

  if (mood === 'happy') {
    return (
      <g className="zz-face-happy">
        {/* 弯月眼 */}
        <path d="M40 52 Q48 44 56 52" fill="none" stroke="#ffffff" strokeWidth="3.5" strokeLinecap="round" filter={eyeFilter} />
        <path d="M64 52 Q72 44 80 52" fill="none" stroke="#ffffff" strokeWidth="3.5" strokeLinecap="round" filter={eyeFilter} />
        {/* 开心嘴 */}
        <path d="M52 62 Q60 74 68 62 Z" fill="#ffffff" opacity="0.95" />
        {/* 腮红 */}
        <ellipse cx="40" cy="62" rx="5" ry="3" fill={primary} opacity="0.25" filter={`url(#zz-glow-${uid})`} />
        <ellipse cx="80" cy="62" rx="5" ry="3" fill={primary} opacity="0.25" filter={`url(#zz-glow-${uid})`} />
      </g>
    )
  }

  // idle
  return (
    <g className="zz-face-idle">
      <ellipse cx="46" cy="50" rx="8" ry="9.5" fill={`url(#zz-eye-${uid})`} filter={eyeFilter} />
      <ellipse cx="74" cy="50" rx="8" ry="9.5" fill={`url(#zz-eye-${uid})`} filter={eyeFilter} />
      <circle cx="48" cy="48" r="2.6" fill="#0d0818" />
      <circle cx="76" cy="48" r="2.6" fill="#0d0818" />
      <circle cx="44" cy="46" r="1.8" fill="#ffffff" opacity="0.95" />
      <circle cx="72" cy="46" r="1.8" fill="#ffffff" opacity="0.95" />
      <path d="M54 64 Q60 70 66 64" fill="none" stroke="#ffffff" strokeWidth="2.8" strokeLinecap="round" opacity="0.9" />
    </g>
  )
}
