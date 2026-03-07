<script setup lang="ts">
import { ref, watch, onMounted, onUnmounted } from "vue";
import { Chart, registerables } from "chart.js";
import type {
	SupercycleSectorReturns,
	SupercyclePerformanceItem,
} from "../../types";

Chart.register(...registerables);

const props = defineProps<{
	sectorReturns: SupercycleSectorReturns | null;
	performance: SupercyclePerformanceItem[];
	selectedDays: number;
}>();

const emit = defineEmits<{
	(e: "update:selectedDays", days: number): void;
}>();

const DAY_OPTIONS = [
	{ label: "1Y", days: 365 },
	{ label: "3Y", days: 1095 },
	{ label: "5Y", days: 1825 },
];

const HORIZONS = ["1m", "3m", "6m", "1y", "3y", "5y"];

const COLORS = [
	"#3b82f6",
	"#ef4444",
	"#10b981",
	"#f59e0b",
	"#8b5cf6",
	"#06b6d4",
];

const canvasRef = ref<HTMLCanvasElement | null>(null);
// eslint-disable-next-line @typescript-eslint/no-explicit-any
let chart: Chart<any> | null = null;

function buildChart() {
	if (!canvasRef.value || !props.sectorReturns) return;
	if (chart) {
		chart.destroy();
		chart = null;
	}

	const series = props.sectorReturns.series.filter((s) => s.data.length > 0);
	if (series.length === 0) return;

	const datasets = series.map((s, i) => ({
		label: `${s.ticker}${s.is_etf ? " (ETF)" : ""}`,
		data: s.data.map((pt) => ({ x: pt.date, y: pt.value })),
		borderColor: COLORS[i % COLORS.length],
		backgroundColor: "transparent",
		borderWidth: 1.5,
		pointRadius: 0,
		tension: 0.1,
	}));

	chart = new Chart(canvasRef.value, {
		type: "line",
		data: { datasets },
		options: {
			responsive: true,
			maintainAspectRatio: false,
			interaction: { mode: "index", intersect: false },
			plugins: {
				legend: { position: "top", labels: { boxWidth: 12, font: { size: 11 } } },
				tooltip: {
					callbacks: {
						label: (ctx) =>
							`${ctx.dataset.label}: ${Number(ctx.parsed.y).toFixed(1)}`,
					},
				},
			},
			scales: {
				x: {
					type: "time",
					time: { unit: "month", displayFormats: { month: "yy/MM" } },
					ticks: { maxTicksLimit: 8, font: { size: 10 } },
				},
				y: {
					ticks: {
						font: { size: 10 },
						callback: (v) => `${v}`,
					},
					title: { display: true, text: "Base 100", font: { size: 10 } },
				},
			},
		},
	});
}

watch(() => props.sectorReturns, buildChart, { deep: true });
onMounted(buildChart);
onUnmounted(() => { chart?.destroy(); });

function fmtReturn(val: number | null | undefined): string {
	if (val === null || val === undefined) return "—";
	const sign = val >= 0 ? "+" : "";
	return `${sign}${val.toFixed(1)}%`;
}

function returnClass(val: number | null | undefined): string {
	if (val === null || val === undefined) return "text-gray-400";
	return val >= 0 ? "text-green-600 font-medium" : "text-red-600 font-medium";
}

// パフォーマンステーブルはセクター内のティッカーのみ
const sectorTickers = computed<Set<string>>(() => {
	if (!props.sectorReturns) return new Set();
	return new Set(props.sectorReturns.series.map((s) => s.ticker));
});

const filteredPerformance = computed(() =>
	props.performance.filter((p) => sectorTickers.value.has(p.ticker)),
);
</script>

<script lang="ts">
import { computed } from "vue";
export default { name: "SupercycleSectorDetail" };
</script>

<template>
	<div class="sector-detail">
		<!-- 期間切替 -->
		<div class="flex items-center gap-2 mb-3">
			<span class="text-xs text-gray-500">期間:</span>
			<button
				v-for="opt in DAY_OPTIONS"
				:key="opt.days"
				class="px-2 py-0.5 text-xs rounded border transition-colors"
				:class="
					selectedDays === opt.days
						? 'bg-blue-600 text-white border-blue-600'
						: 'bg-white text-gray-600 border-gray-300 hover:bg-gray-50'
				"
				@click="emit('update:selectedDays', opt.days)"
			>
				{{ opt.label }}
			</button>
		</div>

		<!-- チャート -->
		<div class="chart-wrapper">
			<canvas ref="canvasRef" />
			<div v-if="!sectorReturns || sectorReturns.series.every(s => s.data.length === 0)" class="no-data">
				データなし
			</div>
		</div>

		<!-- パフォーマンステーブル -->
		<div class="mt-4 overflow-x-auto">
			<table class="perf-table">
				<thead>
					<tr>
						<th>Ticker</th>
						<th>銘柄</th>
						<th v-for="h in HORIZONS" :key="h">{{ h.toUpperCase() }}</th>
					</tr>
				</thead>
				<tbody>
					<tr v-for="item in filteredPerformance" :key="item.ticker">
						<td class="font-mono text-xs font-semibold">
							{{ item.ticker }}
							<span v-if="item.is_etf" class="etf-badge">ETF</span>
						</td>
						<td class="text-xs text-gray-600 max-w-28 truncate">{{ item.label }}</td>
						<td
							v-for="h in HORIZONS"
							:key="h"
							class="text-xs text-right tabular-nums"
							:class="returnClass(item.returns[h])"
						>
							{{ fmtReturn(item.returns[h]) }}
						</td>
					</tr>
					<tr v-if="filteredPerformance.length === 0">
						<td :colspan="2 + HORIZONS.length" class="text-center text-xs text-gray-400 py-4">
							データなし
						</td>
					</tr>
				</tbody>
			</table>
		</div>
	</div>
</template>

<style scoped>
.sector-detail {
	width: 100%;
}

.chart-wrapper {
	position: relative;
	height: 220px;
}

.no-data {
	position: absolute;
	inset: 0;
	display: flex;
	align-items: center;
	justify-content: center;
	font-size: 13px;
	color: #9ca3af;
}

.perf-table {
	width: 100%;
	border-collapse: collapse;
	font-size: 12px;
}

.perf-table th {
	background: #f9fafb;
	border-bottom: 1px solid #e5e7eb;
	padding: 4px 8px;
	text-align: right;
	font-weight: 600;
	font-size: 11px;
	color: #6b7280;
	white-space: nowrap;
}

.perf-table th:first-child,
.perf-table th:nth-child(2) {
	text-align: left;
}

.perf-table td {
	border-bottom: 1px solid #f3f4f6;
	padding: 4px 8px;
}

.perf-table tr:hover td {
	background: #f9fafb;
}

.etf-badge {
	display: inline-block;
	font-size: 9px;
	padding: 0 3px;
	background: #e0e7ff;
	color: #4338ca;
	border-radius: 3px;
	margin-left: 2px;
	vertical-align: middle;
}

.tabular-nums {
	font-variant-numeric: tabular-nums;
}

.max-w-28 {
	max-width: 112px;
}
</style>
