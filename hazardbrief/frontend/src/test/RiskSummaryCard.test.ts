import { mount } from "@vue/test-utils";
import { describe, it, expect } from "vitest";
import RiskSummaryCard from "../components/report/RiskSummaryCard.vue";
import type { RiskCard } from "../types/report";

const mockCard: RiskCard = {
	risk_type: "flood",
	title: "洪水リスク",
	level: "medium",
	level_label: "中",
	level_color: "yellow",
	available: true,
	details: {
		depth_label: "0.5〜1.0m未満（床上浸水）",
		river_name: "テスト川",
		source: "国土交通省 不動産情報ライブラリ",
	},
	description: "想定浸水深: 0.5〜1.0m未満（床上浸水）（テスト川）",
	mitigation: "床上浸水の可能性があります。家財の高所保管、止水板の設置を検討してください。",
};

describe("RiskSummaryCard", () => {
	it("リスクタイトルが表示される", () => {
		const wrapper = mount(RiskSummaryCard, { props: { card: mockCard } });
		expect(wrapper.text()).toContain("洪水リスク");
	});

	it("リスクレベルラベルが表示される", () => {
		const wrapper = mount(RiskSummaryCard, { props: { card: mockCard } });
		expect(wrapper.text()).toContain("中");
	});

	it("説明文が表示される", () => {
		const wrapper = mount(RiskSummaryCard, { props: { card: mockCard } });
		expect(wrapper.text()).toContain("想定浸水深");
	});

	it("対策ヒントが表示される", () => {
		const wrapper = mount(RiskSummaryCard, { props: { card: mockCard } });
		expect(wrapper.text()).toContain("床上浸水の可能性があります");
	});

	it("データ取得不可の場合は警告が表示される", () => {
		const unavailableCard: RiskCard = {
			...mockCard,
			level: "unknown",
			level_label: "要確認",
			available: false,
		};
		const wrapper = mount(RiskSummaryCard, { props: { card: unavailableCard } });
		expect(wrapper.text()).toContain("データを取得できませんでした");
	});

	it("リスクレベル low の場合は緑系スタイルが適用される", () => {
		const lowCard: RiskCard = { ...mockCard, level: "low", level_label: "低" };
		const wrapper = mount(RiskSummaryCard, { props: { card: lowCard } });
		expect(wrapper.html()).toContain("risk-low");
	});

	it("リスクレベル high の場合はオレンジ系スタイルが適用される", () => {
		const highCard: RiskCard = { ...mockCard, level: "high", level_label: "高" };
		const wrapper = mount(RiskSummaryCard, { props: { card: highCard } });
		expect(wrapper.html()).toContain("risk-high");
	});
});
