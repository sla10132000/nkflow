import axios from "axios";

const api = axios.create({
	baseURL: import.meta.env.VITE_API_BASE || "",
	timeout: 15000,
});

export const useApi = () => ({
	getSummary: (days?: number) =>
		api
			.get("/api/summary", { params: days ? { days } : undefined })
			.then((r) => r.data),

	getPrices: (code: string, from?: string, to?: string) =>
		api
			.get(`/api/prices/${code}`, { params: { from, to } })
			.then((r) => r.data),

	getNetwork: (
		type: string,
		period?: string,
		threshold?: string,
		dateFrom?: string,
		dateTo?: string,
	) =>
		api
			.get(`/api/network/${type}`, {
				params: { period, threshold, date_from: dateFrom, date_to: dateTo },
			})
			.then((r) => r.data),

	getStock: (code: string) => api.get(`/api/stock/${code}`).then((r) => r.data),

	getStocks: () => api.get("/api/stocks").then((r) => r.data),

	getFundFlowTimeseries: (granularity: "week" | "month" = "week", limit = 12) =>
		api
			.get("/api/fund-flow/timeseries", { params: { granularity, limit } })
			.then((r) => r.data),

	getFundFlowCumulative: (
		baseDate: string,
		granularity: "week" | "month" = "week",
	) =>
		api
			.get("/api/fund-flow/cumulative", {
				params: { base_date: baseDate, granularity },
			})
			.then((r) => r.data),

	getMarketPressureTimeseries: (days = 90) =>
		api
			.get("/api/market-pressure/timeseries", { params: { days } })
			.then((r) => r.data),

	// Phase 17: セクターローテーション
	getSectorRotationHeatmap: (
		periods = 12,
		periodType: "weekly" | "monthly" = "weekly",
	) =>
		api
			.get("/api/sector-rotation/heatmap", {
				params: { periods, period_type: periodType },
			})
			.then((r) => r.data),

	getSectorRotationStates: (clusterMethod = "kmeans", limit = 52) =>
		api
			.get("/api/sector-rotation/states", {
				params: { cluster_method: clusterMethod, limit },
			})
			.then((r) => r.data),

	getSectorRotationTransitions: (clusterMethod = "kmeans") =>
		api
			.get("/api/sector-rotation/transitions", {
				params: { cluster_method: clusterMethod },
			})
			.then((r) => r.data),

	getSectorRotationPrediction: () =>
		api.get("/api/sector-rotation/prediction").then((r) => r.data),

	// Phase 18: ニュース
	getNews: (params?: { date?: string; ticker?: string; limit?: number }) =>
		api.get("/api/news", { params }).then((r) => r.data),

	getNewsSummary: (date?: string) =>
		api
			.get("/api/news/summary", { params: date ? { date } : undefined })
			.then((r) => r.data),

	// Phase 21: 恐怖指数
	getFearIndices: () => api.get("/api/fear-indices/latest").then((r) => r.data),

	// Phase 22: TD Sequential
	getTdSequential: (code: string, days = 120) =>
		api
			.get(`/api/td-sequential/${code}`, { params: { days } })
			.then((r) => r.data),

	getTdSequentialLatest: (code: string) =>
		api.get(`/api/td-sequential/${code}/latest`).then((r) => r.data),

	getYtdHighs: (limit = 10, thresholdPct = 5.0) =>
		api
			.get("/api/ytd-highs", { params: { limit, threshold_pct: thresholdPct } })
			.then((r) => r.data),

	// Phase 20: 米国株価指数
	getUsIndices: (ticker?: string, days = 90) =>
		api
			.get("/api/us-indices", { params: ticker ? { ticker, days } : { days } })
			.then((r) => r.data),

	getUsIndicesSummary: () =>
		api.get("/api/us-indices/summary").then((r) => r.data),

	// 為替
	getForex: (pair = "USDJPY", days = 60) =>
		api.get("/api/forex", { params: { pair, days } }).then((r) => r.data),

	getForexLatest: () => api.get("/api/forex/latest").then((r) => r.data),

	// Phase 23b: 米国セクター ETF
	getUsSectorPerformance: (period: "1d" | "1w" | "1m" | "3m" = "1d") =>
		api
			.get("/api/us-sectors/performance", { params: { period } })
			.then((r) => r.data),

	getUsSectorHeatmap: (
		periods = 12,
		periodType: "weekly" | "monthly" = "weekly",
	) =>
		api
			.get("/api/us-sectors/heatmap", {
				params: { periods, period_type: periodType },
			})
			.then((r) => r.data),
});
