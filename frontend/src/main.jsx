import React from 'react'
import ReactDOM from 'react-dom/client'
import { ConfigProvider } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import App from './App'
import { THEME } from './config'
import './styles/global.css'
import 'dayjs/locale/zh-cn'

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <ConfigProvider
      locale={zhCN}
      theme={{
        token: {
          colorPrimary: THEME.colorPrimary,
          colorInfo: '#3b82f6',
          colorSuccess: '#00b884',
          colorWarning: '#ff9500',
          colorError: '#ff3b5c',
          borderRadius: THEME.borderRadius,
          fontSize: THEME.fontSize,
          controlHeight: THEME.controlHeight,
          colorText: THEME.colorText,
          colorTextSecondary: THEME.colorTextSecondary,
          colorBorder: THEME.colorBorder,
          colorBorderSecondary: '#f3f3f6',
          colorBgLayout: THEME.colorBgLayout,
          colorBgContainer: '#ffffff',
          colorBgElevated: '#ffffff',
          fontFamily:
            '-apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif',
          lineHeight: 1.6,
          wireframe: false,
        },
        components: {
          Button: {
            controlHeight: 34,
            paddingContentHorizontal: 14,
            fontWeight: 500,
            primaryShadow: 'none',
          },
          Input: {
            controlHeight: 34,
            paddingBlock: 4,
          },
          Select: {
            controlHeight: 34,
          },
          Table: {
            headerBg: '#fafafa',
            headerColor: '#6b6b80',
            rowHoverBg: 'rgba(91, 91, 214, 0.02)',
            cellPaddingBlock: 12,
            cellPaddingInline: 16,
            borderColor: '#f3f3f6',
          },
          Card: {
            paddingLG: 20,
          },
          Menu: {
            itemHeight: 36,
            iconSize: 16,
            darkItemBg: 'transparent',
            darkSubMenuItemBg: 'transparent',
            darkItemSelectedBg: 'rgba(91, 91, 214, 0.2)',
            darkItemHoverBg: '#252542',
          },
          Tabs: {
            titleFontSize: 14,
            inkBarColor: '#5b5bd6',
            itemSelectedColor: '#5b5bd6',
            itemHoverColor: '#1e1e2e',
            itemColor: '#6b6b80',
          },
          Form: {
            labelFontSize: 12,
            itemMarginBottom: 16,
          },
          Modal: {
            borderRadiusLG: 16,
          },
          Drawer: {
            paddingLG: 20,
          },
          Segmented: {
            itemSelectedColor: '#5b5bd6',
          },
        },
      }}
    >
      <App />
    </ConfigProvider>
  </React.StrictMode>,
)
