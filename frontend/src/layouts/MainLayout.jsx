import { useState, useMemo, useEffect } from 'react'
import { Layout, Menu } from 'antd'
import {
  DashboardOutlined,
  FireOutlined,
  FileTextOutlined,
  VideoCameraOutlined,
  RocketOutlined,
  TeamOutlined,
  SettingOutlined,
  BulbOutlined,
  StockOutlined,
  RobotOutlined,
  ApartmentOutlined,
  AppstoreOutlined,
  FundProjectionScreenOutlined,
} from '@ant-design/icons'
import { Outlet, useLocation, useNavigate } from 'react-router-dom'
import { APP_NAME } from '../config'

const { Header, Sider, Content } = Layout

// path → parent group key mapping for auto-expand
const pathGroupMap = {
  '/hot-topics': 'content',
  '/scripts': 'content',
  '/videos': 'content',
  '/publish': 'content',
  '/customers': 'customer',
  '/knowledge': 'ai',
  '/agents': 'ai',
  '/workflows': 'ai',
  '/settings/ai': 'settings',
  '/settings/collectors': 'settings',
  '/settings/publish': 'settings',
  '/settings/media': 'settings',
  '/settings/content': 'settings',
}

const menuItems = [
  { key: '/', icon: <DashboardOutlined />, label: '总览' },
  {
    key: 'content',
    icon: <FundProjectionScreenOutlined />,
    label: '内容运营',
    children: [
      { key: '/hot-topics', icon: <FireOutlined />, label: '内容情报' },
      { key: '/scripts', icon: <FileTextOutlined />, label: '文案中心' },
      { key: '/videos', icon: <VideoCameraOutlined />, label: '视频中心' },
      { key: '/publish', icon: <RocketOutlined />, label: '发布中心' },
    ],
  },
  {
    key: 'customer',
    icon: <TeamOutlined />,
    label: '客户管理',
    children: [
      { key: '/customers', icon: <TeamOutlined />, label: '客户列表' },
    ],
  },
  {
    key: 'ai',
    icon: <AppstoreOutlined />,
    label: 'AI 智能',
    children: [
      { key: '/knowledge', icon: <BulbOutlined />, label: 'AI 知识库' },
      { key: '/agents', icon: <RobotOutlined />, label: 'Agent 中心' },
      { key: '/workflows', icon: <ApartmentOutlined />, label: 'AI助手' },
    ],
  },
  { key: '/stocks', icon: <StockOutlined />, label: '股票研究' },
  {
    key: 'settings',
    icon: <SettingOutlined />,
    label: '系统设置',
    children: [
      { key: '/settings/ai', label: 'AI 大模型' },
      { key: '/settings/collectors', label: '采集平台' },
      { key: '/settings/publish', label: '发布平台' },
      { key: '/settings/media', label: '配音与视频' },
      { key: '/settings/content', label: '内容运营' },
    ],
  },
]

export default function MainLayout() {
  const [collapsed, setCollapsed] = useState(false)
  const navigate = useNavigate()
  const location = useLocation()

  const selectedKey = useMemo(() => {
    if (location.pathname.startsWith('/settings')) {
      const parts = location.pathname.split('/').filter(Boolean)
      if (parts.length >= 2) return `/${parts[0]}/${parts[1]}`
      return '/settings/ai'
    }
    return location.pathname
  }, [location.pathname])

  const [openKeys, setOpenKeys] = useState(() => {
    const group = pathGroupMap[location.pathname]
    return group ? [group] : []
  })

  useEffect(() => {
    const group = pathGroupMap[selectedKey] || pathGroupMap[location.pathname]
    if (group) {
      setOpenKeys(prev => (prev.includes(group) ? prev : [...prev, group]))
    }
  }, [location.pathname, selectedKey])

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider
        collapsible
        collapsed={collapsed}
        onCollapse={setCollapsed}
        style={{
          overflow: 'auto',
          height: '100vh',
          position: 'sticky',
          top: 0,
          left: 0,
        }}
      >
        <div style={{
          height: 56,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          color: '#fff',
          fontWeight: 700,
          fontSize: collapsed ? 14 : 16,
          whiteSpace: 'nowrap',
          overflow: 'hidden',
          background: 'rgba(255,255,255,0.08)',
          margin: '8px 12px',
          borderRadius: 8,
        }}>
          {collapsed ? 'AI' : APP_NAME}
        </div>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[selectedKey]}
          openKeys={openKeys}
          onOpenChange={setOpenKeys}
          items={menuItems}
          onClick={({ key }) => {
            if (key.startsWith('/')) navigate(key)
          }}
        />
      </Sider>
      <Layout>
        <Header style={{
          padding: '0 24px',
          background: '#fff',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          boxShadow: '0 1px 4px rgba(0,0,0,0.06)',
          position: 'sticky',
          top: 0,
          zIndex: 10,
        }}>
          <span style={{ fontSize: 16, fontWeight: 600, color: '#1a1a2e' }}>
            {APP_NAME}
          </span>
          <span style={{ fontSize: 13, color: '#999' }}>PRD V1.2</span>
        </Header>
        <Content style={{
          margin: 16,
          padding: 24,
          background: '#fff',
          borderRadius: 12,
          minHeight: 280,
        }}>
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  )
}
