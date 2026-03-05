<template>
  <div>
    <!-- ===== コントロール ===== -->
    <div class="flex flex-wrap gap-2 items-center mb-3">

      <!-- 粒度 -->
      <div class="flex rounded overflow-hidden border border-gray-300 text-xs">
        <button
          v-for="g in granularities" :key="g.value"
          @click="setGranularity(g.value)"
          class="px-3 py-1 transition-colors"
          :class="granularity === g.value
            ? 'bg-blue-600 text-white'
            : 'bg-gray-100 text-gray-600 hover:bg-gray-200 hover:text-gray-900'"
        >{{ g.label }}</button>
      </div>

      <!-- 通常モード: 指標 -->
      <template v-if="!anchorDate">
        <div class="w-px h-4 bg-gray-300" />
        <div class="flex rounded overflow-hidden border border-gray-300 text-xs">
          <button
            v-for="m in metrics" :key="m.value"
            @click="metric = m.value"
            class="px-3 py-1 transition-colors"
            :class="metric === m.value
              ? 'bg-indigo-600 text-white'
              : 'bg-gray-100 text-gray-600 hover:bg-gray-200 hover:text-gray-900'"
          >{{ m.label }}</button>
        </div>
        <span class="text-xs text-gray-400 ml-1">← 棒をクリックで基準日に設定</span>
      </template>

      <!-- アンカーモード: バッジ + 指標 + 表示方法 + 解除 -->
      <template v-else>
        <span class="flex items-center gap-1 text-xs bg-indigo-100 text-indigo-700 px-2 py-1 rounded border border-indigo-200">
          📍 基準日: {{ anchorPeriodLabel }}
        </span>

        <!-- 指標 -->
        <div class="flex rounded overflow-hidden border border-gray-300 text-xs">
          <button
            v-for="m in anchorMetrics" :key="m.value"
            @click="anchorMetric = m.value"
            class="px-3 py-1 transition-colors"
            :class="anchorMetric === m.value
              ? 'bg-indigo-600 text-white'
              : 'bg-gray-100 text-gray-600 hover:bg-gray-200 hover:text-gray-900'"
          >{{ m.label }}</button>
        </div>

        <!-- 集計粒度 -->
        <div class="flex rounded overflow-hidden border border-gray-300 text-xs">
          <button
            v-for="g in groupByOptions" :key="g.value"
            @click="groupBy = g.value"
            class="px-3 py-1 transition-colors"
            :class="groupBy === g.value
              ? 'bg-amber-600 text-white'
              : 'bg-gray-100 text-gray-600 hover:bg-gray-200 hover:text-gray-900'"
          >{{ g.label }}</button>
        </div>

        <button
          @click="clearAnchor"
          class="text-xs px-2 py-1 rounded border border-gray-300 text-gray-600 hover:border-red-500 hover:text-red-600 transition-colors"
        >× 解除</button>
      </template>
    </div>

    <!-- ===== チャート本体 ===== -->
    <div v-if="loading || loadingCumulative"
         class="flex items-center justify-center h-64 text-gray-500 text-sm">
      読み込み中...
    </div>

    <!-- アンカーモード -->
    <template v-else-if="anchorDate">
      <div v-if="!cumulativeData || cumulativeData.series.length === 0"
           class="flex items-center justify-center h-64 text-gray-500 text-sm">
        基準日以降のデータなし
      </div>
      <template v-else>
        <!-- ペア別折れ線 -->
        <div v-if="groupBy === 'pair'" class="h-72 relative">
          <Line :data="pairChartData" :options="cumulativeChartOptions" :plugins="cumulativePlugins" />
        </div>
        <!-- 流入先集計 積み上げ棒 -->
        <div v-else class="h-72 relative">
          <Bar :data="destChartData" :options="destChartOptions" />
        </div>
      </template>
    </template>

    <!-- 通常モード: 棒グラフ -->
    <template v-else>
      <div v-if="!data || data.series.length === 0"
           class="flex items-center justify-center h-64 text-gray-500 text-sm">
        データなし（資金フローの記録がありません）
      </div>
      <div v-else class="h-72 relative">
        <Bar :data="chartData" :options="chartOptions" />
      </div>
    </template>

    <!-- レジーム凡例 (アンカー・ペア別のみ) -->
    <div v-if="anchorDate && groupBy === 'pair' && cumulativeData?.series.length"
         class="flex gap-4 mt-2 text-xs text-gray-500">
      <span class="flex items-center gap-1">
        <span class="inline-block w-3 h-3 rounded-sm" style="background:rgba(16,185,129,0.25)"></span>Risk-on
      </span>
      <span class="flex items-center gap-1">
        <span class="inline-block w-3 h-3 rounded-sm" style="background:rgba(239,68,68,0.25)"></span>Risk-off
      </span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { Bar, Line } from "vue-chartjs";
import { useApi } from "../../composables/useApi";
import {
	baseLegendBottom,
	baseXScale,
	baseYScale,
	registerChartPlugins,
} from "../../composables/useChartDefaults";
import type { FundFlowCumulative, FundFlowTimeseries } from "../../types";
import { SECTOR_COLORS } from "../../utils/colors";

registerChartPlugins();

// ── Props / Emits ────────────────────────────────────────────────────────────
const emit = defineEmits<{
	"anchor-changed": [date: string | null];
}>();

// ── State ────────────────────────────────────────────────────────────────────
const api = useApi();
const loading = ref(false);
const loadingCumulative = ref(false);
const granularity = ref<"week" | "month">("week");
const metric = ref<"count" | "spread">("count");
const anchorMetric = ref<"spread" | "return">("spread");
const groupBy = ref<"pair" | "destination">("destination");
const anchorDate = ref<string | null>(null);
const anchorPeriodLabel = ref("");
const data = ref<FundFlowTimeseries | null>(null);
const cumulativeData = ref<FundFlowCumulative | null>(null);

const granularities = [
	{ value: "week" as const, label: "週次" },
	{ value: "month" as const, label: "月次" },
];
const metrics = [
	{ value: "count" as const, label: "発生回数" },
	{ value: "spread" as const, label: "スプレッド平均" },
];
const anchorMetrics = [
	{ value: "spread" as const, label: "累積スプレッド" },
	{ value: "return" as const, label: "セクター累積リターン" },
];
const groupByOptions = [
	{ value: "pair" as const, label: "ペア別" },
	{ value: "destination" as const, label: "流入先で集計" },
];

const COLORS = [
	"#60a5fa",
	"#34d399",
	"#f59e0b",
	"#f87171",
	"#a78bfa",
	"#fb923c",
	"#38bdf8",
	"#4ade80",
];
function fmtPeriod(p: string): string {
	if (p.includes("-W")) {
		const [y, w] = p.split("-W");
		return `${y.slice(2)}/${parseInt(w, 10)}w`;
	}
	return p.slice(2);
}

// ── 通常モード: 棒グラフ ────────────────────────────────────────────────────

const chartData = computed(() => {
	if (!data.value) return { labels: [], datasets: [] };
	return {
		labels: data.value.periods.map(fmtPeriod),
		datasets: data.value.series.map((s, i) => ({
			label: s.label,
			data: s.values.map((v) =>
				metric.value === "count" ? v.count : v.avg_spread,
			),
			backgroundColor: `${COLORS[i % COLORS.length]}bb`,
			borderColor: COLORS[i % COLORS.length],
			borderWidth: 1,
			borderRadius: 2,
		})),
	};
});

const chartOptions = computed(() => ({
	responsive: true,
	maintainAspectRatio: false,
	onClick: (_: unknown, elements: { index: number }[]) => {
		if (elements.length > 0 && data.value?.start_dates) {
			const idx = elements[0].index;
			const startDate = data.value.start_dates[idx];
			if (startDate) setAnchor(startDate, fmtPeriod(data.value.periods[idx]));
		}
	},
	plugins: {
		legend: baseLegendBottom(),
		tooltip: {
			callbacks: {
				label: (ctx: {
					dataset: { label?: string };
					parsed: { y: number | null };
				}) => {
					const v = ctx.parsed.y ?? 0;
					return metric.value === "count"
						? `${ctx.dataset.label}: ${v}回`
						: `${ctx.dataset.label}: ${(v * 100).toFixed(2)}%`;
				},
			},
		},
	},
	scales: {
		x: baseXScale(),
		y: baseYScale({
			beginAtZero: true,
			ticks: {
				callback: (v: string | number) =>
					metric.value === "spread"
						? `${(Number(v) * 100).toFixed(1)}%`
						: String(v),
			},
		}),
	},
}));

// ── アンカーモード: ペア別折れ線 ─────────────────────────────────────────────

const pairChartData = computed(() => {
	if (!cumulativeData.value) return { labels: [], datasets: [] };
	return {
		labels: cumulativeData.value.periods.map((p) => fmtPeriod(p.key)),
		datasets: cumulativeData.value.series.map((s, i) => ({
			label: s.label,
			data:
				anchorMetric.value === "spread"
					? s.cumulative_spread
					: s.sector_cumulative_return,
			borderColor: COLORS[i % COLORS.length],
			backgroundColor: `${COLORS[i % COLORS.length]}22`,
			borderWidth: 2,
			pointRadius: 3,
			tension: 0.2,
			fill: false,
		})),
	};
});

const cumulativeChartOptions = computed(() => ({
	responsive: true,
	maintainAspectRatio: false,
	plugins: {
		legend: baseLegendBottom(),
		tooltip: {
			callbacks: {
				label: (ctx: {
					dataset: { label?: string };
					parsed: { y: number | null };
				}) => {
					const v = ctx.parsed.y ?? 0;
					return `${ctx.dataset.label}: ${(v * 100).toFixed(2)}%`;
				},
			},
		},
	},
	scales: {
		x: baseXScale(),
		y: baseYScale({
			ticks: {
				callback: (v: string | number) => `${(Number(v) * 100).toFixed(1)}%`,
			},
		}),
	},
}));

/** レジーム帯 plugin */
const regimeBgPlugin = {
	id: "nkflowRegimeBg",
	beforeDraw(chart: {
		ctx: CanvasRenderingContext2D;
		chartArea: {
			top: number;
			left: number;
			width: number;
			height: number;
		} | null;
	}) {
		const periods = cumulativeData.value?.periods;
		if (!periods?.length) return;
		const { ctx, chartArea } = chart;
		if (!chartArea) return;
		const bw = chartArea.width / periods.length;
		ctx.save();
		periods.forEach((p, i) => {
			ctx.fillStyle =
				p.regime === "risk_on"
					? "rgba(16,185,129,0.10)"
					: p.regime === "risk_off"
						? "rgba(239,68,68,0.10)"
						: "rgba(107,114,128,0.05)";
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
const cumulativePlugins = [regimeBgPlugin];

// ── アンカーモード: 流入先で集計 積み上げ棒 ────────────────────────────────

const destChartData = computed(() => {
	if (!cumulativeData.value) return { labels: [], datasets: [] };

	const labels = cumulativeData.value.periods.map((p) => fmtPeriod(p.key));
	const n = labels.length;

	// sector_to ごとに集計
	const bySector: Record<string, number[]> = {};
	cumulativeData.value.series.forEach((s) => {
		const dest = s.sector_to;
		if (!bySector[dest]) bySector[dest] = new Array(n).fill(0);

		if (anchorMetric.value === "spread") {
			// 累積スプレッド: 複数ソースからの寄与を合算
			s.cumulative_spread.forEach((v, i) => {
				bySector[dest][i] += v;
			});
		} else {
			// セクター累積リターン: 同一セクターの値は同じなので上書き
			s.sector_cumulative_return.forEach((v, i) => {
				bySector[dest][i] = v;
			});
		}
	});

	// 最終値が大きい順でソート
	const sorted = Object.entries(bySector).sort(
		(a, b) => (b[1][n - 1] ?? 0) - (a[1][n - 1] ?? 0),
	);

	return {
		labels,
		datasets: sorted.map(([sector, values]) => ({
			label: sector,
			data: values,
			backgroundColor: `${SECTOR_COLORS[sector] ?? COLORS[sorted.findIndex(([s]) => s === sector) % COLORS.length]}cc`,
			borderColor:
				SECTOR_COLORS[sector] ??
				COLORS[sorted.findIndex(([s]) => s === sector) % COLORS.length],
			borderWidth: 1,
			borderRadius: 2,
			stack: "inflow",
		})),
	};
});

const destChartOptions = computed(() => ({
	responsive: true,
	maintainAspectRatio: false,
	plugins: {
		legend: baseLegendBottom(),
		tooltip: {
			callbacks: {
				label: (ctx: {
					dataset: { label?: string };
					parsed: { y: number | null };
				}) => {
					const v = ctx.parsed.y ?? 0;
					return anchorMetric.value === "spread"
						? `${ctx.dataset.label}: ${(v * 100).toFixed(2)}% (累積スプレッド合計)`
						: `${ctx.dataset.label}: ${(v * 100).toFixed(2)}% (累積リターン)`;
				},
			},
		},
	},
	scales: {
		x: baseXScale({ stacked: true }),
		y: baseYScale({
			stacked: true,
			ticks: {
				callback: (v: string | number) => `${(Number(v) * 100).toFixed(1)}%`,
			},
		}),
	},
}));

// ── データ取得 ────────────────────────────────────────────────────────────────

async function load() {
	loading.value = true;
	try {
		data.value = await api.getFundFlowTimeseries(granularity.value);
	} finally {
		loading.value = false;
	}
}

async function setAnchor(date: string, label: string) {
	anchorDate.value = date;
	anchorPeriodLabel.value = label;
	cumulativeData.value = null;
	groupBy.value = "destination";
	emit("anchor-changed", date);
	loadingCumulative.value = true;
	try {
		cumulativeData.value = await api.getFundFlowCumulative(
			date,
			granularity.value,
		);
	} finally {
		loadingCumulative.value = false;
	}
}

function clearAnchor() {
	anchorDate.value = null;
	anchorPeriodLabel.value = "";
	cumulativeData.value = null;
	emit("anchor-changed", null);
}

function setGranularity(g: "week" | "month") {
	granularity.value = g;
	clearAnchor();
	load();
}

onMounted(load);
</script>
