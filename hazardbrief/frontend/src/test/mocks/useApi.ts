/**
 * useApi composable のモック
 */
import { vi } from "vitest";

export const mockProperties = [
	{
		id: "prop-1",
		company_id: "company-1",
		created_by: null,
		address: "東京都千代田区丸の内1-1-1",
		latitude: 35.6812,
		longitude: 139.7671,
		property_name: "テスト物件",
		notes: null,
		created_at: "2026-03-06T10:00:00",
	},
];

export const mockHazardReport = {
	property: mockProperties[0],
	report: {
		cards: [
			{
				risk_type: "flood",
				title: "洪水リスク",
				level: "medium",
				level_label: "中",
				level_color: "yellow",
				available: true,
				details: { depth_label: "0.5〜1.0m未満（床上浸水）", river_name: "テスト川", source: "国土交通省" },
				description: "想定浸水深: 0.5〜1.0m未満",
				mitigation: "床上浸水の可能性があります。",
			},
			{
				risk_type: "landslide",
				title: "土砂災害リスク",
				level: "low",
				level_label: "低",
				level_color: "green",
				available: true,
				details: { zone_label: "警戒区域外", disaster_type_label: null, source: "国土交通省" },
				description: "警戒区域外",
				mitigation: "土砂災害警戒区域外です。",
			},
			{
				risk_type: "tsunami",
				title: "津波リスク",
				level: "low",
				level_label: "低",
				level_color: "green",
				available: true,
				details: { depth_label: "浸水なし（想定区域外）", source: "国土交通省" },
				description: "想定浸水深: 浸水なし（想定区域外）",
				mitigation: "津波浸水想定区域外です。",
			},
			{
				risk_type: "ground",
				title: "地盤リスク",
				level: "low",
				level_label: "低",
				level_color: "green",
				available: true,
				details: { elevation: 15.5, description: "標高が高い", source: "国土地理院" },
				description: "標高が高く、地盤リスクは相対的に低い傾向です",
				mitigation: "標高が高く、地盤リスクは相対的に低い傾向にあります。",
			},
		],
		risk_summary: {
			overall_level: "medium",
			levels: { flood: "medium", landslide: "low", tsunami: "low", ground: "low" },
			unavailable_count: 0,
			has_partial_data: false,
			disclaimer: "テスト用免責事項",
		},
		fetched_at: "2026-03-06T10:00:00",
		expires_at: "2026-06-04T10:00:00",
		generated_at: "2026-03-06T10:00:00",
	},
	disclaimer:
		"本レポートは公的機関が公表するデータを基に作成しています。",
};

export const mockUseApi = () => ({
	getProperties: vi.fn().mockResolvedValue(mockProperties),
	getProperty: vi.fn().mockResolvedValue(mockProperties[0]),
	createProperty: vi.fn().mockResolvedValue(mockProperties[0]),
	deleteProperty: vi.fn().mockResolvedValue({ property_id: "prop-1", status: "deleted" }),
	getHazard: vi.fn().mockResolvedValue({
		property_id: "prop-1",
		flood_risk: mockHazardReport.report.cards[0].details,
		landslide_risk: {},
		tsunami_risk: {},
		ground_risk: {},
		risk_summary: mockHazardReport.report.risk_summary,
		fetched_at: "2026-03-06T10:00:00",
		from_cache: false,
	}),
	getReport: vi.fn().mockResolvedValue(mockHazardReport),
	getCompanies: vi.fn().mockResolvedValue([]),
	getCompany: vi.fn().mockResolvedValue({}),
	createCompany: vi.fn().mockResolvedValue({}),
});
