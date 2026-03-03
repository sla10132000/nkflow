<template>
  <div>
    <div v-if="loading" class="flex items-center justify-center h-48 text-gray-500 text-sm">
      読み込み中...
    </div>
    <div v-else-if="!data || data.dates.length === 0"
         class="flex items-center justify-center h-48 text-gray-500 text-sm">
      データなし（信用残データは週次蓄積中）
    </div>
    <div v-else class="h-64 relative">
      <Line :data="chartData" :options="chartOptions" :plugins="chartPlugins" />
    </div>

    <!-- 凡例 -->
    <div class="flex gap-4 mt-2 text-xs text-gray-500">
      <span class="flex items-center gap-1">
        <span class="inline-block w-3 h-1 rounded" style="background:#60a5fa"></span>評価損益率
      </span>
      <span class="flex items-center gap-1">
        <span class="inline-block w-3 h-1 rounded border-dashed border border-amber-400"></span>買残増加率(4週)
      </span>
    </div>
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
import { computed, onMounted, ref, watch } from "vue";
import { useApi } from "../../composables/useApi";
import type { MarketPressureTimeseries } from "../../types";

ChartJS.register(
	CategoryScale,
	LinearScale,
	LineElement,
	PointElement,
	Title,
	Tooltip,
	Legend,
	Filler,
);

const props = defineProps<{ days?: number }>();

const api = useApi();
const loading = ref(false);
const data = ref<MarketPressureTimeseries | null>(null);

const ZONE_BG: Record<string, string> = {
	ceiling: "rgba(220,38,38,0.15)",
	overheat: "rgba(202,138,4,0.12)",
	neutral: "rgba(22,163,74,0.08)",
	weak: "rgba(5,95,70,0.08)",
	sellin: "rgba(29,78,216,0.10)",
	bottom: "rgba(30,58,95,0.12)",
};

const chartData = computed(() => {
	if (!data.value) return { labels: [], datasets: [] };
	const labels = data.value.dates.map((d) => d.slice(5)); // MM-DD
	return {
		labels,
		datasets: [
			{
				label: "評価損益率",
				data: data.value.pl_ratio,
				borderColor: "#60a5fa",
				backgroundColor: "#60a5fa22",
				borderWidth: 2,
				pointRadius: 4,
				pointHoverRadius: 6,
				tension: 0.3,
				spanGaps: true,
				yAxisID: "y",
			},
			{
				label: "買残増加率(4週)",
				data: data.value.buy_growth_4w,
				borderColor: "#f59e0b",
				backgroundColor: "transparent",
				borderWidth: 1.5,
				borderDash: [4, 3],
				pointRadius: 4,
				pointHoverRadius: 6,
				tension: 0.3,
				spanGaps: true,
				yAxisID: "y",
			},
		],
	};
});

const chartOptions = computed(() => ({
	responsive: true,
	maintainAspectRatio: false,
	plugins: {
		legend: { display: false },
		tooltip: {
			callbacks: {
				label: (ctx: {
					dataset: { label?: string };
					parsed: { y: number | null };
				}) => {
					const v = ctx.parsed.y;
					if (v == null) return `${ctx.dataset.label}: —`;
					return `${ctx.dataset.label}: ${(v * 100).toFixed(2)}%`;
				},
			},
		},
	},
	scales: {
		x: {
			ticks: { color: "#6b7280", font: { size: 9 }, maxTicksLimit: 10 },
			grid: { color: "#e5e7eb" },
		},
		y: {
			ticks: {
				color: "#6b7280",
				font: { size: 10 },
				callback: (v: string | number) => `${(Number(v) * 100).toFixed(0)}%`,
			},
			grid: { color: "#e5e7eb" },
		},
	},
}));

/** ゾーン背景色帯 plugin */
const zoneBgPlugin = {
	id: "nkflowPressureZoneBg",
	beforeDraw(chart: {
		ctx: CanvasRenderingContext2D;
		chartArea: {
			top: number;
			left: number;
			width: number;
			height: number;
		} | null;
	}) {
		const zones = data.value?.pl_zone;
		if (!zones?.length) return;
		const { ctx, chartArea } = chart;
		if (!chartArea) return;
		const bw = chartArea.width / zones.length;
		ctx.save();
		zones.forEach((zone, i) => {
			ctx.fillStyle = ZONE_BG[zone] ?? "rgba(107,114,128,0.05)";
			ctx.fillRect(
				chartArea.left + i * bw,
				chartArea.top,
				bw,
				chartArea.height,
			);
		});
		ctx.restore();
	},
};

/** 信用過熱警報 縦線 plugin */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const overheatingLinePlugin: any = {
	id: "nkflowCreditOverheating",
	// eslint-disable-next-line @typescript-eslint/no-explicit-any
	afterDraw(chart: any) {
		const flags = data.value?.signal_flags;
		if (!flags?.length) return;
		const { ctx, chartArea, scales } = chart;
		if (!chartArea) return;
		ctx.save();
		ctx.strokeStyle = "#ef4444";
		ctx.lineWidth = 1.5;
		ctx.setLineDash([3, 3]);
		flags.forEach((f: { credit_overheating?: boolean }, i: number) => {
			if (f.credit_overheating) {
				const x = scales.x.getPixelForValue(i);
				ctx.beginPath();
				ctx.moveTo(x, chartArea.top);
				ctx.lineTo(x, chartArea.top + chartArea.height);
				ctx.stroke();
			}
		});
		ctx.restore();
	},
};

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const chartPlugins: any[] = [zoneBgPlugin, overheatingLinePlugin];

async function load() {
	loading.value = true;
	try {
		data.value = await api.getMarketPressureTimeseries(props.days ?? 90);
	} finally {
		loading.value = false;
	}
}

onMounted(load);
watch(() => props.days, load);
</script>
