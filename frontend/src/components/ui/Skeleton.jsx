import './ui.css'

/**
 * 轻量骨架屏。lines: 文本行数；showAvatar: 是否带头像方块；height: 块高度。
 */
export default function Skeleton({ lines = 3, showAvatar = false, avatarSize = 40, blockHeight = 16 }) {
  return (
    <div className="ui-skeleton" aria-hidden>
      {showAvatar ? (
        <div className="ui-skeleton-row">
          <span className="ui-skeleton-block ui-skeleton-circle" style={{ width: avatarSize, height: avatarSize }} />
          <span className="ui-skeleton-block ui-skeleton-line" style={{ width: '40%', height: blockHeight }} />
        </div>
      ) : null}
      {Array.from({ length: lines }).map((_, i) => (
        <span
          key={i}
          className="ui-skeleton-block ui-skeleton-line"
          style={{ width: `${90 - i * 12}%`, height: blockHeight }}
        />
      ))}
    </div>
  )
}
