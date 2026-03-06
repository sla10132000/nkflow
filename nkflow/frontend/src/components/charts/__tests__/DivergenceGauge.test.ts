import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import DivergenceGauge from "../DivergenceGauge.vue";

function mountGauge(value: number | null, regime: string | null = null) {
	return mount(DivergenceGauge, { props: { value, regime } });
}

describe("DivergenceGauge", () => {
	it("SVG が描画される", () => {
		const wrapper = mountGauge(0.3, "bullish");
		expect(wrapper.find("svg").exists()).toBe(true);
	});

	it("5 つのカラーゾーン rect が描画される", () => {
		const wrapper = mountGauge(0, "neutral");
		const rects = wrapper.findAll("svg rect");
		expect(rects.length).toBe(5);
	});

	it("value が null のとき インジケーター line が描画されない", () => {
		const wrapper = mountGauge(null, null);
		// インジケーターの line (stroke-width=2) は v-if="indicatorX !== null" で非表示
		const lines = wrapper.findAll("svg line");
		// 中央ゼロライン (stroke-dasharray) のみ
		expect(lines.length).toBe(1);
	});

	it("value が非 null のとき インジケーター line が描画される", () => {
		const wrapper = mountGauge(0.5, "bullish");
		const lines = wrapper.findAll("svg line");
		// ゼロライン + インジケーター = 2 本
		expect(lines.length).toBe(2);
	});

	it("value の数値ラベルが表示される", () => {
		const wrapper = mountGauge(0.42, "bullish");
		expect(wrapper.text()).toContain("0.42");
	});

	it("value が負のとき正しく表示される", () => {
		const wrapper = mountGauge(-0.75, "bearish");
		expect(wrapper.text()).toContain("-0.75");
	});

	it("regime=bullish のラベルが表示される", () => {
		const wrapper = mountGauge(0.4, "bullish");
		expect(wrapper.text()).toContain("強気");
	});

	it("regime=bearish のラベルが表示される", () => {
		const wrapper = mountGauge(-0.4, "bearish");
		expect(wrapper.text()).toContain("弱気");
	});

	it("regime=neutral のラベルが表示される", () => {
		const wrapper = mountGauge(0, "neutral");
		expect(wrapper.text()).toContain("中立");
	});

	it("regime=diverging のラベルが表示される", () => {
		const wrapper = mountGauge(0.1, "diverging");
		expect(wrapper.text()).toContain("乖離拡大");
	});

	it("regime が null のとき レジームラベルが非表示", () => {
		const wrapper = mountGauge(0, null);
		// regime が null のとき レジームラベルの span は描画されない
		expect(wrapper.find("span").exists()).toBe(false);
	});

	it("端ラベルが表示される", () => {
		const wrapper = mountGauge(0, "neutral");
		const svgText = wrapper.find("svg").text();
		expect(svgText).toContain("底入れ");
		expect(svgText).toContain("天井警戒");
	});

	it("value=1.0 (上限) でもクラッシュしない", () => {
		const wrapper = mountGauge(1.0, "bullish");
		expect(wrapper.find("svg").exists()).toBe(true);
	});

	it("value=-1.0 (下限) でもクラッシュしない", () => {
		const wrapper = mountGauge(-1.0, "bearish");
		expect(wrapper.find("svg").exists()).toBe(true);
	});
});
