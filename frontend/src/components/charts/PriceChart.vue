<template>
  <div ref="chartContainer" class="w-full h-full" />
</template>

<script setup lang="ts">
import {
	type CandlestickData,
	CandlestickSeries,
	ColorType,
	createChart,
	createSeriesMarkers,
	type IChartApi,
	type ISeriesApi,
	type SeriesMarker,
	type Time,
} from "lightweight-charts";
import { onBeforeUnmount, onMounted, ref, watch } from "vue";
import type { DailyPrice, TdSequentialBar } from "../../types";

const props = defineProps<{
	prices: DailyPrice[];
	tdData?: TdSequentialBar[];
	visibleDays?: number; // 表示する営業日数 (省略時は全データ表示)
}>();

const chartContainer = ref<HTMLDivElement>();
let chart: IChartApi | null = null;
let candleSeries: ISeriesApi<"Candlestick"> | null = null;
// biome-ignore lint/suspicious/noExplicitAny: lightweight-charts markers primitive
let markersPrimitive: any = null;
let resizeObserver: ResizeObserver | null = null;

const MAX_VISIBLE_BARS = 250; // スクロールズームの最大表示バー数 (約1年)
const MIN_VISIBLE_BARS = 5;

// ── DailyPrice → CandlestickData 変換 ──────────────────────────────────────
function toCandlestickData(prices: DailyPrice[]): CandlestickData[] {
	return prices.map((p) => ({
		time: p.date as Time,
		open: p.open,
		high: p.high,
		low: p.low,
		close: p.close,
	}));
}

// ── TD Sequential → SeriesMarker 変換 ──────────────────────────────────────
// 色の凡例:
//   緑 (#16a34a) = 強気セットアップ (Setup 1-9、ローソク足の下)
//   水色 (#0284c7) = 強気カウントダウン (CD 1-13、ローソク足の下)
//   赤 (#dc2626) = 弱気セットアップ (Setup 1-9、ローソク足の上)
//   紫 (#9333ea) = 弱気カウントダウン (CD 1-13、ローソク足の上)
function toTdMarkers(
	prices: DailyPrice[],
	tdData?: TdSequentialBar[],
): SeriesMarker<Time>[] {
	if (!tdData?.length) return [];

	const tdMap = new Map<string, TdSequentialBar>();
	for (const bar of tdData) tdMap.set(bar.date, bar);

	const markers: SeriesMarker<Time>[] = [];

	for (const p of prices) {
		const bar = tdMap.get(p.date);
		if (!bar) continue;

		// 強気セットアップ (below bar, green) — カウントダウンと同時表示可
		if (bar.setup_bull > 0) {
			markers.push({
				time: p.date as Time,
				position: "belowBar",
				color: "#16a34a",
				shape: "circle",
				text: String(bar.setup_bull),
				size: 0,
			});
		}

		// 強気カウントダウン (below bar, sky blue) — セットアップと色で区別
		if (bar.countdown_bull > 0) {
			markers.push({
				time: p.date as Time,
				position: "belowBar",
				color: "#0284c7",
				shape: "circle",
				text: String(bar.countdown_bull),
				size: 0,
			});
		}

		// 弱気セットアップ (above bar, red) — カウントダウンと同時表示可
		if (bar.setup_bear > 0) {
			markers.push({
				time: p.date as Time,
				position: "aboveBar",
				color: "#dc2626",
				shape: "circle",
				text: String(bar.setup_bear),
				size: 0,
			});
		}

		// 弱気カウントダウン (above bar, purple) — セットアップと色で区別
		if (bar.countdown_bear > 0) {
			markers.push({
				time: p.date as Time,
				position: "aboveBar",
				color: "#9333ea",
				shape: "circle",
				text: String(bar.countdown_bear),
				size: 0,
			});
		}
	}

	return markers;
}

// ── visibleDays に基づいてタイムスケールを設定 ──────────────────────────────
function applyVisibleDays(days: number) {
	if (!chart || !props.prices.length) return;
	const to = props.prices.length - 1;
	const from = Math.max(0, to - days);
	chart.timeScale().setVisibleLogicalRange({ from, to });
}

// ── マウスホイールズームハンドラ ────────────────────────────────────────────
function handleWheel(event: WheelEvent) {
	if (!chart) return;
	event.preventDefault();

	const logRange = chart.timeScale().getVisibleLogicalRange();
	if (!logRange) return;

	const { from, to } = logRange;
	const currentSize = to - from;

	// scroll down (deltaY > 0) = ズームアウト、scroll up = ズームイン
	const factor = event.deltaY > 0 ? 1.15 : 1 / 1.15;
	const maxBars = Math.min(MAX_VISIBLE_BARS, props.prices.length);
	const newSize = Math.max(
		MIN_VISIBLE_BARS,
		Math.min(maxBars, currentSize * factor),
	);

	// 右端 (最新日) を固定してズーム
	chart.timeScale().setVisibleLogicalRange({ from: to - newSize, to });
}

// ── チャート初期化 ─────────────────────────────────────────────────────────
function initChart() {
	if (!chartContainer.value) return;

	const rect = chartContainer.value.getBoundingClientRect();

	chart = createChart(chartContainer.value, {
		width: rect.width,
		height: rect.height,
		layout: {
			textColor: "#374151",
			background: { type: ColorType.Solid, color: "#ffffff" },
			fontFamily: "system-ui, sans-serif",
			fontSize: 11,
			attributionLogo: false,
		},
		grid: {
			vertLines: { color: "#f3f4f6", style: 1 },
			horzLines: { color: "#f3f4f6", style: 1 },
		},
		crosshair: {
			mode: 0,
			vertLine: {
				width: 1,
				color: "rgba(107, 114, 128, 0.4)",
				labelBackgroundColor: "#374151",
			},
			horzLine: {
				width: 1,
				color: "rgba(107, 114, 128, 0.4)",
				labelBackgroundColor: "#374151",
			},
		},
		rightPriceScale: {
			borderColor: "#e5e7eb",
			autoScale: true,
			scaleMargins: { top: 0.1, bottom: 0.1 },
		},
		timeScale: {
			borderColor: "#e5e7eb",
			timeVisible: false,
			fixLeftEdge: true,
			fixRightEdge: true,
		},
		// マウスホイールはカスタムハンドラで処理するため無効化
		handleScroll: {
			mouseWheel: false,
			pressedMouseMove: true,
			horzTouchDrag: true,
			vertTouchDrag: false,
		},
		handleScale: {
			mouseWheel: false,
			pinch: true,
			axisDoubleClickReset: true,
		},
	});

	candleSeries = chart.addSeries(CandlestickSeries, {
		upColor: "#22c55e",
		downColor: "#ef4444",
		wickUpColor: "#16a34a",
		wickDownColor: "#dc2626",
		borderVisible: false,
	});

	updateData();

	// カスタムホイールズームリスナー
	chartContainer.value.addEventListener("wheel", handleWheel, {
		passive: false,
	});

	// コンテナサイズ追従
	resizeObserver = new ResizeObserver((entries) => {
		if (!chart || !entries.length) return;
		const { width, height } = entries[0].contentRect;
		if (width > 0 && height > 0) {
			chart.resize(width, height);
		}
	});
	resizeObserver.observe(chartContainer.value);
}

// ── データ更新 ─────────────────────────────────────────────────────────────
function updateData() {
	if (!candleSeries || !props.prices.length) return;

	candleSeries.setData(toCandlestickData(props.prices));

	// TD Sequential マーカー
	const markers = toTdMarkers(props.prices, props.tdData);
	if (markersPrimitive) {
		markersPrimitive.setMarkers(markers);
	} else if (markers.length > 0) {
		markersPrimitive = createSeriesMarkers(candleSeries, markers);
	}

	chart?.timeScale().fitContent();

	// visibleDays が指定されていれば表示範囲を上書き
	if (props.visibleDays) {
		applyVisibleDays(props.visibleDays);
	}
}

// ── ライフサイクル ─────────────────────────────────────────────────────────
onMounted(() => {
	initChart();
});

watch(
	() => [props.prices, props.tdData],
	() => {
		updateData();
	},
	{ deep: true },
);

watch(
	() => props.visibleDays,
	(days) => {
		if (days) applyVisibleDays(days);
	},
);

onBeforeUnmount(() => {
	if (chartContainer.value) {
		chartContainer.value.removeEventListener("wheel", handleWheel);
	}
	if (resizeObserver) {
		resizeObserver.disconnect();
		resizeObserver = null;
	}
	if (chart) {
		chart.remove();
		chart = null;
		candleSeries = null;
		markersPrimitive = null;
	}
});
</script>
