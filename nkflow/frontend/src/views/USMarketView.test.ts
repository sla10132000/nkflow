import { flushPromises, mount } from "@vue/test-utils";
import { createPinia } from "pinia";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { createMockApi } from "../test/mocks/useApi";

const mockApi = createMockApi();
vi.mock("../composables/useApi", () => ({ useApi: () => mockApi }));

const { default: USMarketView } = await import("./USMarketView.vue");

const mockSummary = [
	{
		ticker: "^GSPC",
		name: "S&P 500",
		date: "2026-03-04",
		close: 5700.0,
		change_pct: 1.2,
		ytd_return_pct: 3.5,
	},
	{
		ticker: "^IXIC",
		name: "NASDAQ Composite",
		date: "2026-03-04",
		close: 18000.0,
		change_pct: -0.5,
		ytd_return_pct: 2.1,
	},
];

const mockFearIndices = {
	vix: { value: 18.5, change_pct: -2.0, date: "2026-03-04" },
	btc_fear_greed: { value: 45, classification: "Fear", date: "2026-03-04" },
};

const mockForexLatest = [
	{
		date: "2026-03-04",
		pair: "USDJPY",
		open: 150.0,
		high: 150.5,
		low: 149.5,
		close: 150.2,
		change_rate: 0.002,
		ma20: 149.8,
	},
	{
		date: "2026-03-04",
		pair: "EURUSD",
		open: 1.08,
		high: 1.085,
		low: 1.078,
		close: 1.082,
		change_rate: -0.001,
		ma20: 1.079,
	},
];

function mountView() {
	return mount(USMarketView, {
		global: { plugins: [createPinia()] },
	});
}

describe("USMarketView", () => {
	beforeEach(() => {
		vi.clearAllMocks();
		mockApi.getUsIndicesSummary.mockResolvedValue(mockSummary);
		mockApi.getFearIndices.mockResolvedValue(mockFearIndices);
		mockApi.getForexLatest.mockResolvedValue(mockForexLatest);
		mockApi.getUsIndices.mockResolvedValue([]);
		mockApi.getForex.mockResolvedValue([]);
	});

	it("タイトルが表示される", async () => {
		const wrapper = mountView();
		await flushPromises();
		expect(wrapper.text()).toContain("米国市場");
	});

	it("マウント時に必要な API を呼び出す", async () => {
		mountView();
		await flushPromises();
		expect(mockApi.getUsIndicesSummary).toHaveBeenCalled();
		expect(mockApi.getFearIndices).toHaveBeenCalled();
		expect(mockApi.getForexLatest).toHaveBeenCalled();
		expect(mockApi.getUsIndices).toHaveBeenCalled();
		expect(mockApi.getForex).toHaveBeenCalled();
	});

	it("主要指数カードが表示される", async () => {
		const wrapper = mountView();
		await flushPromises();
		expect(wrapper.text()).toContain("S&P 500");
		expect(wrapper.text()).toContain("NASDAQ");
	});

	it("VIX が表示される", async () => {
		const wrapper = mountView();
		await flushPromises();
		expect(wrapper.text()).toContain("VIX 恐怖指数");
		expect(wrapper.text()).toContain("18.50");
	});

	it("BTC Fear & Greed が表示される", async () => {
		const wrapper = mountView();
		await flushPromises();
		expect(wrapper.text()).toContain("Fear&Greed");
		expect(wrapper.text()).toContain("45");
		expect(wrapper.text()).toContain("Fear");
	});

	it("USD/JPY が表示される", async () => {
		const wrapper = mountView();
		await flushPromises();
		expect(wrapper.text()).toContain("USD/JPY");
		expect(wrapper.text()).toContain("150.20");
	});

	it("期間ボタンが表示される", async () => {
		const wrapper = mountView();
		await flushPromises();
		expect(wrapper.text()).toContain("日足");
		expect(wrapper.text()).toContain("週足");
		expect(wrapper.text()).toContain("月足");
	});

	it("指数テーブルが表示される", async () => {
		const wrapper = mountView();
		await flushPromises();
		expect(wrapper.text()).toContain("指数一覧");
	});
});
