export interface Stock {
	code: string;
	name: string;
	sector: string;
}

export interface DailyPrice {
	code: string;
	date: string;
	open: number;
	high: number;
	low: number;
	close: number;
	volume: number;
	return_rate: number;
	price_range: number;
}

export interface Signal {
	id: number;
	date: string;
	signal_type: string;
	code: string | null;
	sector: string | null;
	direction: "bullish" | "bearish";
	confidence: number;
	reasoning: Record<string, unknown>;
}

export interface NetworkData {
	nodes: { id: string; label: string; group: string; size: number }[];
	edges: {
		from: string;
		to: string;
		value: number;
		arrows?: string;
		edge_count?: number;
		coefficient?: number;
	}[];
}

export interface DailySummary {
	date: string;
	nikkei_close: number;
	nikkei_return: number;
	regime: string;
	top_gainers: (Stock & { return_rate: number })[];
	top_losers: (Stock & { return_rate: number })[];
	active_signals: number;
	sector_rotation: {
		sector: string;
		avg_return: number;
		total_volume: number;
	}[];
}

export interface FundFlowTimeseriesValue {
	count: number;
	avg_spread: number;
}

export interface FundFlowTimeseriesSeries {
	label: string;
	sector_from: string;
	sector_to: string;
	values: FundFlowTimeseriesValue[];
}

export interface FundFlowTimeseries {
	periods: string[];
	start_dates: string[];
	series: FundFlowTimeseriesSeries[];
}

export interface FundFlowCumulativePeriod {
	key: string;
	start_date: string;
	regime: "risk_on" | "risk_off" | "neutral" | string;
}

export interface FundFlowCumulativeSeries {
	label: string;
	sector_from: string;
	sector_to: string;
	cumulative_spread: number[];
	sector_cumulative_return: number[];
}

export interface FundFlowCumulative {
	base_date: string;
	periods: FundFlowCumulativePeriod[];
	series: FundFlowCumulativeSeries[];
}

export interface MarketPressureTimeseries {
	dates: string[];
	pl_ratio: (number | null)[];
	pl_zone: string[];
	buy_growth_4w: (number | null)[];
	margin_ratio: (number | null)[];
	margin_ratio_trend: (number | null)[];
	signal_flags: Array<{ credit_overheating?: boolean }>;
}

// ─── Phase 17: セクターローテーション ───────────────────────────────────────

export interface SectorReturnEntry {
	period: string;
	sector: string;
	return_rate: number;
	rank: number;
}

export interface SectorRotationHeatmap {
	periods: string[];
	sectors: string[];
	data: SectorReturnEntry[];
}

export interface SectorRotationState {
	period: string;
	state_id: number;
	state_name: string;
	top_sectors: { sector: string; avg_return: number }[];
}

export interface SectorRotationStates {
	states: SectorRotationState[];
}

export interface SectorRotationTransition {
	from_state: number;
	to_state: number;
	probability: number;
	count: number;
}

export interface SectorRotationTransitions {
	transitions: SectorRotationTransition[];
	state_names: Record<number, string>;
	avg_durations: Record<number, number>;
}

export interface SectorRotationPrediction {
	available: boolean;
	calc_date?: string;
	current?: { state_id: number; state_name: string };
	prediction?: { state_id: number; state_name: string; confidence: number };
	top_sectors?: { sector: string; avg_return: number }[];
	all_probabilities?: {
		state_id: number;
		state_name: string;
		probability: number;
	}[];
	model_accuracy?: number;
}

// ─── Phase 18: ニュース ───────────────────────────────────────────────────────

export interface NewsArticle {
	id: string;
	published_at: string;
	source: string;
	source_name: string | null;
	title: string;
	title_ja: string | null;
	url: string;
	language: string;
	image_url: string | null;
	sentiment: number | null;
	category: string | null;
	tickers: string | null;
}

export interface NewsSummary {
	date: string | null;
	total: number;
	sources: { source: string; count: number }[];
	sentiment_dist: { positive: number; negative: number; neutral: number };
	categories: { category: string; count: number }[];
}

// ─── Phase 21: 恐怖指数 ───────────────────────────────────────────────────────

export interface FearIndices {
	vix: { value: number; change_pct: number | null; date: string } | null;
	btc_fear_greed: {
		value: number;
		classification: string;
		date: string;
	} | null;
}

// ─────────────────────────────────────────────────────────────────────────────

export interface StockDetail {
	code: string;
	name: string;
	sector: string;
	recent_prices: DailyPrice[];
	causes: {
		target: string;
		name: string;
		sector: string;
		lag_days: number;
		p_value: number;
		f_stat: number;
	}[];
	caused_by: {
		source: string;
		name: string;
		sector: string;
		lag_days: number;
		p_value: number;
		f_stat: number;
	}[];
	correlated: {
		peer_code: string;
		name: string;
		sector: string;
		coefficient: number;
	}[];
	cluster: {
		community_id: number;
		members: { code: string; name: string; sector: string }[];
	} | null;
	signals: Signal[];
}

// ─── 年初来高値 ───────────────────────────────────────────────────────────────

export interface YtdHighStock {
	code: string;
	name: string;
	sector: string;
	close: number;
	ytd_high: number;
	gap_pct: number; // (close - ytd_high) / ytd_high * 100 (0=更新中, 負=以下)
}

// ─── Phase 20: 米国株価指数・為替 ────────────────────────────────────────────

export interface UsIndexBar {
	date: string;
	ticker: string;
	name: string;
	open: number;
	high: number;
	low: number;
	close: number;
	volume: number;
	change_pct: number | null;
}

export interface UsIndexSummary {
	ticker: string;
	name: string;
	date: string;
	close: number;
	change_pct: number | null;
	ytd_return_pct: number | null;
}

export interface ForexBar {
	date: string;
	pair: string;
	open: number;
	high: number;
	low: number;
	close: number;
	change_rate: number | null;
	ma20: number | null;
}

// ─── Phase 23b: 米国セクター ETF ─────────────────────────────────────────────

export interface UsSectorPerformanceItem {
	ticker: string;
	name: string;
	sector: string;
	close: number;
	change_pct: number | null;
	volume: number | null;
}

export interface UsSectorPerformance {
	date: string | null;
	period: string;
	sectors: UsSectorPerformanceItem[];
}

export interface UsSectorHeatmapSector {
	ticker: string;
	sector: string;
	values: (number | null)[];
}

export interface UsSectorHeatmap {
	periods: string[];
	sectors: UsSectorHeatmapSector[];
}

// ─── Phase 22: TD Sequential ─────────────────────────────────────────────────

export interface TdSequentialBar {
	date: string;
	setup_bull: number; // 0-9 (0 = inactive)
	setup_bear: number; // 0-9 (0 = inactive)
	countdown_bull: number; // 0-13 (0 = inactive)
	countdown_bear: number; // 0-13 (0 = inactive)
}

// ─── Phase 25: 投資主体別フロー ──────────────────────────────────────────────

export interface InvestorFlowWeekly {
	week_start: string;
	week_end: string;
	investor_type: string;
	sales: number;
	purchases: number;
	balance: number;
}

export interface InvestorFlowIndicator {
	week_end: string;
	foreigners_net: number;
	individuals_net: number;
	foreigners_4w_ma: number | null;
	individuals_4w_ma: number | null;
	foreigners_momentum: number | null;
	individuals_momentum: number | null;
	divergence_score: number | null;
	nikkei_return_4w: number | null;
	flow_regime: string | null;
}

export interface InvestorFlowSignal {
	type: string;
	direction: string;
	confidence: number;
}

export interface InvestorFlowLatest {
	week_end: string;
	flows: {
		foreigners: { sales: number; purchases: number; balance: number };
		individuals: { sales: number; purchases: number; balance: number };
	};
	indicators: {
		divergence_score: number | null;
		flow_regime: string | null;
		foreigners_4w_ma: number | null;
		individuals_4w_ma: number | null;
	};
	signal: InvestorFlowSignal | null;
}

// ─── Phase 26: コモディティ ──────────────────────────────────────────────────

export interface CommodityBar {
	date: string;
	symbol: string;
	name: string;
	open: number | null;
	high: number | null;
	low: number | null;
	close: number;
	volume: number | null;
	change_pct: number | null;
}

export interface CommoditySummary {
	symbol: string;
	name: string;
	label: string;
	date: string;
	close: number;
	change_pct: number | null;
}

// ─── Phase 27: スーパーサイクル分析 ──────────────────────────────────────────

export interface SupercyclePhase {
	name: string;
	name_en: string;
	color: string;
}

export interface SupercycleCommodity {
	ticker: string;
	label: string;
	close: number | null;
	date: string | null;
	change_pct: number | null;
	phase: number;
	position: number;
	is_etf: boolean;
}

export interface SupercycleSector {
	id: string;
	label: string;
	phase: number;
	position: number;
	commodities: SupercycleCommodity[];
}

export interface SupercycleScenario {
	id: string;
	name: string;
	probability: number;
	peak: string;
	description: string;
}

export interface SupercycleCorrelation {
	from_sector: string;
	to_sector: string;
	description: string;
}

export interface SupercycleOverview {
	phases: Record<string, SupercyclePhase>;
	sectors: SupercycleSector[];
	scenarios: SupercycleScenario[];
	correlations: SupercycleCorrelation[];
	updated: string;
}

export interface SupercycleSectorReturnPoint {
	date: string;
	value: number;
}

export interface SupercycleSectorReturnSeries {
	ticker: string;
	label: string;
	is_etf: boolean;
	data: SupercycleSectorReturnPoint[];
}

export interface SupercycleSectorReturns {
	sector: string;
	label: string;
	base_date: string | null;
	series: SupercycleSectorReturnSeries[];
}

export interface SupercyclePerformanceItem {
	ticker: string;
	label: string;
	sector_id: string;
	sector_label: string;
	is_etf: boolean;
	latest_close: number | null;
	latest_date: string | null;
	returns: Record<string, number | null>;
}
