import api from './client'

export const settingsApi = {
  get: () => api.get('/settings'),
  update: (data) => api.put('/settings', data),
  check: () => api.get('/settings/check'),
  modules: () => api.get('/settings/modules'),
  category: (cat) => api.get(`/settings/${cat}`),
  testCommercial: (providerKey) => api.post(`/commercial-data/test/${providerKey}`, {}),
  testNotify: (data = {}) => api.post('/settings/notify/test', data),
  testAi: (data = {}) => api.post('/settings/ai/test', data),
  createAiProvider: (data) => api.post('/settings/ai/providers', data),
  deleteAiProvider: (key) => api.delete(`/settings/ai/providers/${key}`),
  wechatOaMenuLinks: () => api.get('/settings/wechat-oa/menu-links'),
}

export const platformsApi = {
  list: () => api.get('/platforms'),
  create: (data) => api.post('/platforms', data),
  update: (key, data) => api.put(`/platforms/${key}`, data),
  delete: (key) => api.delete(`/platforms/${key}`),
  get: (key) => api.get(`/platforms/${key}`),
}

export const wechatOaPublicApi = {
  profile: () => api.get('/public/wechat-oa/profile'),
  submitLead: (data) => api.post('/public/wechat-oa/leads', data),
}
