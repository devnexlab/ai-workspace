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
import NotificationBell from '../features/notifications/NotificationBell'
import TodoBell from '../features/notifications/TodoBell'

const { Header, Sider, Content } = Layout

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
  '/settings/commercial': 'settings',
  '/settings/publish': 'settings',
  '/settings/media': 'settings',
  '/settings/notify': 'settings',
  '/settings/wechat-oa': 'settings',
  '/settings/content': 'settings',
}

const pageTitleMap = {
  '/': '运营仪表盘',
  '/hot-topics': '内容情报',
  '/scripts': '文案中心',
  '/videos': '视频中心',
  '/publish': '发布中心',
  '/customers': '客户管理',
  '/knowledge': '知识库',
  '/agents': 'Agent 中心',
  '/workflows': 'AI 助手',
  '/stocks': '股票研究',
  '/settings/ai': 'AI 大模型',
  '/settings/collectors': '采集平台',
  '/settings/commercial': '官方数据台',
  '/settings/publish': '发布平台',
  '/settings/media': '配音与视频',
  '/settings/notify': '消息推送',
  '/settings/wechat-oa': '微信服务号',
  '/settings/content': '内容运营',
}

const menuItems = [
  { key: '/', icon: <DashboardOutlined />, label: '运营仪表盘' },
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
      { key: '/knowledge', icon: <BulbOutlined />, label: '知识库' },
      { key: '/agents', icon: <RobotOutlined />, label: 'Agent 中心' },
      { key: '/workflows', icon: <ApartmentOutlined />, label: 'AI 助手' },
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
      { key: '/settings/commercial', label: '官方数据台' },
      { key: '/settings/publish', label: '发布平台' },
      { key: '/settings/media', label: '配音与视频' },
      { key: '/settings/notify', label: '消息推送' },
      { key: '/settings/wechat-oa', label: '微信服务号' },
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

  const pageTitle = pageTitleMap[selectedKey] || APP_NAME

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
    <Layout className="app-shell">
      <Sider
        className="app-sider"
        collapsible
        collapsed={collapsed}
        onCollapse={setCollapsed}
        width={220}
        collapsedWidth={64}
        style={{
          overflow: 'auto',
          height: '100vh',
          position: 'sticky',
          top: 0,
          left: 0,
        }}
      >
        <div className="app-brand">
          <span className="app-brand-icon">AI</span>
          {!collapsed && <span className="app-brand-text">{APP_NAME}</span>}
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
        <Header className="app-header">
          <div className="app-header-title">
            <span className="crumb">{APP_NAME}</span>
            <span className="sep">/</span>
            <span>{pageTitle}</span>
          </div>
          <div className="app-header-actions">
            <TodoBell />
            <NotificationBell />
          </div>
        </Header>
        <Content className="app-content">
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  )
}
