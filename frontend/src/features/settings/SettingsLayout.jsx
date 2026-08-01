import { Outlet, useLocation, Navigate } from 'react-router-dom'
import { Spin } from 'antd'
import { useEffect, useState } from 'react'
import { settingsApi } from '../../api'

/**
 * 系统设置容器：加载模块元数据，/settings 跳转到默认模块。
 * 二级导航由侧栏「系统设置」子菜单负责。
 */
export default function SettingsLayout() {
  const [modules, setModules] = useState([])
  const [loading, setLoading] = useState(true)
  const location = useLocation()

  useEffect(() => {
    settingsApi.modules()
      .then(res => setModules(res.modules || []))
      .finally(() => setLoading(false))
  }, [])

  if (loading) {
    return <div style={{ textAlign: 'center', padding: 80 }}><Spin size="large" /></div>
  }

  if (location.pathname === '/settings' || location.pathname === '/settings/') {
    const first = modules[0]?.path || 'ai'
    return <Navigate to={`/settings/${first}`} replace />
  }

  return (
    <div>
      <Outlet context={{ modules }} />
    </div>
  )
}
