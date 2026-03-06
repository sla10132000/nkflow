<template>
  <div class="w-full">
    <!-- 凡例: ゾーン背景 (MarketPressureTimeline と統一) -->
    <div v-if="activeZones.length" class="flex flex-wrap gap-x-3 gap-y-1 mb-1 px-1 text-xs text-gray-400">
      <span>背景:</span>
      <span v-for="z in activeZones" :key="z" class="flex items-center gap-1">
        <span class="inline-block w-3 h-3 rounded-sm border border-gray-200"
              :style="{ background: ZONE_BG[z] ?? 'transparent' }" />{{ ZONE_LABEL[z] ?? z }}
      </span>
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

// MarketPressureTimeline と同一のゾーン色設定
const ZONE_BG: Record<string, string> = {
	ceiling: "rgba(220,38,38,0.15)",
	overheat: "rgba(202,138,4,0.12)",
	neutral: "rgba(22,163,74,0.08)",
	weak: "rgba(59,130,246,0.18)",
	bottom: "rgba(30,58,95,0.12)",
};

const ZONE_LABEL: Record<string, string> = {
	ceiling: "天井",
	overheat: "過熱",
	neutral: "中立",
	weak: "弱気",
	bottom: "底",
};

// 乖離スコアからゾーンを計算
function computeZone(score: number | null | undefined): string {
	if (score == null) return "neutral";
	if (score > 0.5) return "ceiling";
	if (score > 0.2) return "overheat";
	if (score < -0.5) return "bottom";
	if (score < -0.2) return "weak";
	return "neutral";
}

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

// 現在表示中ゾーン一覧 (凡例表示用)
const activeZones = computed(() => {
	const zones = slicedIndicators.value.map((d) => computeZone(d.divergence_score));
	return [...new Set(zones)].sort(
		(a, b) => Object.keys(ZONE_BG).indexOf(a) - Object.keys(ZONE_BG).indexOf(b),
	);
});

/** 縦色帯ゾーン + 閾値ライン プラグイン (MarketPressureTimeline と同方式) */
const zoneBgPlugin = {
	id: "investorFlowZone",
	beforeDraw(chart: Chart) {
		// eslint-disable-next-line @typescript-eslint/no-explicit-any
		const { ctx, chartArea, scales, data } = chart as any;
		const y2 = scales?.y2;
		if (!y2 || !chartArea) return;

		const n: number = data.labels?.length ?? 0;
		if (!n) return;

		const bw = (chartArea.right - chartArea.left) / n;
		const { top, bottom, left } = chartArea;

		ctx.save();

		// 各時点を縦帯で塗る (MarketPressureTimeline と同方式)
		slicedIndicators.value.forEach((d, i) => {
			const zone = computeZone(d.divergence_score);
			ctx.fillStyle = ZONE_BG[zone] ?? "rgba(107,114,128,0.05)";
			ctx.fillRect(left + i * bw, top, bw, bottom - top);
		});

		// 閾値ライン: ±0.5, ±0.2 (MarketPressureTimeline の閾値ラインと同方式)
		const thresholds = [
			{ val: 0.5, color: "rgba(220,38,38,0.55)", label: "+0.5" },
			{ val: 0.2, color: "rgba(202,138,4,0.55)", label: "+0.2" },
			{ val: 0, color: "rgba(107,114,128,0.4)", label: "0" },
			{ val: -0.2, color: "rgba(59,130,246,0.55)", label: "−0.2" },
			{ val: -0.5, color: "rgba(29,78,216,0.55)", label: "−0.5" },
		];

		thresholds.forEach(({ val, color, label }) => {
			const y: number = y2.getPixelForValue(val);
			if (y < top || y > bottom) return;
			ctx.strokeStyle = color;
			ctx.lineWidth = 1;
			ctx.setLineDash(val === 0 ? [5, 3] : [4, 3]);
			ctx.beginPath();
			ctx.moveTo(chartArea.left, y);
			ctx.lineTo(chartArea.right, y);
			ctx.stroke();
			ctx.setLineDash([]);
			ctx.fillStyle = color;
			ctx.font = "9px sans-serif";
			ctx.textAlign = "right";
			ctx.fillText(label, chartArea.right - 2, y - 2);
		});

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
