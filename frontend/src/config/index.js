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
 * 对齐 dashboard-prototype / full-prototype 设计令牌
 */
export const THEME = {
  colorPrimary: env.VITE_COLOR_PRIMARY || '#5b5bd6',
  borderRadius: 8,
  fontSize: 14,
  controlHeight: 34,
  colorText: '#1e1e2e',
  colorTextSecondary: '#6b6b80',
  colorBorder: '#ededf0',
  colorBgLayout: '#fafafa',
}

export default {
  APP_NAME,
  API_BASE_URL,
  API_TIMEOUT,
  API_LONG_TIMEOUT,
  THEME,
}
