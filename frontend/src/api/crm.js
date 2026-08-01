import api from './client'
import { API_LONG_TIMEOUT } from '../config'

export const customersApi = {
  list: (params) => api.get('/customers', { params }),
  get: (id) => api.get(`/customers/${id}`),
  create: (data) => api.post('/customers', data),
  update: (id, data) => api.put(`/customers/${id}`, data),
  delete: (id) => api.delete(`/customers/${id}`),
  lifecycleStages: () => api.get('/customers/lifecycle-stages'),
  setLifecycle: (id, data) => api.post(`/customers/${id}/lifecycle`, data),
  analyze: (id) => api.post(`/customers/${id}/analyze`, {}, { timeout: API_LONG_TIMEOUT }),
  strategy: (id) => api.get(`/customers/${id}/strategy`),
  autoRemind: (id) => api.post(`/customers/${id}/auto-remind`),
  reminders: (id) => api.get(`/customers/${id}/reminders`),
  createReminder: (id, data) => api.post(`/customers/${id}/reminders`, data),
  owners: () => api.get('/customers/owners'),
}

export const followsApi = {
  list: (params) => api.get('/follows', { params }),
  create: (data) => api.post('/follows', data),
  delete: (id) => api.delete(`/follows/${id}`),
  quickTemplates: () => api.get('/follows/quick-templates'),
  quick: (data) => api.post('/follows/quick', data),
  smartParse: (data) => api.post('/follows/smart-parse', data, { timeout: API_LONG_TIMEOUT }),
  smart: (data) => api.post('/follows/smart', data, { timeout: API_LONG_TIMEOUT }),
}

export const remindersApi = {
  list: (params) => api.get('/reminders', { params }),
  update: (id, data) => api.put(`/reminders/${id}`, data),
  scan: () => api.post('/reminders/scan'),
}
