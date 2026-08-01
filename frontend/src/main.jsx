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
        },
      }}
    >
      <App />
    </ConfigProvider>
  </React.StrictMode>,
)
