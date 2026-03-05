import { vi } from "vitest";

/**
 * useApi のモックファクトリ。
 * 各テストで `vi.mock("../../composables/useApi", () => createMockUseApi())` として使用。
 * 個別のメソッドは `mockResolvedValue` でテストごとにカスタマイズ可能。
 */
export function createMockApi() {
	return {
		getSummary: vi.fn().mockResolvedValue({}),
		getPrices: vi.fn().mockResolvedValue([]),
		getNetwork: vi.fn().mockResolvedValue({ nodes: [], edges: [] }),
		getStock: vi.fn().mockResolvedValue(null),
		getStocks: vi.fn().mockResolvedValue([]),
		getFundFlowTimeseries: vi
			.fn()
			.mockResolvedValue({ periods: [], series: [] }),
		getFundFlowCumulative: vi
			.fn()
			.mockResolvedValue({ base_date: "", series: [] }),
		getMarketPressureTimeseries: vi.fn().mockResolvedValue({
			dates: [],
			pl_ratio: [],
			pl_zone: [],
			margin_ratio: [],
			margin_ratio_trend: [],
			buy_growth_4w: [],
			signal_flags: [],
		}),
		getSectorRotationHeatmap: vi
			.fn()
			.mockResolvedValue({ periods: [], sectors: [] }),
		getSectorRotationStates: vi.fn().mockResolvedValue([]),
		getSectorRotationTransitions: vi.fn().mockResolvedValue({
			state_names: {},
			transitions: [],
			avg_durations: {},
		}),
		getSectorRotationPrediction: vi
			.fn()
			.mockResolvedValue({ available: false }),
		getNews: vi.fn().mockResolvedValue([]),
		getNewsSummary: vi.fn().mockResolvedValue(null),
		getFearIndices: vi.fn().mockResolvedValue(null), // Phase 21
		getTdSequential: vi.fn().mockResolvedValue([]), // Phase 22
		getTdSequentialLatest: vi.fn().mockResolvedValue(null), // Phase 22
		getYtdHighs: vi.fn().mockResolvedValue([]),
		// Phase 20: 米国株価指数・為替
		getUsIndices: vi.fn().mockResolvedValue([]),
		getUsIndicesSummary: vi.fn().mockResolvedValue([]),
		getForex: vi.fn().mockResolvedValue([]),
		getForexLatest: vi.fn().mockResolvedValue([]),
		getJpSectorPerformance: vi.fn().mockResolvedValue([]), // Phase 17 (共通期間セレクタ)
		getUsSectorPerformance: vi.fn().mockResolvedValue({ // Phase 23b
			date: null,
			period: "1d",
			sectors: [],
		}),
		getUsSectorHeatmap: vi.fn().mockResolvedValue({ // Phase 23b
			periods: [],
			sectors: [],
		}),
	};
}

export function createMockUseApi() {
	const mockApi = createMockApi();
	return {
		useApi: () => mockApi,
		__mockApi: mockApi,
	};
}
