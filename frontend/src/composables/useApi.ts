import axios from 'axios'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE || '',
  timeout: 15000,
})

export const useApi = () => ({
  getSummary: (days?: number) =>
    api.get('/api/summary', { params: days ? { days } : undefined }).then(r => r.data),

  getPrices: (code: string, from?: string, to?: string) =>
    api.get(`/api/prices/${code}`, { params: { from, to } }).then(r => r.data),

  getSignals: (params?: Record<string, string>) =>
    api.get('/api/signals', { params }).then(r => r.data),

  getNetwork: (type: string, period?: string, threshold?: string) =>
    api.get(`/api/network/${type}`, { params: { period, threshold } }).then(r => r.data),

  getStock: (code: string) =>
    api.get(`/api/stock/${code}`).then(r => r.data),

  getStocks: () =>
    api.get('/api/stocks').then(r => r.data),
})
