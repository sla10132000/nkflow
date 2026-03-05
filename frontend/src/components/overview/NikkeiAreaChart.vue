<template>
  <div ref="chartContainer" class="w-full" style="height: 160px" />
</template>

<script setup lang="ts">
import {
	CandlestickSeries,
	ColorType,
	createChart,
	type IChartApi,
	type ISeriesApi,
	type Time,
} from "lightweight-charts";
import { onBeforeUnmount, onMounted, ref } from "vue";
import { useApi } from "../../composables/useApi";

const api = useApi();
const chartContainer = ref<HTMLDivElement>();
let chart: IChartApi | null = null;
let candleSeries: ISeriesApi<"Candlestick"> | null = null;

function initChart() {
	if (!chartContainer.value) return;

	chart = createChart(chartContainer.value, {
		autoSize: true,
		layout: {
			textColor: "#6b7280",
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
				color: "rgba(107, 114, 128, 0.3)",
				labelBackgroundColor: "#374151",
			},
			horzLine: {
				width: 1,
				color: "rgba(107, 114, 128, 0.3)",
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
	});

	candleSeries = chart.addSeries(CandlestickSeries, {
		upColor: "#16a34a",
		downColor: "#dc2626",
		borderUpColor: "#16a34a",
		borderDownColor: "#dc2626",
		wickUpColor: "#16a34a",
		wickDownColor: "#dc2626",
	});

	loadData();
}

async function loadData() {
	try {
		const data = await api.getUsIndices("^N225", 60);
		if (!candleSeries || !data.length) return;
		candleSeries.setData(
			data
				.filter((d: { open: number | null; close: number | null }) => d.open != null && d.close != null)
				.map((d: { date: string; open: number; high: number; low: number; close: number }) => ({
					time: d.date as Time,
					open: d.open,
					high: d.high,
					low: d.low,
					close: d.close,
				})),
		);
		chart?.timeScale().fitContent();
	} catch (e) {
		console.error("Nikkei OHLC fetch failed", e);
	}
}

onMounted(() => {
	initChart();
});

onBeforeUnmount(() => {
	if (chart) {
		chart.remove();
		chart = null;
		candleSeries = null;
	}
});
</script>
