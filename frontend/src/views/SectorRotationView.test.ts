import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { createMockApi } from "../test/mocks/useApi";

const mockApi = createMockApi();
vi.mock("../composables/useApi", () => ({ useApi: () => mockApi }));

// Stub child components
vi.mock("../components/charts/SectorReturnHeatmap.vue", () => ({
	default: { template: "<div data-testid='heatmap-stub' />" },
}));
vi.mock("../components/charts/SectorRotationTimeline.vue", () => ({
	default: { template: "<div data-testid='timeline-stub' />" },
}));

const { default: SectorRotationView } = await import(
	"./SectorRotationView.vue"
);

function mountView() {
	return mount(SectorRotationView);
}

describe("SectorRotationView", () => {
	beforeEach(() => {
		vi.clearAllMocks();
	});

	it("日本語の見出しが表示される", async () => {
		const wrapper = mountView();
		await flushPromises();
		expect(wrapper.text()).toContain("セクターローテーション");
	});

	it("タブ UI が表示される", async () => {
		const wrapper = mountView();
		await flushPromises();

		expect(wrapper.text()).toContain("ヒートマップ");
		expect(wrapper.text()).toContain("タイムライン");
		expect(wrapper.text()).toContain("遷移行列");
	});

	it("期間タイプ選択が表示される", async () => {
		const wrapper = mountView();
		await flushPromises();

		expect(wrapper.text()).toContain("週次");
		expect(wrapper.text()).toContain("月次");
	});

	it("セクター別リターンラベルが表示される", async () => {
		const wrapper = mountView();
		await flushPromises();

		expect(wrapper.text()).toContain("セクター別リターン");
	});

	it("マウント時に予測データを取得する", async () => {
		mountView();
		await flushPromises();

		expect(mockApi.getSectorRotationPrediction).toHaveBeenCalled();
	});

	it("予測データが available の場合にパネルを表示する", async () => {
		mockApi.getSectorRotationPrediction.mockResolvedValue({
			available: true,
			current: { state_id: 0, state_name: "ディフェンシブ主導" },
			prediction: { state_id: 1, state_name: "景気敏感主導", confidence: 0.65 },
			top_sectors: [{ sector: "電気機器", avg_return: 0.02 }],
			all_probabilities: [
				{ state_id: 0, state_name: "ディフェンシブ主導", probability: 0.35 },
				{ state_id: 1, state_name: "景気敏感主導", probability: 0.65 },
			],
			model_accuracy: 0.72,
		});

		const wrapper = mountView();
		await flushPromises();

		expect(wrapper.text()).toContain("現在のローテーション状態");
		expect(wrapper.text()).toContain("次期予測状態");
		expect(wrapper.text()).toContain("状態別確率");
		expect(wrapper.text()).toContain("ディフェンシブ主導");
		expect(wrapper.text()).toContain("景気敏感主導");
		expect(wrapper.text()).toContain("65%");
	});

	it("遷移行列タブクリックで API を呼び出す", async () => {
		const wrapper = mountView();
		await flushPromises();

		const transitionsTab = wrapper
			.findAll("button")
			.find((b) => b.text() === "遷移行列");
		expect(transitionsTab).toBeDefined();
		await transitionsTab?.trigger("click");
		await flushPromises();

		expect(mockApi.getSectorRotationTransitions).toHaveBeenCalled();
	});
});
