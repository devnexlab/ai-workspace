import { useContext } from 'react'
import { MoonOutlined, SunOutlined } from '@ant-design/icons'
import { Tooltip } from 'antd'
import ThemeContext from '../../theme/ThemeContext'
import './ui.css'

/** 浅/深色主题切换按钮（顶栏使用）。 */
export default function ThemeToggle() {
  const { mode, toggle } = useContext(ThemeContext)

  return (
    <Tooltip title={mode === 'dark' ? '切换到浅色' : '切换到深色'} mouseEnterDelay={0.35} mouseLeaveDelay={0.08}>
      <button
        type="button"
        className="app-icon-btn ui-theme-toggle"
        aria-label="切换主题"
        aria-pressed={mode === 'dark'}
        onClick={toggle}
      >
        {mode === 'dark' ? <SunOutlined /> : <MoonOutlined />}
      </button>
    </Tooltip>
  )
}
