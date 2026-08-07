import api from './client'
import { API_LONG_TIMEOUT } from '../config'

export const stocksApi = {
  watchlist: () => api.get('/stocks/watchlist'),
  addStock: (data) => api.post('/stocks/watchlist', data),
  updateStock: (id, data) => api.put(`/stocks/watchlist/${id}`, data),
  deleteStock: (id) => api.delete(`/stocks/watchlist/${id}`),
  refreshPrices: () => api.post('/stocks/watchlist/refresh-prices', {}, { timeout: API_LONG_TIMEOUT }),
  universe: (params) => api.get('/stocks/universe', { params }),
  universeMeta: () => api.get('/stocks/universe/meta'),
  refreshUniverse: () => api.post('/stocks/universe/refresh', {}, { timeout: API_LONG_TIMEOUT * 3 }),
  indicators: (code) => api.get('/stocks/indicators', { params: { code } }),
  patternRules: () => api.get('/stocks/pattern-rules'),
  savePatternRules: (data) => api.put('/stocks/pattern-rules', data),
  screening: (data) => api.post('/stocks/screening', data, { timeout: API_LONG_TIMEOUT }),
  getScreening: (id) => api.get(`/stocks/screening/${id}`),
  cancelScreening: (id) => api.post(`/stocks/screening/${id}/cancel`),
  screeningHistory: () => api.get('/stocks/screening/history'),
  strategies: () => api.get('/stocks/strategies'),
  activeStrategies: () => api.get('/stocks/strategies', { params: { active: 1 } }),
  parseStrategy: (data) => api.post('/stocks/strategies/parse', data),
  createStrategy: (data) => api.post('/stocks/strategies', data),
  updateStrategy: (id, data) => api.put(`/stocks/strategies/${id}`, data),
  deleteStrategy: (id) => api.delete(`/stocks/strategies/${id}`),
  review: (data) => api.post('/stocks/review', data, { timeout: API_LONG_TIMEOUT }),
  note: (data) => api.post('/stocks/note', data),

  /** 内容情报 · 股票：新闻 → 股市简报 → AI 分析（分开） */
  stockNews: (params) => api.get('/stock-news', { params }),
  refreshStockNews: (data) => api.post('/stock-news/refresh', data || {}, { timeout: API_LONG_TIMEOUT * 5 }),
  stockBriefingToday: () => api.get('/stock-briefing/today'),
  buildStockBriefing: (data) => api.post('/stock-briefing/build', data || {}, { timeout: API_LONG_TIMEOUT * 3 }),
  analyzeStockBriefing: (data) => api.post('/stock-briefing/analyze', data || {}, { timeout: API_LONG_TIMEOUT * 3 }),
}
