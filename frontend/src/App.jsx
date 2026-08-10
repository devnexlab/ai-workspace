import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import MainLayout from './layouts/MainLayout'

import Dashboard from './features/dashboard/Dashboard'
import HotTopics from './features/content/HotTopics'
import Scripts from './features/content/Scripts'
import Videos from './features/content/Videos'
import Publish from './features/content/Publish'
import Customers from './features/crm/Customers'
import Leads from './features/crm/Leads'
import KnowledgeBase from './features/knowledge/KnowledgeBase'
import Stocks from './features/stocks/Stocks'
import Agents from './features/agents/Agents'
import Workflows from './features/agents/Workflows'
import SettingsLayout from './features/settings/SettingsLayout'
import SettingsModulePage from './features/settings/SettingsModulePage'
import WechatOaAbout from './features/wechat/WechatOaAbout'
import WechatOaBook from './features/wechat/WechatOaBook'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        {/* 服务号菜单可挂的客户页（无侧栏） */}
        <Route path="/m/about" element={<WechatOaAbout />} />
        <Route path="/m/book" element={<WechatOaBook />} />

        <Route path="/" element={<MainLayout />}>
          <Route index element={<Dashboard />} />
          <Route path="hot-topics" element={<HotTopics />} />
          <Route path="scripts" element={<Scripts />} />
          <Route path="videos" element={<Videos />} />
          <Route path="publish" element={<Publish />} />
          <Route path="customers" element={<Customers />} />
          <Route path="leads" element={<Leads />} />
          <Route path="knowledge" element={<KnowledgeBase />} />
          <Route path="stocks" element={<Stocks section="market" />} />
          <Route path="stocks/watchlist" element={<Stocks section="watchlist" />} />
          <Route path="agents" element={<Agents />} />
          <Route path="workflows" element={<Workflows />} />
          <Route path="settings" element={<SettingsLayout />}>
            <Route index element={<Navigate to="ai" replace />} />
            <Route path=":moduleKey" element={<SettingsModulePage />} />
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
