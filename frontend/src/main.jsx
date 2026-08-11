import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import ThemeProvider from './theme/ThemeProvider'
import './styles/global.css'
import './styles/theme.css'
import 'dayjs/locale/zh-cn'

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <ThemeProvider>
      <App />
    </ThemeProvider>
  </React.StrictMode>,
)
