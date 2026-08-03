import api from './client'
import { API_LONG_TIMEOUT } from '../config'

export const stocksApi = {
  watchlist: () => api.get('/stocks/watchlist'),
  addStock: (data) => api.post('/stocks/watchlist', data),
  updateStock: (id, data) => api.put(`/stocks/watchlist/${id}`, data),
  deleteStock: (id) => api.delete(`/stocks/watchlist/${id}`),
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
}
