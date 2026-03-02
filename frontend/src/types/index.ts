export interface Stock {
  code: string
  name: string
  sector: string
}

export interface DailyPrice {
  code: string
  date: string
  open: number
  high: number
  low: number
  close: number
  volume: number
  return_rate: number
  price_range: number
}

export interface Signal {
  id: number
  date: string
  signal_type: string
  code: string | null
  sector: string | null
  direction: 'bullish' | 'bearish'
  confidence: number
  reasoning: Record<string, unknown>
}

export interface NetworkData {
  nodes: { id: string; label: string; group: string; size: number }[]
  edges: { from: string; to: string; value: number; arrows?: string; edge_count?: number; coefficient?: number }[]
}

export interface DailySummary {
  date: string
  nikkei_close: number
  nikkei_return: number
  regime: string
  top_gainers: (Stock & { return_rate: number })[]
  top_losers: (Stock & { return_rate: number })[]
  active_signals: number
  sector_rotation: { sector: string; avg_return: number; total_volume: number }[]
}

export interface FundFlowTimeseriesValue {
  count: number
  avg_spread: number
}

export interface FundFlowTimeseriesSeries {
  label: string
  sector_from: string
  sector_to: string
  values: FundFlowTimeseriesValue[]
}

export interface FundFlowTimeseries {
  periods: string[]
  start_dates: string[]
  series: FundFlowTimeseriesSeries[]
}

export interface FundFlowCumulativePeriod {
  key: string
  start_date: string
  regime: 'risk_on' | 'risk_off' | 'neutral' | string
}

export interface FundFlowCumulativeSeries {
  label: string
  sector_from: string
  sector_to: string
  cumulative_spread: number[]
  sector_cumulative_return: number[]
}

export interface FundFlowCumulative {
  base_date: string
  periods: FundFlowCumulativePeriod[]
  series: FundFlowCumulativeSeries[]
}

export interface StockDetail {
  code: string
  name: string
  sector: string
  latest: DailyPrice | null
  causes: { code: string; name: string; lag_days: number; p_value: number }[]
  caused_by: { code: string; name: string; lag_days: number; p_value: number }[]
  correlated: { code: string; name: string; coefficient: number }[]
  community_members: { code: string; name: string }[]
  signals: Signal[]
}
