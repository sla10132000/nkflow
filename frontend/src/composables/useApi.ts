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

  getNetwork: (type: string, period?: string, threshold?: string, dateFrom?: string, dateTo?: string) =>
    api.get(`/api/network/${type}`, { params: { period, threshold, date_from: dateFrom, date_to: dateTo } }).then(r => r.data),

  getStock: (code: string) =>
    api.get(`/api/stock/${code}`).then(r => r.data),

  getStocks: () =>
    api.get('/api/stocks').then(r => r.data),

  getFundFlowTimeseries: (granularity: 'week' | 'month' = 'week', limit = 12) =>
    api.get('/api/fund-flow/timeseries', { params: { granularity, limit } }).then(r => r.data),

  getFundFlowCumulative: (baseDate: string, granularity: 'week' | 'month' = 'week') =>
    api.get('/api/fund-flow/cumulative', { params: { base_date: baseDate, granularity } }).then(r => r.data),

  getMarketPressureTimeseries: (days = 90) =>
    api.get('/api/market-pressure/timeseries', { params: { days } }).then(r => r.data),

  // Phase 17: セクターローテーション
  getSectorRotationHeatmap: (periods = 12, periodType: 'weekly' | 'monthly' = 'weekly') =>
    api.get('/api/sector-rotation/heatmap', { params: { periods, period_type: periodType } }).then(r => r.data),

  getSectorRotationStates: (clusterMethod = 'kmeans', limit = 52) =>
    api.get('/api/sector-rotation/states', { params: { cluster_method: clusterMethod, limit } }).then(r => r.data),

  getSectorRotationTransitions: (clusterMethod = 'kmeans') =>
    api.get('/api/sector-rotation/transitions', { params: { cluster_method: clusterMethod } }).then(r => r.data),

  getSectorRotationPrediction: () =>
    api.get('/api/sector-rotation/prediction').then(r => r.data),

  // Phase 18: ニュース
  getNews: (params?: { date?: string; ticker?: string; limit?: number }) =>
    api.get('/api/news', { params }).then(r => r.data),

  getNewsSummary: (date?: string) =>
    api.get('/api/news/summary', { params: date ? { date } : undefined }).then(r => r.data),
})
