import './ui.css'

/**
 * 统一页面头部：标题 + 描述 + 操作区。
 * icon 接收 antd 图标节点。
 */
export default function PageHeader({ title, description, icon, actions }) {
  return (
    <header className="ui-page-header">
      <div className="ui-page-header-main">
        <h1 className="ui-page-title">
          {icon ? <span className="ui-page-icon">{icon}</span> : null}
          {title}
        </h1>
        {description ? <p className="ui-page-desc">{description}</p> : null}
      </div>
      {actions ? <div className="ui-page-actions">{actions}</div> : null}
    </header>
  )
}
