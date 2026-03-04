<template>
  <div class="relative">
    <Line :data="chartData" :options="chartOptions" :plugins="allPlugins" />
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
	tdData?: TdSequentialBar[];
}>();

// date → TdSequentialBar ルックアップマップ
const tdMap = computed<Map<string, TdSequentialBar>>(() => {
	const m = new Map<string, TdSequentialBar>();
	if (props.tdData) {
		for (const bar of props.tdData) m.set(bar.date, bar);
	}
	return m;
});

// y 軸スケール用に高値・安値の透明データセット
const chartData = computed(() => ({
	labels: props.prices.map((p) => p.date),
	datasets: [
		{
			// 高値: y 軸上限を確保
			data: props.prices.map((p) => p.high),
			borderColor: "transparent",
			backgroundColor: "transparent",
			pointRadius: 0,
			borderWidth: 0,
		},
		{
			// 安値: y 軸下限を確保
			data: props.prices.map((p) => p.low),
			borderColor: "transparent",
			backgroundColor: "transparent",
			pointRadius: 0,
			borderWidth: 0,
		},
	],
}));

const chartOptions = computed(() => ({
	responsive: true,
	maintainAspectRatio: false,
	layout: {
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
				label: (ctx: { dataIndex: number }) => {
					const p = props.prices[ctx.dataIndex];
					if (!p || ctx.dataIndex !== 0) return undefined;
					return [
						`始値: ¥${p.open?.toLocaleString()}`,
						`高値: ¥${p.high?.toLocaleString()}`,
						`安値: ¥${p.low?.toLocaleString()}`,
						`終値: ¥${p.close?.toLocaleString()}`,
					];
				},
				title: (items: { label: string }[]) => items[0]?.label ?? "",
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

// ── ローソク足描画プラグイン ───────────────────────────────────────────────────

// biome-ignore lint/suspicious/noExplicitAny: Chart.js plugin pattern
const candlestickPlugin: any = {
	id: "nkflowCandlestick",
	// biome-ignore lint/suspicious/noExplicitAny: Chart.js plugin pattern
	afterDatasetsDraw(chart: any) {
		const { ctx, chartArea, scales } = chart;
		if (!chartArea) return;

		const labels: string[] = chart.data.labels ?? [];
		const totalBars = labels.length;
		if (totalBars === 0) return;

		// バー幅を計算 (隣接 2 点のピクセル間隔の 60%)
		const barWidth = totalBars > 1
			? Math.max(1, (scales.x.getPixelForValue(1) - scales.x.getPixelForValue(0)) * 0.6)
			: 4;

		ctx.save();

		labels.forEach((date: string, idx: number) => {
			const p = props.prices[idx];
			if (!p) return;

			const x = scales.x.getPixelForValue(idx);
			const yOpen  = scales.y.getPixelForValue(p.open);
			const yHigh  = scales.y.getPixelForValue(p.high);
			const yLow   = scales.y.getPixelForValue(p.low);
			const yClose = scales.y.getPixelForValue(p.close);

			const isUp = p.close >= p.open;
			const color = isUp ? "#16a34a" : "#dc2626";

			// ヒゲ (high-low 線)
			ctx.strokeStyle = color;
			ctx.lineWidth = 1;
			ctx.beginPath();
			ctx.moveTo(x, yHigh);
			ctx.lineTo(x, yLow);
			ctx.stroke();

			// 実体 (open-close 矩形)
			const bodyTop    = Math.min(yOpen, yClose);
			const bodyHeight = Math.max(1, Math.abs(yOpen - yClose));
			if (isUp) {
				ctx.strokeStyle = color;
				ctx.strokeRect(x - barWidth / 2, bodyTop, barWidth, bodyHeight);
			} else {
				ctx.fillStyle = color;
				ctx.fillRect(x - barWidth / 2, bodyTop, barWidth, bodyHeight);
			}
		});

		ctx.restore();
	},
};

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

			if (bar.setup_bull > 0 || bar.countdown_bull > 0) {
				const label = bar.countdown_bull > 0
					? String(bar.countdown_bull)
					: String(bar.setup_bull);
				ctx.fillStyle = bar.countdown_bull > 0 ? "#059669" : "#16a34a";
				ctx.textBaseline = "top";
				ctx.fillText(label, x, chartArea.bottom + 4);
			}

			if (bar.setup_bear > 0 || bar.countdown_bear > 0) {
				const label = bar.countdown_bear > 0
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

const allPlugins = computed(() => {
	const plugins = [candlestickPlugin];
	if (props.tdData?.length) plugins.push(tdAnnotationPlugin);
	return plugins;
});
</script>
