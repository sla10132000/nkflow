/**
 * ハザードレポート型定義
 */
import type { Property } from "./property";
import type { RiskLevel, RiskSummary } from "./hazard";

export interface RiskCard {
	risk_type: "flood" | "landslide" | "tsunami" | "ground";
	title: string;
	level: RiskLevel;
	level_label: string;
	level_color: "green" | "yellow" | "orange" | "gray";
	available: boolean;
	details: Record<string, string | number | null>;
	description: string;
	mitigation: string;
}

export interface ReportData {
	cards: RiskCard[];
	risk_summary: RiskSummary;
	fetched_at: string;
	expires_at: string | null;
	generated_at: string;
}

export interface HazardReport {
	property: Property;
	report: ReportData;
	disclaimer: string;
}
