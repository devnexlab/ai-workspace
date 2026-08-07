/**
 * 系统设置容器：侧栏只进一次，页内左侧 Tab 切换模块。
 */
import { Outlet, useLocation, Navigate, useNavigate } from 'react-router-dom'
import { Spin } from 'antd'
import { useCallback, useEffect, useState } from 'react'
import { settingsApi } from '../../api'
import './Settings.css'

export default function SettingsLayout() {
  const [modules, setModules] = useState([])
  const [loading, setLoading] = useState(true)
  const location = useLocation()
  const navigate = useNavigate()

  const reloadModules = useCallback(() => {
    return settingsApi.modules()
      .then(res => setModules(res.modules || []))
  }, [])

  useEffect(() => {
    reloadModules().finally(() => setLoading(false))
  }, [reloadModules])

  if (loading) {
    return <div style={{ textAlign: 'center', padding: 80 }}><Spin size="large" /></div>
  }

  if (location.pathname === '/settings' || location.pathname === '/settings/') {
    const first = modules[0]?.path || 'ai'
    return <Navigate to={`/settings/${first}`} replace />
  }

  const activePath = location.pathname.replace(/^\/settings\/?/, '').split('/')[0] || 'ai'

  return (
    <div className="settings-page">
      <div className="settings-page-head">
        <h1 className="settings-page-title">系统设置</h1>
        <p className="settings-page-desc">集中管理 AI、采集、发布、媒体与消息等配置。</p>
      </div>

      <div className="settings-frame">
        <nav className="settings-tabs" aria-label="设置模块">
          {modules.map(m => (
            <button
              key={m.path}
              type="button"
              className={`settings-tab${activePath === m.path ? ' active' : ''}`}
              onClick={() => navigate(`/settings/${m.path}`)}
            >
              {m.label}
            </button>
          ))}
        </nav>
        <div className="settings-panel">
          <Outlet context={{ modules, reloadModules }} />
        </div>
      </div>
    </div>
  )
}
