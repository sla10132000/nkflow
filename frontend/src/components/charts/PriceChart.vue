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
}>();

const chartContainer = ref<HTMLDivElement>();
let chart: IChartApi | null = null;
let candleSeries: ISeriesApi<"Candlestick"> | null = null;
// biome-ignore lint/suspicious/noExplicitAny: lightweight-charts markers primitive
let markersPrimitive: any = null;
let resizeObserver: ResizeObserver | null = null;

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

		// Bullish (below bar) — countdown 優先
		if (bar.countdown_bull > 0) {
			markers.push({
				time: p.date as Time,
				position: "belowBar",
				color: "#059669",
				shape: "circle",
				text: String(bar.countdown_bull),
				size: 0,
			});
		} else if (bar.setup_bull > 0) {
			markers.push({
				time: p.date as Time,
				position: "belowBar",
				color: "#16a34a",
				shape: "circle",
				text: String(bar.setup_bull),
				size: 0,
			});
		}

		// Bearish (above bar) — countdown 優先
		if (bar.countdown_bear > 0) {
			markers.push({
				time: p.date as Time,
				position: "aboveBar",
				color: "#b91c1c",
				shape: "circle",
				text: String(bar.countdown_bear),
				size: 0,
			});
		} else if (bar.setup_bear > 0) {
			markers.push({
				time: p.date as Time,
				position: "aboveBar",
				color: "#dc2626",
				shape: "circle",
				text: String(bar.setup_bear),
				size: 0,
			});
		}
	}

	return markers;
}

// ── チャート初期化 ─────────────────────────────────────────────────────────
function initChart() {
	if (!chartContainer.value) return;

	const rect = chartContainer.value.getBoundingClientRect();

	chart = createChart(chartContainer.value, {
		width: rect.width,
		height: rect.height,
		layout: {
			textColor: "#9ca3af",
			background: { type: ColorType.Solid, color: "#131722" },
			fontFamily: "system-ui, sans-serif",
			fontSize: 11,
			attributionLogo: false,
		},
		grid: {
			vertLines: { color: "rgba(255,255,255,0.05)", style: 1 },
			horzLines: { color: "rgba(255,255,255,0.05)", style: 1 },
		},
		crosshair: {
			mode: 0,
			vertLine: {
				width: 1,
				color: "rgba(156, 163, 175, 0.4)",
				labelBackgroundColor: "#374151",
			},
			horzLine: {
				width: 1,
				color: "rgba(156, 163, 175, 0.4)",
				labelBackgroundColor: "#374151",
			},
		},
		rightPriceScale: {
			borderColor: "rgba(255,255,255,0.1)",
			autoScale: true,
			scaleMargins: { top: 0.1, bottom: 0.1 },
		},
		timeScale: {
			borderColor: "rgba(255,255,255,0.1)",
			timeVisible: false,
			fixLeftEdge: true,
			fixRightEdge: true,
		},
	});

	candleSeries = chart.addSeries(CandlestickSeries, {
		upColor: "#26a69a",
		downColor: "#ef5350",
		wickUpColor: "#26a69a",
		wickDownColor: "#ef5350",
		borderVisible: false,
	});

	updateData();

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

onBeforeUnmount(() => {
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
