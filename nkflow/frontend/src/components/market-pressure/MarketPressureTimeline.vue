<template>
  <div>
    <!-- 凡例: ライン (上部) -->
    <div class="flex gap-4 mb-1 text-xs text-gray-500">
      <span class="flex items-center gap-1">
        <span class="inline-block w-3 h-1 rounded" style="background:#60a5fa"></span>評価損益率
      </span>
      <span class="flex items-center gap-1">
        <span class="inline-block w-3 h-1 rounded border-dashed border border-amber-400"></span>買残増加率(4週)
      </span>
    </div>
    <!-- 凡例: 閾値ライン (上部) -->
    <div class="flex gap-3 mb-1 text-xs text-gray-400">
      <span>閾値:</span>
      <span class="flex items-center gap-1">
        <span class="inline-block w-3 h-0 border-t border-dashed" style="border-color:#dc2626"></span>+15% 天井
      </span>
      <span class="flex items-center gap-1">
        <span class="inline-block w-3 h-0 border-t border-dashed" style="border-color:#ca8a04"></span>+5% 過熱
      </span>
      <span class="flex items-center gap-1">
        <span class="inline-block w-3 h-0 border-t border-dotted" style="border-color:#6b7280"></span>0%
      </span>
      <span class="flex items-center gap-1">
        <span class="inline-block w-3 h-0 border-t border-dashed" style="border-color:#1d4ed8"></span>-10% 弱気
      </span>
    </div>
    <!-- 凡例: ゾーン背景 (上部・固定) -->
    <div class="flex flex-wrap gap-x-3 gap-y-1 mb-1 text-xs text-gray-400">
      <span>背景:</span>
      <span v-for="z in ZONE_KEYS" :key="z" class="flex items-center gap-1">
        <span class="inline-block w-3 h-3 rounded-sm border border-gray-200"
              :style="{ background: ZONE_BG[z] ?? 'transparent' }"></span>{{ ZONE_LABEL[z] ?? z }}
      </span>
    </div>

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
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { Line } from "vue-chartjs";
import { useApi } from "../../composables/useApi";
import { baseXScale, baseYScale, registerChartPlugins } from "../../composables/useChartDefaults";
import type { MarketPressureTimeseries } from "../../types";

registerChartPlugins();

const props = defineProps<{ days?: number }>();

const api = useApi();
const loading = ref(false);
const data = ref<MarketPressureTimeseries | null>(null);

const ZONE_BG: Record<string, string> = {
	ceiling: "rgba(220,38,38,0.15)",
	overheat: "rgba(202,138,4,0.12)",
	neutral: "rgba(22,163,74,0.08)",
	weak: "rgba(59,130,246,0.18)",
	sellin: "rgba(29,78,216,0.10)",
	bottom: "rgba(30,58,95,0.12)",
};

const ZONE_LABEL: Record<string, string> = {
	ceiling: "天井",
	overheat: "過熱",
	neutral: "中立",
	weak: "弱気",
	sellin: "売り圧力",
	bottom: "底",
};

const ZONE_KEYS = ["ceiling", "overheat", "neutral", "weak", "bottom"] as const;

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
	layout: { padding: { right: 65 } },
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
		x: baseXScale({ ticks: { font: { size: 9 } } }),
		y: baseYScale({
			ticks: {
				callback: (v: string | number) => `${(Number(v) * 100).toFixed(0)}%`,
			},
			afterFit: (scale: { width: number }) => { scale.width = 52; },
		}),
	},
}));

/** ゾーン背景色帯 + ラベル plugin */
const zoneBgPlugin = {
	id: "nkflowPressureZoneBg",
	beforeDraw(chart: {
		ctx: CanvasRenderingContext2D;
		chartArea: {
			top: number;
			bottom: number;
			left: number;
			width: number;
			height: number;
		} | null;
		scales: { y: { getPixelForValue: (v: number) => number } };
	}) {
		const zones = data.value?.pl_zone;
		if (!zones?.length) return;
		const { ctx, chartArea } = chart;
		if (!chartArea) return;
		const bw = chartArea.width / zones.length;
		ctx.save();

		// 背景色帯: 列全体を塗る（その時期がどのゾーンかを示す）
		// 閾値の水平線がゾーン境界を表す役割を担う
		zones.forEach((zone, i) => {
			ctx.fillStyle = ZONE_BG[zone] ?? "rgba(107,114,128,0.05)";
			ctx.fillRect(
				chartArea.left + i * bw,
				chartArea.top,
				bw,
				chartArea.bottom - chartArea.top,
			);
		});

		// ゾーン切替時にラベルを描画
		ctx.font = "bold 10px sans-serif";
		ctx.textBaseline = "top";
		let prevZone = "";
		zones.forEach((zone, i) => {
			if (zone !== prevZone) {
				const label = ZONE_LABEL[zone] ?? zone;
				const x = chartArea.left + i * bw + 3;
				const y = chartArea.top + 3;
				// 背景付きテキスト
				ctx.fillStyle = "rgba(255,255,255,0.75)";
				const tw = ctx.measureText(label).width;
				ctx.fillRect(x - 1, y - 1, tw + 4, 14);
				ctx.fillStyle = "#6b7280";
				ctx.fillText(label, x + 1, y);
				prevZone = zone;
			}
		});
		ctx.restore();
	},
};

/** ゾーン境界 水平線 plugin */
const THRESHOLD_LINES = [
	{ value: 0.15, label: "+15% 天井", color: "#dc2626", dash: [4, 3] },
	{ value: 0.05, label: "+5% 過熱", color: "#ca8a04", dash: [6, 3] },
	{ value: 0,    label: "0%",       color: "#6b7280", dash: [2, 2] },
	{ value: -0.10, label: "-10% 弱気", color: "#1d4ed8", dash: [4, 3] },
];
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const thresholdLinePlugin: any = {
	id: "nkflowThresholdLines",
	// eslint-disable-next-line @typescript-eslint/no-explicit-any
	afterDraw(chart: any) {
		const { ctx, chartArea, scales } = chart;
		if (!chartArea) return;
		ctx.save();
		for (const t of THRESHOLD_LINES) {
			const y = scales.y.getPixelForValue(t.value);
			if (y < chartArea.top || y > chartArea.top + chartArea.height) continue;
			ctx.strokeStyle = t.color;
			ctx.lineWidth = 1;
			ctx.setLineDash(t.dash);
			ctx.beginPath();
			ctx.moveTo(chartArea.left, y);
			ctx.lineTo(chartArea.left + chartArea.width, y);
			ctx.stroke();
			// ラベル (右端): 白背景付きで視認性向上
			ctx.font = "bold 10px sans-serif";
			ctx.textAlign = "right";
			ctx.textBaseline = "bottom";
			const lw = ctx.measureText(t.label).width;
			const lx = chartArea.left + chartArea.width - 3;
			const ly = y - 2;
			ctx.setLineDash([]);
			ctx.fillStyle = "rgba(255,255,255,0.85)";
			ctx.fillRect(lx - lw - 3, ly - 11, lw + 6, 13);
			ctx.fillStyle = t.color;
			ctx.fillText(t.label, lx, ly);
		}
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
const chartPlugins: any[] = [zoneBgPlugin, thresholdLinePlugin, overheatingLinePlugin];

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
