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
          borderRadius: THEME.borderRadius,
          fontSize: THEME.fontSize,
          controlHeight: THEME.controlHeight,
          colorText: THEME.colorText,
          colorTextSecondary: THEME.colorTextSecondary,
          colorBorder: THEME.colorBorder,
          colorBgLayout: THEME.colorBgLayout,
          colorBgContainer: '#ffffff',
          fontFamily:
            '"PingFang SC", "Microsoft YaHei", "Segoe UI", system-ui, -apple-system, sans-serif',
          lineHeight: 1.6,
          wireframe: false,
        },
        components: {
          Button: {
            controlHeight: 36,
            paddingContentHorizontal: 16,
            fontWeight: 500,
          },
          Input: {
            controlHeight: 36,
            paddingBlock: 6,
          },
          Select: {
            controlHeight: 36,
          },
          Table: {
            headerBg: '#f8fafc',
            headerColor: '#475569',
            rowHoverBg: '#f1f5f9',
            cellPaddingBlock: 12,
            cellPaddingInline: 14,
          },
          Card: {
            paddingLG: 20,
          },
          Menu: {
            itemHeight: 44,
            iconSize: 16,
          },
          Tabs: {
            titleFontSize: 14,
          },
          Form: {
            labelFontSize: 14,
            itemMarginBottom: 18,
          },
          Modal: {
            borderRadiusLG: 14,
          },
          Drawer: {
            paddingLG: 20,
          },
        },
      }}
    >
      <App />
    </ConfigProvider>
  </React.StrictMode>,
)
