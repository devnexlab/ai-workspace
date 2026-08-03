import api from './client'
import { API_LONG_TIMEOUT } from '../config'

export const agentsApi = {
  list: () => api.get('/agents'),
  types: () => api.get('/agents/types'),
  create: (data) => api.post('/agents', data),
  update: (id, data) => api.put(`/agents/${id}`, data),
  delete: (id) => api.delete(`/agents/${id}`),
  run: (id, data) => api.post(`/agents/${id}/run`, data || {}, { timeout: API_LONG_TIMEOUT }),
  assistants: () => api.get('/assistants'),
  runAssistant: (key, data) => api.post(`/assistants/${key}/run`, data || {}, { timeout: API_LONG_TIMEOUT }),
  assistantBoard: (key, params) => api.get(`/assistants/${key}/board`, { params }),
  assistantTasks: (key, params) => api.get(`/assistants/${key}/tasks`, { params }),
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
