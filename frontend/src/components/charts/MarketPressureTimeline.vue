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

    <!-- 凡例: ライン -->
    <div class="flex gap-4 mt-2 text-xs text-gray-500">
      <span class="flex items-center gap-1">
        <span class="inline-block w-3 h-1 rounded" style="background:#60a5fa"></span>評価損益率
      </span>
      <span class="flex items-center gap-1">
        <span class="inline-block w-3 h-1 rounded border-dashed border border-amber-400"></span>買残増加率(4週)
      </span>
    </div>
    <!-- 凡例: 閾値ライン -->
    <div class="flex gap-3 mt-1 text-xs text-gray-400">
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
    <!-- 凡例: ゾーン背景 -->
    <div v-if="activeZones.length" class="flex flex-wrap gap-x-3 gap-y-1 mt-1 text-xs text-gray-400">
      <span>背景:</span>
      <span v-for="z in activeZones" :key="z" class="flex items-center gap-1">
        <span class="inline-block w-3 h-3 rounded-sm border border-gray-200"
              :style="{ background: ZONE_BG[z] ?? 'transparent' }"></span>{{ ZONE_LABEL[z] ?? z }}
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
import { Line } from "vue-chartjs";
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

const ZONE_LABEL: Record<string, string> = {
	ceiling: "天井圏",
	overheat: "過熱",
	neutral: "中立",
	weak: "弱気",
	sellin: "売り圧力",
	bottom: "底値圏",
};

const activeZones = computed(() => {
	const zones = data.value?.pl_zone;
	if (!zones?.length) return [];
	return [...new Set(zones)].sort(
		(a, b) =>
			Object.keys(ZONE_BG).indexOf(a) - Object.keys(ZONE_BG).indexOf(b),
	);
});

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

/**
 * ゾーンの値域境界: yMax (上端の閾値) / yMin (下端の閾値)
 * null = チャートエリア端まで延伸
 */
const ZONE_THRESHOLDS: Record<string, { yMin: number | null; yMax: number | null }> = {
	ceiling:  { yMin: 0.15,  yMax: null  },  // +15% 以上
	overheat: { yMin: 0.05,  yMax: 0.15  },  // +5% 〜 +15%
	neutral:  { yMin: 0,     yMax: 0.05  },  // 0% 〜 +5%
	weak:     { yMin: -0.10, yMax: 0     },  // -10% 〜 0%
	bottom:   { yMin: null,  yMax: -0.10 },  // -10% 以下
};

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
		const { ctx, chartArea, scales } = chart;
		if (!chartArea) return;
		const bw = chartArea.width / zones.length;
		ctx.save();

		// 背景色帯: ゾーンに対応した Y 範囲のみ塗る
		zones.forEach((zone, i) => {
			const bounds = ZONE_THRESHOLDS[zone];
			// topPixel: yMax 閾値のピクセル位置 (null = チャート上端)
			const topPixel = bounds?.yMax != null
				? Math.max(chartArea.top, scales.y.getPixelForValue(bounds.yMax))
				: chartArea.top;
			// bottomPixel: yMin 閾値のピクセル位置 (null = チャート下端)
			const bottomPixel = bounds?.yMin != null
				? Math.min(chartArea.bottom, scales.y.getPixelForValue(bounds.yMin))
				: chartArea.bottom;
			if (bottomPixel <= topPixel) return; // 表示範囲外

			ctx.fillStyle = ZONE_BG[zone] ?? "rgba(107,114,128,0.05)";
			ctx.fillRect(
				chartArea.left + i * bw,
				topPixel,
				bw,
				bottomPixel - topPixel,
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
			// ラベル (右端)
			ctx.fillStyle = t.color;
			ctx.font = "9px sans-serif";
			ctx.textAlign = "right";
			ctx.textBaseline = "bottom";
			ctx.fillText(t.label, chartArea.left + chartArea.width - 2, y - 2);
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
