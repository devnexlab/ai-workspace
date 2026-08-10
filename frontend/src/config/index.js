/**
 * 前端统一配置。
 * 可通过 Vite 环境变量 (.env) 覆盖，前缀均为 VITE_。
 */

const env = import.meta.env

export const APP_NAME = env.VITE_APP_NAME || 'AI 智能运营'

/** axios / fetch 的 API 前缀；开发态走 Vite 代理 */
export const API_BASE_URL = env.VITE_API_BASE_URL || '/api'

/** 默认请求超时（毫秒） */
export const API_TIMEOUT = Number(env.VITE_API_TIMEOUT || 60000)

/** 长请求超时（采集 / AI 生成等） */
export const API_LONG_TIMEOUT = Number(env.VITE_API_LONG_TIMEOUT || 120000)

/**
 * Ant Design 主题 — Linear-inspired Modern SaaS
 * 对齐 WorkBuddy full-prototype 设计令牌
 */
export const THEME = {
  colorPrimary: env.VITE_COLOR_PRIMARY || '#5b5bd6',
  colorPrimaryLight: '#7d7dff',
  colorPrimaryDark: '#4a4ab8',
  borderRadius: 8,
  borderRadiusLG: 12,
  borderRadiusXL: 16,
  fontSize: 14,
  controlHeight: 34,
  colorText: '#1e1e2e',
  colorTextSecondary: '#6b6b80',
  colorTextTertiary: '#9b9bb0',
  colorBorder: '#ededf0',
  colorBorderSecondary: '#f3f3f6',
  colorBgLayout: '#fafafa',
  colorBgContainer: '#ffffff',
  colorBgSidebar: '#1a1a2e',
  colorSuccess: '#00b884',
  colorWarning: '#ff9500',
  colorError: '#ff3b5c',
  colorInfo: '#3b82f6',
  chart: ['#5b5bd6', '#00b884', '#ff9500', '#ff3b5c', '#3b82f6', '#9b5de5', '#00bbf9', '#f15bb5'],
}

export default {
  APP_NAME,
  API_BASE_URL,
  API_TIMEOUT,
  API_LONG_TIMEOUT,
  THEME,
}
