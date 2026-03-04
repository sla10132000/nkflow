<template>
  <div class="relative">
    <Line :data="chartData" :options="chartOptions" :plugins="tdPlugins" />
  </div>
</template>

<script setup lang="ts">
import {
	CategoryScale,
	Chart as ChartJS,
	Filler,
	Legend,
	LinearScale,
	LineElement,
	PointElement,
	Title,
	Tooltip,
} from "chart.js";
import { computed } from "vue";
import { Line } from "vue-chartjs";
import type { DailyPrice, TdSequentialBar } from "../../types";

ChartJS.register(
	CategoryScale,
	LinearScale,
	PointElement,
	LineElement,
	Title,
	Tooltip,
	Legend,
	Filler,
);

const props = defineProps<{
	prices: DailyPrice[];
	tdData?: TdSequentialBar[]; // Phase 22: optional TD Sequential overlay
}>();

// date → TdSequentialBar ルックアップマップ
const tdMap = computed<Map<string, TdSequentialBar>>(() => {
	const m = new Map<string, TdSequentialBar>();
	if (props.tdData) {
		for (const bar of props.tdData) {
			m.set(bar.date, bar);
		}
	}
	return m;
});

const chartData = computed(() => ({
	labels: props.prices.map((p) => p.date),
	datasets: [
		{
			label: "終値",
			data: props.prices.map((p) => p.close),
			borderColor: "#3b82f6",
			backgroundColor: "rgba(59,130,246,0.08)",
			borderWidth: 1.5,
			pointRadius: 0,
			fill: true,
			tension: 0.1,
		},
	],
}));

const chartOptions = computed(() => ({
	responsive: true,
	maintainAspectRatio: false,
	layout: {
		// TD Sequential 数値の描画領域を確保
		padding: {
			top: props.tdData?.length ? 16 : 0,
			bottom: props.tdData?.length ? 20 : 0,
		},
	},
	plugins: {
		legend: { display: false },
		tooltip: {
			mode: "index" as const,
			intersect: false,
			callbacks: {
				label: (ctx: { parsed: { y: number | null } }) =>
					ctx.parsed.y != null ? `¥${ctx.parsed.y.toLocaleString()}` : "",
			},
		},
	},
	scales: {
		x: {
			ticks: { color: "#6b7280", maxTicksLimit: 8 },
			grid: { color: "#e5e7eb" },
		},
		y: {
			ticks: { color: "#6b7280" },
			grid: { color: "#e5e7eb" },
		},
	},
}));

// ── TD Sequential annotation plugin ──────────────────────────────────────────

// biome-ignore lint/suspicious/noExplicitAny: Chart.js plugin pattern
const tdAnnotationPlugin: any = {
	id: "nkflowTdSequential",
	// biome-ignore lint/suspicious/noExplicitAny: Chart.js plugin pattern
	afterDraw(chart: any) {
		if (!props.tdData?.length) return;

		const { ctx, chartArea, scales } = chart;
		if (!chartArea) return;

		const labels: string[] = chart.data.labels ?? [];
		const map = tdMap.value;

		ctx.save();
		ctx.font = "bold 9px monospace";
		ctx.textAlign = "center";

		labels.forEach((dateLabel: string, idx: number) => {
			const bar = map.get(dateLabel);
			if (!bar) return;

			const x = scales.x.getPixelForValue(idx);

			// 強気: setup_bull または countdown_bull が有効 → 緑でチャート下部に表示
			if (bar.setup_bull > 0 || bar.countdown_bull > 0) {
				const label =
					bar.countdown_bull > 0
						? String(bar.countdown_bull) // Countdown を優先表示
						: String(bar.setup_bull);
				ctx.fillStyle = bar.countdown_bull > 0 ? "#059669" : "#16a34a";
				ctx.textBaseline = "top";
				ctx.fillText(label, x, chartArea.bottom + 4);
			}

			// 弱気: setup_bear または countdown_bear が有効 → 赤でチャート上部に表示
			if (bar.setup_bear > 0 || bar.countdown_bear > 0) {
				const label =
					bar.countdown_bear > 0
						? String(bar.countdown_bear)
						: String(bar.setup_bear);
				ctx.fillStyle = bar.countdown_bear > 0 ? "#b91c1c" : "#dc2626";
				ctx.textBaseline = "bottom";
				ctx.fillText(label, x, chartArea.top - 2);
			}
		});

		ctx.restore();
	},
};

const tdPlugins = computed(() =>
	props.tdData?.length ? [tdAnnotationPlugin] : [],
);
</script>
