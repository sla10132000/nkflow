<template>
  <div class="w-full">
    <!-- 凡例補足 (MarketPressureTimeline と色統一: 弱気=青 / 中立=灰 / 過熱=琥珀) -->
    <div class="flex items-center gap-3 text-xs text-gray-500 mb-1 px-1">
      <span class="inline-block w-3 h-2 rounded-sm" style="background:rgba(59,130,246,0.18);" />
      <span>弱気域 (スコア &lt; 0)</span>
      <span class="inline-block w-3 h-2 rounded-sm" style="background:rgba(202,138,4,0.15);" />
      <span>過熱域 (スコア &gt; 0)</span>
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
			label: "乖離スコア (↑過熱 / ↓弱気)",
			data: slicedIndicators.value.map((d) => d.divergence_score),
			borderColor: "rgba(107,114,128,0.8)",
			backgroundColor: "transparent",
			borderWidth: 2,
			pointRadius: 4,
			pointBackgroundColor: slicedIndicators.value.map((d) => {
				const s = d.divergence_score;
				if (s === null || s === undefined) return "rgba(107,114,128,0.9)";
				if (s > 0.2) return "rgba(202,138,4,0.9)";   // 過熱 = 琥珀 (MarketPressureTimeline と統一)
				if (s < -0.2) return "rgba(59,130,246,0.9)"; // 弱気 = 青 (MarketPressureTimeline と統一)
				return "rgba(156,163,175,0.9)";               // 中立 = グレー
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
								? " [過熱]"
								: val < -0.3
									? " [弱気]"
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
					if (val === 1) return "+1 過熱";
					if (val === -1) return "-1 弱気";
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

		// 正領域 (スコア > 0 = 過熱): 薄琥珀 (MarketPressureTimeline の過熱ゾーンと統一)
		const amberTop = Math.max(top, Math.min(zeroY, bottom));
		if (amberTop > top) {
			ctx.fillStyle = "rgba(202,138,4,0.08)";
			ctx.fillRect(left, top, width, amberTop - top);
		}

		// 負領域 (スコア < 0 = 弱気): 薄青 (MarketPressureTimeline の弱気ゾーンと統一)
		const blueBottom = Math.min(bottom, Math.max(zeroY, top));
		if (blueBottom < bottom) {
			ctx.fillStyle = "rgba(59,130,246,0.08)";
			ctx.fillRect(left, blueBottom, width, bottom - blueBottom);
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
