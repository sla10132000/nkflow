/**
 * ハザードリスク型定義
 * リスクレベル: low / medium / high / unknown
 */

export type RiskLevel = "low" | "medium" | "high" | "unknown";

export interface BaseRisk {
	level: RiskLevel;
	source: string;
	available: boolean;
	unavailable_reason?: string;
}

export interface FloodRisk extends BaseRisk {
	depth: string | null;
	depth_label: string;
	river_name: string | null;
}

export interface LandslideRisk extends BaseRisk {
	zone_type: "special" | "warning" | "none" | null;
	zone_label: string;
	disaster_type: string | null;
	disaster_type_label: string | null;
}

export interface TsunamiRisk extends BaseRisk {
	depth: string | null;
	depth_label: string;
}

export interface GroundRisk extends BaseRisk {
	elevation: number | null;
	description: string;
	liquefaction_note: string;
}

export interface RiskSummary {
	overall_level: RiskLevel;
	levels: {
		flood: RiskLevel;
		landslide: RiskLevel;
		tsunami: RiskLevel;
		ground: RiskLevel;
	};
	unavailable_count: number;
	has_partial_data: boolean;
	disclaimer: string;
}

export interface HazardData {
	property_id: string;
	flood_risk: FloodRisk;
	landslide_risk: LandslideRisk;
	tsunami_risk: TsunamiRisk;
	ground_risk: GroundRisk;
	risk_summary: RiskSummary;
	fetched_at: string;
	from_cache: boolean;
}
