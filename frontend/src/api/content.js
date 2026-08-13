import api from './client'
import { API_LONG_TIMEOUT } from '../config'

/** 内容情报 / 爆款&口播采集 */
export const hotTopicsApi = {
  list: (params) => api.get('/hot-topics', { params }),
  get: (id) => api.get(`/hot-topics/${id}`),
  create: (data) => api.post('/hot-topics', data),
  update: (id, data) => api.put(`/hot-topics/${id}`, data),
  delete: (id) => api.delete(`/hot-topics/${id}`),
  collect: (data) => api.post('/hot-topics/collect', data, { timeout: API_LONG_TIMEOUT }),
  refresh: (data) => api.post('/content-ops/refresh', data || {}, { timeout: API_LONG_TIMEOUT * 3 }),
  meta: () => api.get('/content-ops/meta'),
  generateScript: (id, data) => api.post(`/hot-topics/${id}/generate-script`, data, { timeout: API_LONG_TIMEOUT }),
  batchGenerate: (data) => api.post('/hot-topics/batch-generate', data, { timeout: API_LONG_TIMEOUT * 3 }),
}

/** 文案中心 */
export const scriptsApi = {
  list: (params) => api.get('/scripts', { params }),
  get: (id) => api.get(`/scripts/${id}`),
  create: (data) => api.post('/scripts', data),
  generate: (data) => api.post('/scripts/generate', data, { timeout: API_LONG_TIMEOUT }),
  dailyPlan: (data) => api.post('/scripts/daily-plan', data || {}, { timeout: API_LONG_TIMEOUT * 5 }),
  dailyRun: (data) => api.post('/scripts/daily-run', data || {}, { timeout: API_LONG_TIMEOUT * 8 }),
  dailyRunStatus: () => api.get('/scripts/daily-run/status'),
  update: (id, data) => api.put(`/scripts/${id}`, data),
  produce: (id, data) => api.post(`/scripts/${id}/produce`, data || {}),
  delete: (id) => api.delete(`/scripts/${id}`),
}

/** 视频生产 */
export const videosApi = {
  list: (params) => api.get('/videos', { params }),
  get: (id) => api.get(`/videos/${id}`),
  create: (data) => api.post('/videos', data),
  update: (id, data) => api.put(`/videos/${id}`, data),
  execute: (id, step) => api.post(`/videos/${id}/execute/${step}`, {}, { timeout: 30000 }),
  getStatus: (id) => api.get(`/videos/${id}/status`, { timeout: 10000 }),
  delete: (id) => api.delete(`/videos/${id}`),
  checkFfmpeg: () => api.get('/videos/check-ffmpeg'),
  voiceOptions: () => api.get('/videos/voice-options'),
  lastPrefs: () => api.get('/videos/last-prefs'),
  generateScenes: (id, data) => api.post(`/videos/${id}/generate-scenes`, data, { timeout: API_LONG_TIMEOUT }),
  getScenes: (id) => api.get(`/videos/${id}/scenes`),
  updateScenes: (id, scenes) => api.put(`/videos/${id}/scenes`, { scenes }),
}

/** 素材库 */
export const materialsApi = {
  list: (params) => api.get('/materials', { params }),
  upload: (formData, onProgress) => api.post('/materials', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: API_LONG_TIMEOUT,
    onUploadProgress: onProgress,
  }),
  delete: (id) => api.delete(`/materials/${id}`),
  styles: () => api.get('/materials/styles'),
}

/** 发布中心 */
export const publishApi = {
  list: (params) => api.get('/publish', { params }),
  create: (data) => api.post('/publish', data),
  update: (id, data) => api.put(`/publish/${id}`, data),
  publish: (id, data) => api.post(`/publish/${id}/publish`, data || {}, { timeout: API_LONG_TIMEOUT * 3 }),
  prepare: (id) => api.post(`/publish/${id}/prepare`, {}),
  confirm: (id, data) => api.post(`/publish/${id}/confirm`, data || {}),
  sync: (id) => api.post(`/publish/${id}/sync`, {}, { timeout: API_LONG_TIMEOUT * 3 }),
  delete: (id) => api.delete(`/publish/${id}`),
  status: () => api.get('/publish/status'),
  analytics: (params) => api.get('/publish/analytics', { params }),
  sessions: () => api.get('/publish/sessions'),
  closeSession: (sid) => api.post(`/publish/sessions/${sid}/close`),
  workbench: (params) => api.get('/publish/workbench', { params }),
  workbenchSync: (data) => api.post('/publish/workbench/sync', data || {}, { timeout: API_LONG_TIMEOUT * 5 }),
  workbenchLogin: (data) => api.post('/publish/workbench/login', data || {}, { timeout: API_LONG_TIMEOUT * 2 }),
}
