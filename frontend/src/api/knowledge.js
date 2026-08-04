import api from './client'
import { API_LONG_TIMEOUT } from '../config'

export const knowledgeApi = {
  list: (params) => api.get('/knowledge', { params }),
  get: (id) => api.get(`/knowledge/${id}`),
  create: (data) => api.post('/knowledge', data),
  update: (id, data) => api.put(`/knowledge/${id}`, data),
  delete: (id) => api.delete(`/knowledge/${id}`),
  aiProcess: (id) => api.post(`/knowledge/${id}/ai-process`, {}, { timeout: API_LONG_TIMEOUT }),
  compare: (data) => api.post('/knowledge/compare', data, { timeout: API_LONG_TIMEOUT }),
  categories: () => api.get('/knowledge/categories'),
  upload: (formData, onProgress) => api.post('/knowledge/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: API_LONG_TIMEOUT * 5,
    onUploadProgress: onProgress,
  }),
}
