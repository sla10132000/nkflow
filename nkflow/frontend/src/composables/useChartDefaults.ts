/**
 * Chart.js 共通設定 — プラグイン登録・スケール・凡例ビルダー
 *
 * 各チャートコンポーネントで散在していた ChartJS.register() と
 * 共通オプション定義をここに集約する。
 */

import {
	BarElement,
	CategoryScale,
	Chart,
	Filler,
	Legend,
	LinearScale,
	LineElement,
	PointElement,
	Title,
	Tooltip,
} from "chart.js";

// ── Plugin Registration ───────────────────────────────────────────────────────

let registered = false;

/**
 * Chart.js プラグインを一度だけ登録する。
 * 各チャートコンポーネントの先頭で ChartJS.register(...) を呼ぶ代わりに
 * この関数を呼び出す。
 */
export function registerChartPlugins(): void {
	if (registered) return;
	Chart.register(
		CategoryScale,
		LinearScale,
		BarElement,
		LineElement,
		PointElement,
		Title,
		Tooltip,
		Legend,
		Filler,
	);
	registered = true;
}

// ── Common Style Constants ────────────────────────────────────────────────────

const TICK_COLOR = "#6b7280";
const GRID_COLOR = "#e5e7eb";
const TICK_FONT_SIZE = 10;

// ── Scale Builders ────────────────────────────────────────────────────────────

export interface AxisOverrides {
	ticks?: Record<string, unknown>;
	grid?: Record<string, unknown>;
	[key: string]: unknown;
}

/** 共通の X 軸スケール設定を返す。overrides でカスタマイズ可能。 */
export function baseXScale(overrides: AxisOverrides = {}): Record<string, unknown> {
	const { ticks: ticksOverride, grid: gridOverride, ...rest } = overrides;
	return {
		ticks: { color: TICK_COLOR, font: { size: TICK_FONT_SIZE }, ...ticksOverride },
		grid: { color: GRID_COLOR, ...gridOverride },
		...rest,
	};
}

/** 共通の Y 軸スケール設定を返す。overrides でカスタマイズ可能。 */
export function baseYScale(overrides: AxisOverrides = {}): Record<string, unknown> {
	const { ticks: ticksOverride, grid: gridOverride, ...rest } = overrides;
	return {
		ticks: { color: TICK_COLOR, font: { size: TICK_FONT_SIZE }, ...ticksOverride },
		grid: { color: GRID_COLOR, ...gridOverride },
		...rest,
	};
}

/** legend: display=true, position=bottom の共通設定を返す。 */
export function baseLegendBottom(): Record<string, unknown> {
	return {
		display: true,
		position: "bottom" as const,
		labels: { color: TICK_COLOR, boxWidth: 10, font: { size: TICK_FONT_SIZE } },
	};
}
