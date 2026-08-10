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
          colorInfo: THEME.colorInfo,
          colorSuccess: THEME.colorSuccess,
          colorWarning: THEME.colorWarning,
          colorError: THEME.colorError,
          borderRadius: THEME.borderRadius,
          borderRadiusLG: THEME.borderRadiusLG,
          borderRadiusSM: 6,
          fontSize: THEME.fontSize,
          controlHeight: THEME.controlHeight,
          colorText: THEME.colorText,
          colorTextSecondary: THEME.colorTextSecondary,
          colorTextTertiary: THEME.colorTextTertiary,
          colorBorder: THEME.colorBorder,
          colorBorderSecondary: THEME.colorBorderSecondary,
          colorBgLayout: THEME.colorBgLayout,
          colorBgContainer: THEME.colorBgContainer,
          colorBgElevated: THEME.colorBgContainer,
          fontFamily:
            '-apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif',
          lineHeight: 1.6,
          wireframe: false,
        },
        components: {
          Button: {
            controlHeight: 34,
            controlHeightSM: 28,
            paddingContentHorizontal: 14,
            fontWeight: 500,
            primaryShadow: 'none',
            defaultShadow: 'none',
            borderRadius: 8,
          },
          Input: {
            controlHeight: 34,
            paddingBlock: 4,
            borderRadius: 8,
          },
          Select: {
            controlHeight: 34,
            borderRadius: 8,
          },
          Table: {
            headerBg: '#fafafa',
            headerColor: '#6b6b80',
            headerSplitColor: '#ededf0',
            rowHoverBg: 'rgba(91, 91, 214, 0.02)',
            cellPaddingBlock: 12,
            cellPaddingInline: 16,
            borderColor: '#f3f3f6',
            headerBorderRadius: 0,
          },
          Card: {
            paddingLG: 20,
            headerHeight: 52,
            borderRadiusLG: 12,
          },
          Tag: {
            defaultBg: '#fafafa',
            defaultColor: '#6b6b80',
            borderRadiusSM: 6,
          },
          Statistic: {
            titleFontSize: 12,
            contentFontSize: 28,
          },
          Alert: {
            borderRadiusLG: 8,
          },
          Pagination: {
            itemSize: 32,
            borderRadius: 6,
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
            horizontalItemPadding: '10px 16px',
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
            trackBg: '#fafafa',
            trackPadding: 3,
          },
        },
      }}
    >
      <App />
    </ConfigProvider>
  </React.StrictMode>,
)
