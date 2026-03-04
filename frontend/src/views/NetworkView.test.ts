import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { createMockApi } from "../test/mocks/useApi";

const mockApi = createMockApi();
vi.mock("../composables/useApi", () => ({ useApi: () => mockApi }));

// Stub child components
vi.mock("../components/charts/FundFlowSankey.vue", () => ({
	default: { template: "<div data-testid='sankey-stub' />" },
}));
vi.mock("../components/charts/FundFlowTimeline.vue", () => ({
	default: {
		template: "<div data-testid='timeline-stub' />",
		emits: ["anchor-changed"],
	},
}));
vi.mock("../components/charts/MarketPressureGauge.vue", () => ({
	default: { template: "<div data-testid='gauge-stub' />" },
}));
vi.mock("../components/charts/MarketPressureTimeline.vue", () => ({
	default: { template: "<div data-testid='pressure-timeline-stub' />" },
}));
vi.mock("../components/network/GraphView.vue", () => ({
	default: { template: "<div data-testid='graph-stub' />" },
}));

const { default: NetworkView } = await import("./NetworkView.vue");

function mountView() {
	return mount(NetworkView);
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

	it("サンキー図セクションが表示される", async () => {
		const wrapper = mountView();
		await flushPromises();

		expect(wrapper.text()).toContain("資金の合流 — サンキー図");
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
		expect(mockApi.getSummary).toHaveBeenCalledWith(1);
		expect(mockApi.getMarketPressureTimeseries).toHaveBeenCalled();
	});
});
