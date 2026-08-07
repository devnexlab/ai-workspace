import api from './client'
import { API_LONG_TIMEOUT } from '../config'

export const customersApi = {
  list: (params) => api.get('/customers', { params }),
  get: (id) => api.get(`/customers/${id}`),
  create: (data) => api.post('/customers', data, { timeout: API_LONG_TIMEOUT }),
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
  assistantBoard: (params) => api.get('/crm/assistant/board', { params }),
  runAssistant: (id) => api.post(`/customers/${id}/assistant`, {}, { timeout: API_LONG_TIMEOUT }),
}

export const followsApi = {
  list: (params) => api.get('/follows', { params }),
  create: (data) => api.post('/follows', data, { timeout: API_LONG_TIMEOUT }),
  delete: (id) => api.delete(`/follows/${id}`),
  quickTemplates: () => api.get('/follows/quick-templates'),
  quick: (data) => api.post('/follows/quick', data, { timeout: API_LONG_TIMEOUT }),
  smartParse: (data) => api.post('/follows/smart-parse', data, { timeout: API_LONG_TIMEOUT }),
  smart: (data) => api.post('/follows/smart', data, { timeout: API_LONG_TIMEOUT }),
}

export const remindersApi = {
  list: (params) => api.get('/reminders', { params }),
  update: (id, data) => api.put(`/reminders/${id}`, data),
  scan: () => api.post('/reminders/scan'),
}

export const leadsApi = {
  meta: () => api.get('/leads/meta'),
  list: (params) => api.get('/leads', { params }),
  get: (id) => api.get(`/leads/${id}`),
  create: (data) => api.post('/leads', data),
  update: (id, data) => api.put(`/leads/${id}`, data),
  convert: (id) => api.post(`/leads/${id}/convert`),
  batchConvert: (ids) => api.post('/leads/batch-convert', { ids }),
  delete: (id) => api.delete(`/leads/${id}`),
}
