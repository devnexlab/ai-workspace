import axios from 'axios'
import { API_BASE_URL, API_TIMEOUT } from '../config'

const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: API_TIMEOUT,
  headers: { 'Content-Type': 'application/json' },
})

api.interceptors.response.use(
  (res) => res.data,
  (err) => {
    console.error('API Error:', err?.response?.data || err.message)
    return Promise.reject(err?.response?.data || err)
  }
)

export default api
