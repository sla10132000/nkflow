import { flushPromises, mount } from "@vue/test-utils";
import { createPinia } from "pinia";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { createMockApi } from "../test/mocks/useApi";

const mockApi = createMockApi();
vi.mock("../composables/useApi", () => ({ useApi: () => mockApi }));

// Stub child components (パスはドメイン別フォルダに移動済み)
vi.mock("../components/fund-flow/FundFlowSankey.vue", () => ({
	default: { template: "<div data-testid='sankey-stub' />" },
}));
vi.mock("../components/fund-flow/FundFlowTimeline.vue", () => ({
	default: {
		template: "<div data-testid='timeline-stub' />",
		emits: ["anchor-changed"],
	},
}));
vi.mock("../components/market-pressure/MarketPressureGauge.vue", () => ({
	default: { template: "<div data-testid='gauge-stub' />" },
}));
vi.mock("../components/market-pressure/MarketPressureTimeline.vue", () => ({
	default: { template: "<div data-testid='pressure-timeline-stub' />" },
}));
vi.mock("../components/network/GraphView.vue", () => ({
	default: { template: "<div data-testid='graph-stub' />" },
}));
vi.mock("../components/charts/InvestorFlowChart.vue", () => ({
	default: { template: "<div data-testid='investor-flow-chart-stub' />" },
}));
vi.mock("../components/charts/DivergenceGauge.vue", () => ({
	default: { template: "<div data-testid='divergence-gauge-stub' />" },
}));

const { default: NetworkView } = await import("./NetworkView.vue");

function mountView() {
	return mount(NetworkView, {
		global: { plugins: [createPinia()] },
	});
}

describe("NetworkView", () => {
	beforeEach(() => {
		vi.clearAllMocks();
		mockApi.getSummary.mockResolvedValue({ regime: "risk_on" });
		mockApi.getNetwork.mockResolvedValue({ nodes: [], edges: [] });
		mockApi.getMarketPressureTimeseries.mockResolvedValue({
			dates: ["2026-03-04"],
			pl_ratio: [-0.05],
			pl_zone: ["neutral"],
			margin_ratio: [3.2],
			margin_ratio_trend: [0.01],
			buy_growth_4w: [0.02],
			signal_flags: [{ credit_overheating: false }],
		});
		mockApi.getInvestorFlowsLatest.mockResolvedValue(null);
		mockApi.getInvestorFlowsIndicators.mockResolvedValue([]);
	});

	it("日本語の見出しが表示される", async () => {
		const wrapper = mountView();
		await flushPromises();

		expect(wrapper.text()).toContain("資金フロー");
	});

	it("フィルタ UI の日本語ラベルが表示される", async () => {
		const wrapper = mountView();
		await flushPromises();

		expect(wrapper.text()).toContain("期間");
		expect(wrapper.text()).toContain("範囲");
		expect(wrapper.text()).toContain("日付");
	});

	it("市場圧力セクションが表示される", async () => {
		const wrapper = mountView();
		await flushPromises();

		expect(wrapper.text()).toContain("市場圧力 (信用評価損益)");
	});

	it("時系列フローセクションが表示される", async () => {
		const wrapper = mountView();
		await flushPromises();

		expect(wrapper.text()).toContain("時系列フロー");
	});

	it("サンキー図タブが表示される", async () => {
		const wrapper = mountView();
		await flushPromises();

		expect(wrapper.text()).toContain("サンキー図");
		expect(wrapper.text()).toContain("ネットワーク");
	});

	it("デフォルトでサンキー図タブがアクティブ", async () => {
		const wrapper = mountView();
		await flushPromises();

		const sankeyTab = wrapper
			.findAll("button")
			.find((b) => b.text() === "サンキー図");
		expect(sankeyTab?.classes()).toContain("text-blue-600");
	});

	it("ネットワークタブに切り替えるとグラフが表示される", async () => {
		mockApi.getNetwork.mockResolvedValue({
			nodes: [{ id: "7203", label: "7203", group: "輸送用機器" }],
			edges: [],
		});
		const wrapper = mountView();
		await flushPromises();

		const networkTab = wrapper
			.findAll("button")
			.find((b) => b.text() === "ネットワーク");
		await networkTab?.trigger("click");

		expect(wrapper.find("[data-testid='graph-stub']").exists()).toBe(true);
	});

	it("信用圧力タイムラインが表示される", async () => {
		const wrapper = mountView();
		await flushPromises();

		expect(wrapper.text()).toContain("信用圧力タイムライン");
	});

	it("範囲プリセットボタンが表示される", async () => {
		const wrapper = mountView();
		await flushPromises();

		expect(wrapper.text()).toContain("直近5営業日");
		expect(wrapper.text()).toContain("先月");
		expect(wrapper.text()).toContain("3ヶ月");
	});

	it("マウント時に API を呼び出す", async () => {
		mountView();
		await flushPromises();

		expect(mockApi.getNetwork).toHaveBeenCalled();
		expect(mockApi.getSummary).toHaveBeenCalled();
		expect(mockApi.getMarketPressureTimeseries).toHaveBeenCalled();
	});

	it("投資主体別フローセクションの見出しが表示される", async () => {
		const wrapper = mountView();
		await flushPromises();

		expect(wrapper.text()).toContain("投資主体別フロー");
	});

	it("マウント時に investor-flows API を呼び出す", async () => {
		mountView();
		await flushPromises();

		expect(mockApi.getInvestorFlowsLatest).toHaveBeenCalled();
		expect(mockApi.getInvestorFlowsIndicators).toHaveBeenCalled();
	});

	it("latestFlow があるとき 最新週ラベルが表示される", async () => {
		mockApi.getInvestorFlowsLatest.mockResolvedValue({
			week_end: "2026-03-01",
			flows: {
				foreigners: { sales: 1e12, purchases: 1.2e12, balance: 2e11 },
				individuals: { sales: 8e11, purchases: 7e11, balance: -1e11 },
			},
			indicators: {
				divergence_score: 0.45,
				flow_regime: "bullish",
				foreigners_4w_ma: 1.5e11,
				individuals_4w_ma: -8e10,
			},
			signal: null,
		});
		const wrapper = mountView();
		await flushPromises();

		expect(wrapper.text()).toContain("2026-03-01");
		expect(wrapper.text()).toContain("強気 (海外買い優勢)");
		expect(wrapper.text()).toContain("乖離スコア:");
	});
});
