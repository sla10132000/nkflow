import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { createMockApi } from "../test/mocks/useApi";

const mockApi = createMockApi();
vi.mock("../composables/useApi", () => ({ useApi: () => mockApi }));

// Stub child components
vi.mock("../components/charts/HeatMap.vue", () => ({
	default: { template: "<div data-testid='heatmap-stub' />" },
}));

const { default: OverviewView } = await import("./OverviewView.vue");

function mountView() {
	return mount(OverviewView, {
		global: {
			stubs: { RouterLink: { template: "<a><slot /></a>" } },
		},
	});
}

describe("OverviewView", () => {
	beforeEach(() => {
		vi.clearAllMocks();
	});

	it("日本語の見出しが表示される", async () => {
		mockApi.getSummary.mockResolvedValue({
			date: "2026-03-04",
			nikkei_close: 38000,
			nikkei_return: 0.012,
			regime: "risk_on",
			active_signals: 3,
			top_gainers: [],
			top_losers: [],
			sector_rotation: [],
		});

		const wrapper = mountView();
		await flushPromises();

		expect(wrapper.text()).toContain("概要");
		expect(wrapper.text()).toContain("日経終値");
		expect(wrapper.text()).toContain("騰落率");
		expect(wrapper.text()).toContain("レジーム");
	});

	it("サマリーデータを正しく表示する", async () => {
		mockApi.getSummary.mockResolvedValue({
			date: "2026-03-04",
			nikkei_close: 38000,
			nikkei_return: 0.012,
			regime: "risk_on",
			active_signals: 5,
			top_gainers: [{ code: "7203", name: "トヨタ", return_rate: 0.05 }],
			top_losers: [{ code: "9984", name: "ソフトバンクG", return_rate: -0.03 }],
			sector_rotation: [],
		});

		const wrapper = mountView();
		await flushPromises();

		expect(wrapper.text()).toContain("2026-03-04");
		expect(wrapper.text()).toContain("38,000");
		expect(wrapper.text()).toContain("+1.20%");
		expect(wrapper.text()).toContain("上昇上位");
		expect(wrapper.text()).toContain("下落上位");
		expect(wrapper.text()).toContain("7203");
		expect(wrapper.text()).toContain("9984");
	});

	it("API を days=1 で呼び出す", async () => {
		mockApi.getSummary.mockResolvedValue({});
		mountView();
		await flushPromises();
		expect(mockApi.getSummary).toHaveBeenCalledWith(1);
	});

	it("getNews が昨日の日付・limit=3 で呼び出される", async () => {
		mockApi.getSummary.mockResolvedValue({});
		mountView();
		await flushPromises();
		expect(mockApi.getNews).toHaveBeenCalledWith(
			expect.objectContaining({ limit: 3 }),
		);
	});

	it("ニュースが取得できた場合に表示される", async () => {
		mockApi.getSummary.mockResolvedValue({
			date: "2026-03-04",
			nikkei_close: 38000,
			nikkei_return: 0.012,
			regime: "risk_on",
			active_signals: 0,
			top_gainers: [],
			top_losers: [],
			sector_rotation: [],
		});
		mockApi.getNews.mockResolvedValue([
			{
				id: "n1",
				published_at: "2026-03-03T06:00:00Z",
				source: "reuters",
				source_name: "Reuters",
				title: "Toyota raises forecast",
				title_ja: "トヨタが業績予想を上方修正",
				url: "https://example.com/1",
				language: "ja",
				image_url: null,
				sentiment: 0.8,
			},
		]);

		const wrapper = mountView();
		await flushPromises();

		expect(wrapper.text()).toContain("昨日の主なニュース");
		expect(wrapper.text()).toContain("トヨタが業績予想を上方修正");
		expect(wrapper.text()).toContain("Reuters");
	});

	it("読み込み中の表示", () => {
		mockApi.getSummary.mockReturnValue(new Promise(() => {})); // never resolves
		const wrapper = mountView();
		expect(wrapper.text()).toContain("読み込み中...");
	});

	it("エラー時にメッセージを表示する", async () => {
		mockApi.getSummary.mockRejectedValue(new Error("Network Error"));
		const wrapper = mountView();
		await flushPromises();
		expect(wrapper.text()).toContain("Network Error");
	});

	it("セクター騰落率セクションが表示される", async () => {
		mockApi.getSummary.mockResolvedValue({
			date: "2026-03-04",
			nikkei_close: 38000,
			nikkei_return: 0.012,
			regime: "risk_on",
			active_signals: 0,
			top_gainers: [],
			top_losers: [],
			sector_rotation: [],
		});

		const wrapper = mountView();
		await flushPromises();

		expect(wrapper.text()).toContain("セクター騰落率");
	});
});
