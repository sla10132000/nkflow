<template>
  <div ref="chartContainer" class="w-full" style="height: 160px" />
</template>

<script setup lang="ts">
import {
	AreaSeries,
	ColorType,
	createChart,
	type IChartApi,
	type ISeriesApi,
	type Time,
} from "lightweight-charts";
import { onBeforeUnmount, onMounted, ref, watch } from "vue";

interface DataPoint {
	date: string;
	close: number;
}

const props = defineProps<{ data: DataPoint[] }>();

const chartContainer = ref<HTMLDivElement>();
let chart: IChartApi | null = null;
let areaSeries: ISeriesApi<"Area"> | null = null;
let resizeObserver: ResizeObserver | null = null;

function isUp(): boolean {
	if (props.data.length < 2) return true;
	return props.data[props.data.length - 1].close >= props.data[0].close;
}

function initChart() {
	if (!chartContainer.value) return;
	const rect = chartContainer.value.getBoundingClientRect();

	chart = createChart(chartContainer.value, {
		width: rect.width,
		height: 160,
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

	const up = isUp();
	areaSeries = chart.addSeries(AreaSeries, {
		lineColor: up ? "#16a34a" : "#dc2626",
		topColor: up ? "rgba(22,163,74,0.2)" : "rgba(220,38,38,0.2)",
		bottomColor: up ? "rgba(22,163,74,0.0)" : "rgba(220,38,38,0.0)",
		lineWidth: 2,
	});

	updateData();

	resizeObserver = new ResizeObserver((entries) => {
		if (!chart || !entries.length) return;
		const { width, height } = entries[0].contentRect;
		if (width > 0 && height > 0) {
			chart.resize(width, height);
		}
	});
	resizeObserver.observe(chartContainer.value);
}

function updateData() {
	if (!areaSeries || !props.data.length) return;
	areaSeries.setData(
		props.data.map((d) => ({ time: d.date as Time, value: d.close })),
	);
	chart?.timeScale().fitContent();
}

onMounted(() => {
	initChart();
});

watch(
	() => props.data,
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
		areaSeries = null;
	}
});
</script>
