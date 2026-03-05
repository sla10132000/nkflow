import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import HeatMap from "./HeatMap.vue";

function mountHeatMap(sectors: { sector: string; avg_return: number }[]) {
	return mount(HeatMap, { props: { sectors } });
}

describe("HeatMap", () => {
	it("セクターを表示する", () => {
		const wrapper = mountHeatMap([
			{ sector: "電気機器", avg_return: 0.03 },
			{ sector: "銀行業", avg_return: -0.01 },
		]);

		expect(wrapper.text()).toContain("電気機器");
		expect(wrapper.text()).toContain("銀行業");
	});

	it("騰落率のパーセント表示", () => {
		const wrapper = mountHeatMap([
			{ sector: "電気機器", avg_return: 0.03 },
			{ sector: "銀行業", avg_return: -0.015 },
		]);

		expect(wrapper.text()).toContain("+3.00%");
		expect(wrapper.text()).toContain("-1.50%");
	});

	it("正の騰落率は緑色のバー", () => {
		const wrapper = mountHeatMap([{ sector: "電気機器", avg_return: 0.03 }]);

		const bar = wrapper.find(".bg-green-400");
		expect(bar.exists()).toBe(true);
	});

	it("負の騰落率は赤色のバー", () => {
		const wrapper = mountHeatMap([{ sector: "銀行業", avg_return: -0.025 }]);

		const bar = wrapper.find(".bg-red-400");
		expect(bar.exists()).toBe(true);
	});

	it("騰落率降順にソートされる", () => {
		const wrapper = mountHeatMap([
			{ sector: "銀行業", avg_return: -0.01 },
			{ sector: "電気機器", avg_return: 0.03 },
			{ sector: "医薬品", avg_return: 0.005 },
		]);

		const names = wrapper.findAll(".w-20").map((el) => el.text());
		expect(names).toEqual(["電気機器", "医薬品", "銀行業"]);
	});

	it("空配列でもエラーにならない", () => {
		const wrapper = mountHeatMap([]);
		expect(wrapper.exists()).toBe(true);
	});

	it("バーの幅が最大絶対値に基づいて計算される", () => {
		const wrapper = mountHeatMap([
			{ sector: "電気機器", avg_return: 0.02 },
			{ sector: "銀行業", avg_return: -0.01 },
		]);

		const bars = wrapper.findAll(".bg-gray-100 > div");
		// 電気機器: 0.02/0.02 * 100 = 100%
		expect(bars[0].attributes("style")).toContain("width: 100%");
		// 銀行業: 0.01/0.02 * 100 = 50%
		expect(bars[1].attributes("style")).toContain("width: 50%");
	});
});
