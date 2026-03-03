<template>
  <div class="relative">
    <Line :data="chartData" :options="chartOptions" />
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
import type { DailyPrice } from "../../types";

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

const props = defineProps<{ prices: DailyPrice[] }>();

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

const chartOptions = {
	responsive: true,
	maintainAspectRatio: false,
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
};
</script>
