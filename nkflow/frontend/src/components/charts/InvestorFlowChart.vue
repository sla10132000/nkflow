<template>
  <div class="w-full">
    <!-- 凡例補足 -->
    <div class="flex items-center gap-3 text-xs text-gray-500 mb-1 px-1">
      <span class="inline-block w-3 h-2 rounded-sm" style="background:rgba(34,197,94,0.15);" />
      <span>底入れ域 (スコア &lt; 0)</span>
      <span class="inline-block w-3 h-2 rounded-sm" style="background:rgba(239,68,68,0.12);" />
      <span>天井警戒域 (スコア &gt; 0)</span>
    </div>
    <!-- responsive:true + maintainAspectRatio:false には親の固定高さが必要 -->
    <div style="position: relative; height: 220px;">
      <canvas ref="canvasRef" />
    </div>
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
			label: "乖離スコア (↑天井警戒 / ↓底入れ)",
			data: slicedIndicators.value.map((d) => d.divergence_score),
			borderColor: "rgba(34,197,94,1)",
			backgroundColor: "transparent",
			borderWidth: 2,
			pointRadius: 4,
			pointBackgroundColor: slicedIndicators.value.map((d) => {
				const s = d.divergence_score;
				if (s === null || s === undefined) return "rgba(34,197,94,0.9)";
				if (s > 0.2) return "rgba(239,68,68,0.9)";
				if (s < -0.2) return "rgba(34,197,94,0.9)";
				return "rgba(156,163,175,0.9)";
			}),
			pointBorderColor: "white",
			pointBorderWidth: 1,
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
						if (val === null || val === undefined) return `${label}: —`;
						const desc =
							val > 0.3
								? " [天井警戒]"
								: val < -0.3
									? " [底入れ]"
									: " [中立]";
						return `${label}: ${val.toFixed(2)}${desc}`;
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
			ticks: {
				font: { size: 10 },
				stepSize: 0.5,
				callback(val: string | number) {
					if (val === 1) return "+1 天井";
					if (val === -1) return "-1 底入れ";
					if (val === 0) return "0 中立";
					return typeof val === "number" ? val.toFixed(1) : val;
				},
			},
			grid: { drawOnChartArea: false },
			title: {
				display: true,
				text: "乖離スコア",
				font: { size: 10 },
			},
		},
	},
}));

// ゾーン背景 + ゼロライン強調プラグイン
const zoneBgPlugin = {
	id: "investorFlowZone",
	beforeDraw(chart: Chart) {
		// eslint-disable-next-line @typescript-eslint/no-explicit-any
		const { ctx, chartArea, scales } = chart as any;
		const y2 = scales?.y2;
		if (!y2 || !chartArea) return;

		const zeroY: number = y2.getPixelForValue(0);
		const { top, bottom, left, right } = chartArea;
		const width = right - left;

		ctx.save();

		// 正領域 (スコア > 0 = 天井警戒): 薄赤
		const redTop = Math.max(top, Math.min(zeroY, bottom));
		if (redTop > top) {
			ctx.fillStyle = "rgba(239,68,68,0.07)";
			ctx.fillRect(left, top, width, redTop - top);
		}

		// 負領域 (スコア < 0 = 底入れ): 薄緑
		const greenBottom = Math.min(bottom, Math.max(zeroY, top));
		if (greenBottom < bottom) {
			ctx.fillStyle = "rgba(34,197,94,0.07)";
			ctx.fillRect(left, greenBottom, width, bottom - greenBottom);
		}

		// ゼロライン (破線で強調)
		if (zeroY >= top && zeroY <= bottom) {
			ctx.strokeStyle = "rgba(107,114,128,0.5)";
			ctx.lineWidth = 1.5;
			ctx.setLineDash([5, 3]);
			ctx.beginPath();
			ctx.moveTo(left, zeroY);
			ctx.lineTo(right, zeroY);
			ctx.stroke();
			ctx.setLineDash([]);

			// ゼロラインラベル
			ctx.fillStyle = "rgba(107,114,128,0.7)";
			ctx.font = "9px sans-serif";
			ctx.textAlign = "left";
			ctx.fillText("0 (中立)", left + 4, zeroY - 3);
		}

		ctx.restore();
	},
};

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
		plugins: [zoneBgPlugin],
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
