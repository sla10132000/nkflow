import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { createMockApi } from "../test/mocks/useApi";

const mockApi = createMockApi();
vi.mock("../composables/useApi", () => ({ useApi: () => mockApi }));

// Stub chart component
vi.mock("../components/charts/PriceChart.vue", () => ({
	default: { template: "<div data-testid='price-chart-stub' />" },
}));

const { default: StockView } = await import("./StockView.vue");

function mountView(code = "7203") {
	return mount(StockView, {
		props: { code },
		global: {
			stubs: {
				RouterLink: { template: "<a><slot /></a>" },
			},
		},
	});
}

describe("StockView", () => {
	beforeEach(() => {
		vi.clearAllMocks();
	});

	it("銘柄コードを表示する", async () => {
		mockApi.getStock.mockResolvedValue({
			name: "トヨタ自動車",
			sector: "輸送用機器",
			latest: {
				close: 2800,
				return_rate: 0.015,
				price_range: 50,
				volume: 1000000,
			},
			causes: [],
			caused_by: [],
			correlated: [],
			community_members: [],
			signals: [],
		});
		mockApi.getPrices.mockResolvedValue([]);

		const wrapper = mountView("7203");
		await flushPromises();

		expect(wrapper.text()).toContain("7203");
		expect(wrapper.text()).toContain("トヨタ自動車");
		expect(wrapper.text()).toContain("輸送用機器");
	});

	it("日本語ラベルが表示される", async () => {
		mockApi.getStock.mockResolvedValue({
			name: "テスト銘柄",
			sector: "テスト",
			latest: {
				close: 1000,
				return_rate: 0.01,
				price_range: 20,
				volume: 500000,
			},
			causes: [],
			caused_by: [],
			correlated: [],
			community_members: [],
			signals: [],
		});
		mockApi.getPrices.mockResolvedValue([]);

		const wrapper = mountView();
		await flushPromises();

		expect(wrapper.text()).toContain("終値");
		expect(wrapper.text()).toContain("騰落率");
		expect(wrapper.text()).toContain("値幅");
		expect(wrapper.text()).toContain("出来高");
		expect(wrapper.text()).toContain("株価チャート");
		expect(wrapper.text()).toContain("この銘柄が因果する銘柄");
		expect(wrapper.text()).toContain("この銘柄を因果する銘柄");
		expect(wrapper.text()).toContain("高相関銘柄");
	});

	it("getStock を正しいコードで呼び出す", async () => {
		mockApi.getStock.mockResolvedValue({
			latest: null,
			causes: [],
			caused_by: [],
			correlated: [],
			community_members: [],
			signals: [],
		});
		mockApi.getPrices.mockResolvedValue([]);

		mountView("9984");
		await flushPromises();

		expect(mockApi.getStock).toHaveBeenCalledWith("9984");
	});

	it("戻るボタンが表示される", async () => {
		mockApi.getStock.mockResolvedValue({
			latest: null,
			causes: [],
			caused_by: [],
			correlated: [],
			community_members: [],
			signals: [],
		});
		mockApi.getPrices.mockResolvedValue([]);

		const wrapper = mountView();
		await flushPromises();

		expect(wrapper.text()).toContain("← 戻る");
	});

	it("期間ボタンが表示される", async () => {
		mockApi.getStock.mockResolvedValue({
			latest: {
				close: 1000,
				return_rate: 0.01,
				price_range: 20,
				volume: 500000,
			},
			causes: [],
			caused_by: [],
			correlated: [],
			community_members: [],
			signals: [],
		});
		mockApi.getPrices.mockResolvedValue([]);

		const wrapper = mountView();
		await flushPromises();

		expect(wrapper.text()).toContain("1M");
		expect(wrapper.text()).toContain("3M");
		expect(wrapper.text()).toContain("6M");
	});

	it("エラー時にメッセージを表示する", async () => {
		mockApi.getStock.mockRejectedValue(new Error("Not found"));
		const wrapper = mountView();
		await flushPromises();
		expect(wrapper.text()).toContain("Not found");
	});
});
