import api from './client'
import { API_LONG_TIMEOUT } from '../config'

export const agentsApi = {
  list: () => api.get('/agents'),
  types: () => api.get('/agents/types'),
  create: (data) => api.post('/agents', data),
  update: (id, data) => api.put(`/agents/${id}`, data),
  delete: (id) => api.delete(`/agents/${id}`),
  run: (id) => api.post(`/agents/${id}/run`, {}, { timeout: API_LONG_TIMEOUT }),
}

export const workflowsApi = {
  list: () => api.get('/workflows'),
  templates: () => api.get('/workflows/templates'),
  get: (id) => api.get(`/workflows/${id}`),
  create: (data) => api.post('/workflows', data),
  update: (id, data) => api.put(`/workflows/${id}`, data),
  delete: (id) => api.delete(`/workflows/${id}`),
  advance: (id) => api.post(`/workflows/${id}/advance`),
}
