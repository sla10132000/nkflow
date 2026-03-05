import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { createMockApi } from "../test/mocks/useApi";

const mockApi = createMockApi();
vi.mock("../composables/useApi", () => ({ useApi: () => mockApi }));

// Stub chart component
vi.mock("../components/charts/PriceChart.vue", () => ({
	default: { template: "<div data-testid='price-chart-stub' />" },
}));

const { default: TimeseriesView } = await import("./TimeseriesView.vue");

function mountView() {
	return mount(TimeseriesView);
}

describe("TimeseriesView", () => {
	beforeEach(() => {
		vi.clearAllMocks();
		mockApi.getStocks.mockResolvedValue([
			{ code: "7203", name: "トヨタ自動車", sector: "輸送用機器" },
			{ code: "6758", name: "ソニーグループ", sector: "電気機器" },
		]);
	});

	it("日本語の見出しが表示される", () => {
		const wrapper = mountView();
		expect(wrapper.text()).toContain("銘柄チャート");
	});

	it("銘柄コード入力フィールドが存在する", () => {
		const wrapper = mountView();
		const input = wrapper.find("input");
		expect(input.exists()).toBe(true);
		expect(input.attributes("placeholder")).toContain("銘柄コード");
	});

	it("表示ボタンが存在する", () => {
		const wrapper = mountView();
		expect(wrapper.text()).toContain("表示");
	});

	it("期間選択ボタンが表示される", () => {
		const wrapper = mountView();
		expect(wrapper.text()).toContain("1M");
		expect(wrapper.text()).toContain("3M");
		expect(wrapper.text()).toContain("6M");
		expect(wrapper.text()).toContain("1Y");
	});

	it("初期状態で案内メッセージが表示される", () => {
		const wrapper = mountView();
		expect(wrapper.text()).toContain(
			"銘柄コードを入力して「表示」を押してください",
		);
	});

	it("マウント時に getStocks を呼び出す", async () => {
		mountView();
		await flushPromises();
		expect(mockApi.getStocks).toHaveBeenCalled();
	});

	it("銘柄コード入力後に API を呼び出す", async () => {
		mockApi.getPrices.mockResolvedValue([
			{
				date: "2026-03-04",
				open: 1000,
				high: 1050,
				low: 980,
				close: 1020,
				return_rate: 0.02,
				volume: 100000,
			},
		]);

		const wrapper = mountView();
		await flushPromises();
		const input = wrapper.find("input");
		await input.setValue("7203");
		await wrapper.find("button.btn-primary").trigger("click");
		await flushPromises();

		expect(mockApi.getPrices).toHaveBeenCalledWith("7203", expect.any(String));
	});

	it("銘柄名入力でサジェストドロップダウンが表示される", async () => {
		const wrapper = mountView();
		await flushPromises();
		const input = wrapper.find("input");
		await input.setValue("トヨタ");
		await input.trigger("focus");
		await input.trigger("input");

		expect(wrapper.text()).toContain("7203");
		expect(wrapper.text()).toContain("トヨタ自動車");
	});

	it("データテーブルの日本語ヘッダーが表示される", async () => {
		mockApi.getPrices.mockResolvedValue([
			{
				date: "2026-03-04",
				open: 1000,
				high: 1050,
				low: 980,
				close: 1020,
				return_rate: 0.02,
				volume: 100000,
			},
		]);

		const wrapper = mountView();
		await flushPromises();
		const input = wrapper.find("input");
		await input.setValue("7203");
		await wrapper.find("button.btn-primary").trigger("click");
		await flushPromises();

		expect(wrapper.text()).toContain("始値");
		expect(wrapper.text()).toContain("高値");
		expect(wrapper.text()).toContain("安値");
		expect(wrapper.text()).toContain("終値");
		expect(wrapper.text()).toContain("騰落率");
		expect(wrapper.text()).toContain("出来高");
		expect(wrapper.text()).toContain("価格データ");
	});
});
