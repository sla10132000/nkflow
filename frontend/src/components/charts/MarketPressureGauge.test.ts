import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import MarketPressureGauge from "./MarketPressureGauge.vue";

function mountGauge(props: {
	plRatio: number | null;
	plZone: string;
	buyGrowth4w: number | null;
}) {
	return mount(MarketPressureGauge, { props });
}

describe("MarketPressureGauge", () => {
	it("SVG が描画される", () => {
		const wrapper = mountGauge({
			plRatio: -0.05,
			plZone: "neutral",
			buyGrowth4w: 0.03,
		});
		expect(wrapper.find("svg").exists()).toBe(true);
	});

	it("ゾーンラベル — 天井警戒", () => {
		const wrapper = mountGauge({
			plRatio: 0.18,
			plZone: "ceiling",
			buyGrowth4w: 0.1,
		});
		expect(wrapper.text()).toContain("天井警戒");
	});

	it("ゾーンラベル — 過熱", () => {
		const wrapper = mountGauge({
			plRatio: 0.08,
			plZone: "overheat",
			buyGrowth4w: 0.05,
		});
		expect(wrapper.text()).toContain("過熱");
	});

	it("ゾーンラベル — 中立", () => {
		const wrapper = mountGauge({
			plRatio: 0.02,
			plZone: "neutral",
			buyGrowth4w: 0.01,
		});
		expect(wrapper.text()).toContain("中立");
	});

	it("ゾーンラベル — 弱含み", () => {
		const wrapper = mountGauge({
			plRatio: -0.05,
			plZone: "weak",
			buyGrowth4w: -0.01,
		});
		expect(wrapper.text()).toContain("弱含み");
	});

	it("ゾーンラベル — 投げ売り", () => {
		const wrapper = mountGauge({
			plRatio: -0.12,
			plZone: "sellin",
			buyGrowth4w: -0.05,
		});
		expect(wrapper.text()).toContain("投げ売り");
	});

	it("ゾーンラベル — 大底", () => {
		const wrapper = mountGauge({
			plRatio: -0.2,
			plZone: "bottom",
			buyGrowth4w: -0.1,
		});
		expect(wrapper.text()).toContain("大底");
	});

	it("plRatio が null のとき — を表示", () => {
		const wrapper = mountGauge({
			plRatio: null,
			plZone: "neutral",
			buyGrowth4w: null,
		});
		// text nodes inside SVG
		const svgText = wrapper.find("svg").text();
		expect(svgText).toContain("—");
	});

	it("plRatio のパーセント表示", () => {
		const wrapper = mountGauge({
			plRatio: -0.05,
			plZone: "weak",
			buyGrowth4w: 0.02,
		});
		expect(wrapper.text()).toContain("-5.0%");
	});

	it("信用買残4週増加率ラベルが表示される", () => {
		const wrapper = mountGauge({
			plRatio: 0,
			plZone: "neutral",
			buyGrowth4w: 0.03,
		});
		expect(wrapper.text()).toContain("信用買残4週増加率");
		expect(wrapper.text()).toContain("3.0%");
	});

	it("buyGrowth4w が null のとき — を表示", () => {
		const wrapper = mountGauge({
			plRatio: 0,
			plZone: "neutral",
			buyGrowth4w: null,
		});
		expect(wrapper.text()).toContain("信用買残4週増加率");
		expect(wrapper.text()).toContain("—");
	});

	it("gauge にセグメントが 6 つある (大底→天井)", () => {
		const wrapper = mountGauge({
			plRatio: 0,
			plZone: "neutral",
			buyGrowth4w: 0,
		});
		const paths = wrapper.findAll("svg path");
		expect(paths.length).toBe(6);
	});

	it("端ラベル 大底・天井 が表示される", () => {
		const wrapper = mountGauge({
			plRatio: 0,
			plZone: "neutral",
			buyGrowth4w: 0,
		});
		const svgText = wrapper.find("svg").text();
		expect(svgText).toContain("大底");
		expect(svgText).toContain("天井");
	});
});
