import api from './client'

export const settingsApi = {
  get: () => api.get('/settings'),
  update: (data) => api.put('/settings', data),
  check: () => api.get('/settings/check'),
  modules: () => api.get('/settings/modules'),
  category: (cat) => api.get(`/settings/${cat}`),
  testCommercial: (providerKey) => api.post(`/commercial-data/test/${providerKey}`, {}),
  testNotify: (data = {}) => api.post('/settings/notify/test', data),
}

export const platformsApi = {
  list: () => api.get('/platforms'),
  create: (data) => api.post('/platforms', data),
  update: (key, data) => api.put(`/platforms/${key}`, data),
  delete: (key) => api.delete(`/platforms/${key}`),
  get: (key) => api.get(`/platforms/${key}`),
}
