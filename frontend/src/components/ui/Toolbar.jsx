import './ui.css'

/** 统一工具栏：左侧筛选 / 右侧操作。 */
export default function Toolbar({ left, right }) {
  return (
    <div className="ui-toolbar">
      {left ? <div className="ui-toolbar-left">{left}</div> : <span />}
      {right ? <div className="ui-toolbar-right">{right}</div> : null}
    </div>
  )
}
