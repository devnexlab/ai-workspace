import { useState, useMemo } from 'react'
import { Layout, Tooltip, Button, Drawer } from 'antd'
import {
  DashboardOutlined,
  FireOutlined,
  FileTextOutlined,
  VideoCameraOutlined,
  RocketOutlined,
  TeamOutlined,
  UserAddOutlined,
  SettingOutlined,
  BulbOutlined,
  StockOutlined,
  LineChartOutlined,
  RobotOutlined,
  ApartmentOutlined,
  RightOutlined,
  QuestionCircleOutlined,
  MenuOutlined,
  CloseOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
} from '@ant-design/icons'
import { Outlet, useLocation, useNavigate } from 'react-router-dom'
import { APP_NAME } from '../config'
import NotificationBell from '../features/notifications/NotificationBell'
import TodoBell from '../features/notifications/TodoBell'
import PetChat from '../features/pet/PetChat'
import ThemeToggle from '../components/ui/ThemeToggle'

const { Header, Sider, Content } = Layout

const BRAND_NAME = '智能运营台'

const pageTitleMap = {
  '/': '运营仪表盘',
  '/hot-topics': '热点情报',
  '/scripts': '文案管理',
  '/videos': '视频生产',
  '/publish': '发布中心',
  '/customers': '客户列表',
  '/leads': '线索池',
  '/knowledge': '知识库',
  '/agents': 'AI Agent',
  '/workflows': 'AI助手',
  '/stocks': '市场概览',
  '/stocks/watchlist': '自选股',
  '/settings': '系统设置',
}

const sectionLabelMap = {
  '/': '总览',
  '/hot-topics': '内容运营',
  '/scripts': '内容运营',
  '/videos': '内容运营',
  '/publish': '内容运营',
  '/customers': '客户管理',
  '/leads': '客户管理',
  '/knowledge': 'AI 智能',
  '/agents': 'AI 智能',
  '/workflows': 'AI 智能',
  '/stocks': '股票研究',
  '/stocks/watchlist': '股票研究',
  '/settings': '系统',
}

const navGroups = [
  {
    label: '总览',
    items: [{ key: '/', icon: <DashboardOutlined />, label: '运营仪表盘' }],
  },
  {
    label: '内容运营',
    items: [
      { key: '/hot-topics', icon: <FireOutlined />, label: '热点情报' },
      { key: '/scripts', icon: <FileTextOutlined />, label: '文案管理' },
      { key: '/videos', icon: <VideoCameraOutlined />, label: '视频生产' },
      { key: '/publish', icon: <RocketOutlined />, label: '发布中心' },
    ],
  },
  {
    label: '客户管理',
    items: [
      { key: '/customers', icon: <TeamOutlined />, label: '客户列表' },
      { key: '/leads', icon: <UserAddOutlined />, label: '线索池' },
    ],
  },
  {
    label: 'AI 智能',
    items: [
      { key: '/knowledge', icon: <BulbOutlined />, label: '知识库' },
      { key: '/agents', icon: <RobotOutlined />, label: 'AI Agent' },
      { key: '/workflows', icon: <ApartmentOutlined />, label: 'AI助手' },
    ],
  },
  {
    label: '股票研究',
    items: [
      { key: '/stocks', icon: <StockOutlined />, label: '市场概览' },
      { key: '/stocks/watchlist', icon: <LineChartOutlined />, label: '自选股' },
    ],
  },
  {
    label: '系统',
    items: [{ key: '/settings', icon: <SettingOutlined />, label: '系统设置' }],
  },
]

function isNavActive(pathname, key) {
  if (key === '/') return pathname === '/'
  if (key === '/settings') return pathname.startsWith('/settings')
  if (key === '/stocks') return pathname === '/stocks' || pathname === '/stocks/'
  return pathname === key || pathname.startsWith(`${key}/`)
}

function NavContent({ collapsed, onNavigate }) {
  const location = useLocation()
  return (
    <nav className="app-sider-nav">
      {navGroups.map((group) => (
        <div key={group.label} className="app-nav-group">
          {!collapsed && <div className="app-nav-group-label">{group.label}</div>}
          {group.items.map((item) => {
            const active = isNavActive(location.pathname, item.key)
            return (
              <button
                key={item.key}
                type="button"
                className={`app-nav-item${active ? ' active' : ''}`}
                title={collapsed ? item.label : undefined}
                onClick={() => onNavigate(item.key)}
              >
                <span className="app-nav-icon">{item.icon}</span>
                {!collapsed && <span className="app-nav-text">{item.label}</span>}
              </button>
            )
          })}
        </div>
      ))}
    </nav>
  )
}

export default function MainLayout() {
  const [collapsed, setCollapsed] = useState(false)
  const [mobileOpen, setMobileOpen] = useState(false)
  const navigate = useNavigate()
  const location = useLocation()

  const selectedKey = useMemo(() => {
    if (location.pathname.startsWith('/settings')) return '/settings'
    return location.pathname
  }, [location.pathname])

  const pageTitle = pageTitleMap[selectedKey] || APP_NAME
  const sectionLabel = sectionLabelMap[selectedKey] || '总览'

  const go = (key) => {
    navigate(key)
    setMobileOpen(false)
  }

  return (
    <Layout className="app-shell">
      <Sider
        className="app-sider"
        collapsible
        collapsed={collapsed}
        trigger={null}
        width={220}
        collapsedWidth={64}
        style={{
          height: '100vh',
          position: 'sticky',
          top: 0,
          left: 0,
        }}
      >
        <div className="app-brand">
          <span className="app-brand-icon">智</span>
          {!collapsed && <span className="app-brand-text">{BRAND_NAME}</span>}
          <button
            type="button"
            className="app-collapse-btn"
            title={collapsed ? '展开侧边栏' : '折叠侧边栏'}
            onClick={() => setCollapsed((v) => !v)}
          >
            {collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
          </button>
        </div>

        <NavContent collapsed={collapsed} onNavigate={go} />

        <div className="app-sider-footer">
          <div className="app-user-card" title={collapsed ? '顾问' : undefined}>
            <div className="app-user-avatar">顾</div>
            {!collapsed && (
              <div className="app-user-info">
                <div className="app-user-name">顾问</div>
                <div className="app-user-plan">本地工作台</div>
              </div>
            )}
          </div>
        </div>
      </Sider>

      <Layout className="app-main">
        <Header className="app-header">
          <div className="app-header-left">
            <button
              type="button"
              className="app-menu-btn"
              aria-label="打开菜单"
              onClick={() => setMobileOpen(true)}
            >
              <MenuOutlined />
            </button>
            <div className="app-header-title">
              <span className="crumb">{sectionLabel}</span>
              <span className="sep">
                <RightOutlined />
              </span>
              <span className="current">{pageTitle}</span>
            </div>
          </div>
          <div className="app-header-right">
            <div className="app-header-actions">
              <NotificationBell />
              <TodoBell />
              <ThemeToggle />
              <Tooltip
                title={(
                  <div style={{ maxWidth: 260, lineHeight: 1.55 }}>
                    <div style={{ fontWeight: 600, marginBottom: 4 }}>待办说明</div>
                    <div>汇总运营待处理事项：待出片文案、待生成视频、待发布任务、待跟进客户。点击待办图标可查看明细并跳转处理。</div>
                  </div>
                )}
                placement="bottomRight"
                mouseEnterDelay={0.35}
                mouseLeaveDelay={0.08}
              >
                <Button
                  type="text"
                  className="app-icon-btn"
                  aria-label="待办帮助"
                  icon={<QuestionCircleOutlined />}
                />
              </Tooltip>
            </div>
          </div>
        </Header>
        <Content className="app-content">
          <Outlet />
        </Content>
      </Layout>

      {/* 移动端抽屉式侧栏 */}
      <Drawer
        placement="left"
        open={mobileOpen}
        onClose={() => setMobileOpen(false)}
        width={240}
        closable={false}
        className="app-mobile-drawer"
        styles={{ body: { padding: 0, background: 'var(--bg-sidebar)' } }}
        title={null}
      >
        <div className="app-brand app-brand--mobile">
          <span className="app-brand-icon">智</span>
          <span className="app-brand-text">{BRAND_NAME}</span>
          <button
            type="button"
            className="app-collapse-btn"
            aria-label="关闭菜单"
            onClick={() => setMobileOpen(false)}
          >
            <CloseOutlined />
          </button>
        </div>
        <NavContent collapsed={false} onNavigate={go} />
      </Drawer>

      <PetChat />
    </Layout>
  )
}
