import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { createMockApi } from "../test/mocks/useApi";

const mockApi = createMockApi();
vi.mock("../composables/useApi", () => ({ useApi: () => mockApi }));

const { default: NewsView } = await import("./NewsView.vue");

function mountView() {
	return mount(NewsView);
}

describe("NewsView", () => {
	beforeEach(() => {
		vi.clearAllMocks();
	});

	it("日本語の見出しが表示される", async () => {
		const wrapper = mountView();
		await flushPromises();

		expect(wrapper.text()).toContain("ニュース");
		expect(wrapper.text()).toContain("本日のニュース");
	});

	it("フィルタ UI の日本語ラベルが表示される", async () => {
		const wrapper = mountView();
		await flushPromises();

		expect(wrapper.text()).toContain("日付");
		expect(wrapper.text()).toContain("絞り込み");
		expect(wrapper.text()).toContain("クリア");
	});

	it("初期日付が JST 当日にセットされる", () => {
		const expectedDate = new Date().toLocaleDateString("sv-SE", {
			timeZone: "Asia/Tokyo",
		});
		const wrapper = mountView();
		const input = wrapper.find("input[type='date']");
		expect((input.element as HTMLInputElement).value).toBe(expectedDate);
	});

	it("マウント時に API を呼び出す", async () => {
		mountView();
		await flushPromises();

		expect(mockApi.getNews).toHaveBeenCalled();
		expect(mockApi.getNewsSummary).toHaveBeenCalled();
	});

	it("API パラメータに date と limit を渡す", async () => {
		mountView();
		await flushPromises();

		const newsCall = mockApi.getNews.mock.calls[0][0];
		expect(newsCall).toHaveProperty("limit", 50);
		expect(newsCall).toHaveProperty("date");
	});

	it("サマリーの合計件数を表示する", async () => {
		mockApi.getNewsSummary.mockResolvedValue({
			date: "2026-03-04",
			total: 42,
			sources: [{ source: "Reuters", count: 20 }],
		});
		mockApi.getNews.mockResolvedValue([]);

		const wrapper = mountView();
		await flushPromises();

		expect(wrapper.text()).toContain("42 件");
	});

	it("記事一覧を表示する", async () => {
		mockApi.getNews.mockResolvedValue([
			{
				id: 1,
				title: "Test Article",
				title_ja: "テスト記事",
				source: "Reuters",
				published_at: "2026-03-04T10:00:00Z",
				sentiment: 0.5,
				url: "https://example.com",
			},
		]);
		mockApi.getNewsSummary.mockResolvedValue(null);

		const wrapper = mountView();
		await flushPromises();

		expect(wrapper.text()).toContain("テスト記事");
		expect(wrapper.text()).toContain("ポジティブ");
	});

	it("記事なしの場合にメッセージを表示する", async () => {
		mockApi.getNews.mockResolvedValue([]);
		mockApi.getNewsSummary.mockResolvedValue(null);

		const wrapper = mountView();
		await flushPromises();

		expect(wrapper.text()).toContain("記事なし");
	});
});
