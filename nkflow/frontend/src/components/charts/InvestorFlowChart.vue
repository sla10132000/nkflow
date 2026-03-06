<template>
  <div class="w-full">
    <canvas ref="canvasRef" :height="220" />
  </div>
</template>

<script setup lang="ts">
import {
	BarElement,
	CategoryScale,
	Chart,
	type ChartData,
	type ChartOptions,
	Legend,
	LinearScale,
	LineElement,
	PointElement,
	Tooltip,
} from "chart.js";
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import type { InvestorFlowIndicator } from "../../types";

Chart.register(
	CategoryScale,
	LinearScale,
	BarElement,
	LineElement,
	PointElement,
	Tooltip,
	Legend,
);

const props = withDefaults(
	defineProps<{
		indicators: InvestorFlowIndicator[];
		weeks?: number;
	}>(),
	{ weeks: 13 },
);

const canvasRef = ref<HTMLCanvasElement | null>(null);
let chartInstance: Chart | null = null;

const slicedIndicators = computed(() => props.indicators.slice(-props.weeks));

const labels = computed(
	() => slicedIndicators.value.map((d) => d.week_end.slice(5)), // MM-DD
);

// 海外差引の棒グラフ色 (正=青, 負=赤紫)
function foreignerBarColors(indicators: InvestorFlowIndicator[]) {
	return indicators.map((d) =>
		d.foreigners_net >= 0 ? "rgba(59,130,246,0.75)" : "rgba(139,92,246,0.75)",
	);
}

// 個人差引の棒グラフ色 (正=橙, 負=灰)
function individualBarColors(indicators: InvestorFlowIndicator[]) {
	return indicators.map((d) =>
		d.individuals_net >= 0 ? "rgba(251,146,60,0.75)" : "rgba(156,163,175,0.75)",
	);
}

const chartData = computed<ChartData>(() => ({
	labels: labels.value,
	datasets: [
		{
			type: "bar" as const,
			label: "海外差引 (億円)",
			data: slicedIndicators.value.map((d) =>
				Math.round(d.foreigners_net / 1e8),
			),
			backgroundColor: foreignerBarColors(slicedIndicators.value),
			yAxisID: "y",
			order: 2,
		},
		{
			type: "bar" as const,
			label: "個人差引 (億円)",
			data: slicedIndicators.value.map((d) =>
				Math.round(d.individuals_net / 1e8),
			),
			backgroundColor: individualBarColors(slicedIndicators.value),
			yAxisID: "y",
			order: 2,
		},
		{
			type: "line" as const,
			label: "乖離スコア",
			data: slicedIndicators.value.map((d) => d.divergence_score),
			borderColor: "rgba(34,197,94,0.9)",
			backgroundColor: "rgba(34,197,94,0.1)",
			borderWidth: 2,
			pointRadius: 3,
			pointBackgroundColor: "rgba(34,197,94,0.9)",
			yAxisID: "y2",
			order: 1,
			tension: 0.3,
		},
	],
}));

const chartOptions = computed<ChartOptions>(() => ({
	responsive: true,
	maintainAspectRatio: false,
	interaction: { mode: "index", intersect: false },
	plugins: {
		legend: {
			position: "top",
			labels: { font: { size: 11 }, boxWidth: 12, padding: 8 },
		},
		tooltip: {
			callbacks: {
				label(ctx) {
					const label = ctx.dataset.label ?? "";
					const val = ctx.parsed.y;
					if (ctx.datasetIndex === 2) {
						return `${label}: ${val != null ? val.toFixed(2) : "—"}`;
					}
					return `${label}: ${val != null ? val.toLocaleString() : "—"}`;
				},
			},
		},
	},
	scales: {
		x: {
			ticks: { font: { size: 10 }, maxRotation: 45 },
			grid: { color: "rgba(0,0,0,0.04)" },
		},
		y: {
			type: "linear",
			position: "left",
			ticks: { font: { size: 10 } },
			grid: { color: "rgba(0,0,0,0.06)" },
			title: { display: true, text: "億円", font: { size: 10 } },
		},
		y2: {
			type: "linear",
			position: "right",
			min: -1,
			max: 1,
			ticks: { font: { size: 10 }, stepSize: 0.5 },
			grid: { drawOnChartArea: false },
			title: { display: true, text: "スコア", font: { size: 10 } },
		},
	},
}));

function buildChart() {
	if (!canvasRef.value) return;
	if (chartInstance) {
		chartInstance.destroy();
		chartInstance = null;
	}
	chartInstance = new Chart(canvasRef.value, {
		type: "bar",
		data: chartData.value,
		options: chartOptions.value,
	});
}

function updateChart() {
	if (!chartInstance) {
		buildChart();
		return;
	}
	chartInstance.data = chartData.value;
	chartInstance.options = chartOptions.value;
	chartInstance.update();
}

onMounted(() => {
	buildChart();
});

watch(
	() => [props.indicators, props.weeks],
	() => {
		updateChart();
	},
);

onBeforeUnmount(() => {
	if (chartInstance) {
		chartInstance.destroy();
		chartInstance = null;
	}
});
</script>
