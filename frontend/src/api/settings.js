import api from './client'

export const settingsApi = {
  get: () => api.get('/settings'),
  update: (data) => api.put('/settings', data),
  check: () => api.get('/settings/check'),
  modules: () => api.get('/settings/modules'),
  category: (cat) => api.get(`/settings/${cat}`),
}
