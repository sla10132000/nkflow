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

	it("正の騰落率は緑系の背景色", () => {
		const wrapper = mountHeatMap([{ sector: "電気機器", avg_return: 0.03 }]);

		const cell = wrapper.find("div.grid > div");
		const bg = cell.attributes("style");
		expect(bg).toContain("#166534"); // > 0.02 → darkest green
	});

	it("負の騰落率は赤系の背景色", () => {
		const wrapper = mountHeatMap([{ sector: "銀行業", avg_return: -0.025 }]);

		const cell = wrapper.find("div.grid > div");
		const bg = cell.attributes("style");
		expect(bg).toContain("#991b1b"); // < -0.02 → darkest red
	});

	it("長いセクター名は8文字目以降省略される", () => {
		const wrapper = mountHeatMap([
			{ sector: "情報・通信・サービス業", avg_return: 0.01 },
		]);

		expect(wrapper.text()).toContain("情報・通信・サ…");
	});

	it("空配列でもエラーにならない", () => {
		const wrapper = mountHeatMap([]);
		expect(wrapper.exists()).toBe(true);
	});

	it("グリッドのカラム数が最大6", () => {
		const sectors = Array.from({ length: 10 }, (_, i) => ({
			sector: `セクター${i}`,
			avg_return: 0.01 * i,
		}));
		const wrapper = mountHeatMap(sectors);
		const style = wrapper.find("div.grid").attributes("style");
		expect(style).toContain("repeat(6,");
	});

	it("セクター数が6未満ならその数がカラム数", () => {
		const sectors = [
			{ sector: "A", avg_return: 0.01 },
			{ sector: "B", avg_return: -0.01 },
			{ sector: "C", avg_return: 0.005 },
		];
		const wrapper = mountHeatMap(sectors);
		const style = wrapper.find("div.grid").attributes("style");
		expect(style).toContain("repeat(3,");
	});
});
