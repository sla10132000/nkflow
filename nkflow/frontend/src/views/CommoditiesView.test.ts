import { flushPromises, mount } from "@vue/test-utils";
import { createPinia } from "pinia";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { createMockApi } from "../test/mocks/useApi";

const mockApi = createMockApi();
vi.mock("../composables/useApi", () => ({ useApi: () => mockApi }));

// Stub chart / shared components
vi.mock("../components/charts/PriceChart.vue", () => ({
	default: { template: "<div data-testid='price-chart-stub' />" },
}));
vi.mock("../components/charts/SupercyclePhaseChart.vue", () => ({
	default: { template: "<div data-testid='supercycle-phase-chart-stub' />" },
}));
vi.mock("../components/charts/SupercycleSectorDetail.vue", () => ({
	default: { template: "<div data-testid='supercycle-sector-detail-stub' />" },
}));

const { default: CommoditiesView } = await import("./CommoditiesView.vue");

const mockSummary = [
	{
		symbol: "GC=F",
		name: "Gold Futures",
		label: "金",
		date: "2026-03-07",
		close: 2890.5,
		change_pct: 0.35,
	},
	{
		symbol: "CL=F",
		name: "WTI Crude Oil",
		label: "原油 (WTI)",
		date: "2026-03-07",
		close: 71.2,
		change_pct: -1.1,
	},
	{
		symbol: "SI=F",
		name: "Silver Futures",
		label: "銀",
		date: "2026-03-07",
		close: 32.5,
		change_pct: 0.8,
	},
	{
		symbol: "HG=F",
		name: "Copper Futures",
		label: "銅",
		date: "2026-03-07",
		close: 4.35,
		change_pct: -0.2,
	},
];

const mockChartData = [
	{
		date: "2026-03-06",
		symbol: "GC=F",
		name: "Gold Futures",
		open: 2880.0,
		high: 2895.0,
		low: 2875.0,
		close: 2890.5,
		volume: 150000,
		change_pct: 0.35,
	},
];

function mountView() {
	return mount(CommoditiesView, {
		global: { plugins: [createPinia()] },
	});
}

describe("CommoditiesView", () => {
	beforeEach(() => {
		vi.clearAllMocks();
		mockApi.getCommoditiesSummary.mockResolvedValue(mockSummary);
		mockApi.getCommodities.mockResolvedValue(mockChartData);
	});

	it("タイトルが表示される", async () => {
		const wrapper = mountView();
		await flushPromises();
		expect(wrapper.text()).toContain("コモディティ");
	});

	it("マウント時に API を呼び出す", async () => {
		mountView();
		await flushPromises();
		expect(mockApi.getCommoditiesSummary).toHaveBeenCalled();
		expect(mockApi.getCommodities).toHaveBeenCalled();
	});

	it("サマリカードが表示される", async () => {
		const wrapper = mountView();
		await flushPromises();
		expect(wrapper.text()).toContain("金");
		expect(wrapper.text()).toContain("原油");
		expect(wrapper.text()).toContain("銀");
		expect(wrapper.text()).toContain("銅");
	});

	it("コモディティ選択ボタンが表示される", async () => {
		const wrapper = mountView();
		await flushPromises();
		expect(wrapper.text()).toContain("金");
		expect(wrapper.text()).toContain("WTI");
	});

	it("期間ボタンが表示される", async () => {
		const wrapper = mountView();
		await flushPromises();
		expect(wrapper.text()).toContain("1W");
		expect(wrapper.text()).toContain("1M");
		expect(wrapper.text()).toContain("3M");
		expect(wrapper.text()).toContain("1Y");
	});

	it("エラー時にエラーメッセージが表示される", async () => {
		mockApi.getCommoditiesSummary.mockRejectedValue(new Error("Network Error"));
		const wrapper = mountView();
		await flushPromises();
		expect(wrapper.text()).toContain("失敗");
	});

	it("タブボタン [価格] [サイクル分析] が表示される", async () => {
		const wrapper = mountView();
		await flushPromises();
		expect(wrapper.text()).toContain("価格");
		expect(wrapper.text()).toContain("サイクル分析");
	});

	it("デフォルトは価格タブ — サマリカードが表示される", async () => {
		const wrapper = mountView();
		await flushPromises();
		// 価格タブがアクティブなのでサマリが表示される
		expect(wrapper.text()).toContain("金");
	});
});
