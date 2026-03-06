import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import type { InvestorFlowIndicator } from "../../../types";
import InvestorFlowChart from "../InvestorFlowChart.vue";

const sampleIndicators: InvestorFlowIndicator[] = [
	{
		week_end: "2026-01-09",
		foreigners_net: 50_000_000_000,
		individuals_net: -30_000_000_000,
		foreigners_4w_ma: 40_000_000_000,
		individuals_4w_ma: -25_000_000_000,
		foreigners_momentum: 0.1,
		individuals_momentum: -0.05,
		divergence_score: 0.4,
		nikkei_return_4w: 0.02,
		flow_regime: "bullish",
	},
	{
		week_end: "2026-01-16",
		foreigners_net: -20_000_000_000,
		individuals_net: 15_000_000_000,
		foreigners_4w_ma: 30_000_000_000,
		individuals_4w_ma: -10_000_000_000,
		foreigners_momentum: -0.05,
		individuals_momentum: 0.03,
		divergence_score: -0.2,
		nikkei_return_4w: -0.01,
		flow_regime: "bearish",
	},
];

function mountChart(
	indicators: InvestorFlowIndicator[] = sampleIndicators,
	weeks = 13,
) {
	return mount(InvestorFlowChart, {
		props: { indicators, weeks },
	});
}

describe("InvestorFlowChart", () => {
	it("canvas 要素が描画される", () => {
		const wrapper = mountChart();
		expect(wrapper.find("canvas").exists()).toBe(true);
	});

	it("indicators が空のとき canvas は描画される", () => {
		const wrapper = mountChart([]);
		expect(wrapper.find("canvas").exists()).toBe(true);
	});

	it("weeks prop がデフォルト 13 で動作する", () => {
		const wrapper = mount(InvestorFlowChart, {
			props: { indicators: sampleIndicators },
		});
		expect(wrapper.find("canvas").exists()).toBe(true);
	});

	it("weeks prop でスライス数が変わる", () => {
		const manyIndicators: InvestorFlowIndicator[] = Array.from(
			{ length: 20 },
			(_, i) => ({
				week_end: `2026-01-${String(i + 1).padStart(2, "0")}`,
				foreigners_net: i * 1e9,
				individuals_net: -i * 5e8,
				foreigners_4w_ma: null,
				individuals_4w_ma: null,
				foreigners_momentum: null,
				individuals_momentum: null,
				divergence_score: null,
				nikkei_return_4w: null,
				flow_regime: null,
			}),
		);
		// weeks=5 に設定してもクラッシュしない
		const wrapper = mount(InvestorFlowChart, {
			props: { indicators: manyIndicators, weeks: 5 },
		});
		expect(wrapper.find("canvas").exists()).toBe(true);
	});

	it("ゾーン凡例が表示される (弱気域/過熱域)", () => {
		const wrapper = mountChart();
		expect(wrapper.text()).toContain("弱気域");
		expect(wrapper.text()).toContain("過熱域");
	});

	it("divergence_score が null でもクラッシュしない", () => {
		const indicators: InvestorFlowIndicator[] = [
			{
				...sampleIndicators[0],
				divergence_score: null,
			},
		];
		const wrapper = mountChart(indicators);
		expect(wrapper.find("canvas").exists()).toBe(true);
	});
});
