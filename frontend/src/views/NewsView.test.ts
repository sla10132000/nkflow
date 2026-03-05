import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { createMockApi } from "../test/mocks/useApi";

const mockApi = createMockApi();
vi.mock("../composables/useApi", () => ({ useApi: () => mockApi }));

const { default: NewsView } = await import("./NewsView.vue");

function mountView() {
	return mount(NewsView);
}

const mockSummary = {
	date: "2026-03-04",
	total: 42,
	sources: [{ source: "Reuters", count: 20 }],
	sentiment_dist: { positive: 15, negative: 10, neutral: 17 },
	categories: [
		{ category: "決算", count: 12 },
		{ category: "金融政策", count: 8 },
	],
};

const mockArticle = {
	id: "a1",
	title: "Test Article",
	title_ja: "テスト記事",
	source: "reuters",
	source_name: "Reuters",
	published_at: "2026-03-04T10:00:00Z",
	sentiment: 0.5,
	url: "https://example.com",
	language: "en",
	image_url: null,
	category: "決算",
	tickers: "7203",
};

describe("NewsView", () => {
	beforeEach(() => {
		vi.clearAllMocks();
		mockApi.getNews.mockResolvedValue([]);
		mockApi.getNewsSummary.mockResolvedValue(null);
	});

	it("ページタイトルが表示される", async () => {
		const wrapper = mountView();
		await flushPromises();
		expect(wrapper.text()).toContain("ニュース");
	});

	it("クイック日付プリセットボタンが表示される", async () => {
		const wrapper = mountView();
		await flushPromises();
		expect(wrapper.text()).toContain("今日");
		expect(wrapper.text()).toContain("昨日");
		expect(wrapper.text()).toContain("1週間");
	});

	it("初期日付が空 (最新モード)", () => {
		const wrapper = mountView();
		const input = wrapper.find("input[type='date']");
		expect((input.element as HTMLInputElement).value).toBe("");
	});

	it("マウント時に API を呼び出す", async () => {
		mountView();
		await flushPromises();
		expect(mockApi.getNews).toHaveBeenCalled();
		expect(mockApi.getNewsSummary).toHaveBeenCalled();
	});

	it("API パラメータに limit を渡す", async () => {
		mountView();
		await flushPromises();
		const newsCall = mockApi.getNews.mock.calls[0][0];
		expect(newsCall).toHaveProperty("limit", 100);
	});

	it("サマリのセンチメント分布を表示する", async () => {
		mockApi.getNewsSummary.mockResolvedValue(mockSummary);
		const wrapper = mountView();
		await flushPromises();

		expect(wrapper.text()).toContain("合計: 42件");
		expect(wrapper.text()).toContain("▲ 15");
		expect(wrapper.text()).toContain("▼ 10");
	});

	it("テーマバッジを表示する", async () => {
		mockApi.getNewsSummary.mockResolvedValue(mockSummary);
		const wrapper = mountView();
		await flushPromises();

		expect(wrapper.text()).toContain("決算");
		expect(wrapper.text()).toContain("金融政策");
	});

	it("タブが表示される", async () => {
		const wrapper = mountView();
		await flushPromises();

		expect(wrapper.text()).toContain("速報");
		expect(wrapper.text()).toContain("テーマ別");
		expect(wrapper.text()).toContain("ソース別");
	});

	it("記事一覧にカテゴリバッジとティッカーを表示する", async () => {
		mockApi.getNews.mockResolvedValue([mockArticle]);
		const wrapper = mountView();
		await flushPromises();

		expect(wrapper.text()).toContain("テスト記事");
		expect(wrapper.text()).toContain("決算");
		expect(wrapper.text()).toContain("7203");
	});

	it("センチメントスコアを表示する", async () => {
		mockApi.getNews.mockResolvedValue([mockArticle]);
		const wrapper = mountView();
		await flushPromises();

		expect(wrapper.text()).toContain("▲");
		expect(wrapper.text()).toContain("0.5");
	});

	it("記事なしの場合にメッセージを表示する", async () => {
		const wrapper = mountView();
		await flushPromises();
		expect(wrapper.text()).toContain("記事なし");
	});

	it("相対日付がホバーで絶対日付を表示する (title属性)", async () => {
		mockApi.getNews.mockResolvedValue([mockArticle]);
		const wrapper = mountView();
		await flushPromises();

		const dateSpan = wrapper.findAll("span").find((s) => s.attributes("title"));
		expect(dateSpan).toBeTruthy();
		expect(dateSpan?.attributes("title")).toContain("2026/03/04");
	});

	it("テーマ別タブでグループ表示される", async () => {
		mockApi.getNews.mockResolvedValue([
			{ ...mockArticle, id: "a1", category: "決算" },
			{ ...mockArticle, id: "a2", category: "為替", title_ja: "円安ニュース" },
		]);
		const wrapper = mountView();
		await flushPromises();

		// テーマ別タブをクリック
		const themeTab = wrapper
			.findAll("button")
			.find((b) => b.text() === "テーマ別");
		await themeTab?.trigger("click");
		await flushPromises();

		expect(wrapper.text()).toContain("決算");
		expect(wrapper.text()).toContain("為替");
		expect(wrapper.text()).toContain("1件");
	});
});
