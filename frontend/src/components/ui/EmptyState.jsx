import './ui.css'

/**
 * 统一空状态。icon 可传 antd 图标节点或 emoji。
 */
export default function EmptyState({ icon, title, description, actions }) {
  return (
    <div className="ui-empty">
      {icon ? <span className="ui-empty-icon">{icon}</span> : null}
      {title ? <div className="ui-empty-title">{title}</div> : null}
      {description ? <div className="ui-empty-desc">{description}</div> : null}
      {actions ? <div className="ui-empty-actions">{actions}</div> : null}
    </div>
  )
}
