<template>
  <div class="space-y-2">
    <h1 class="text-lg font-bold">コモディティ</h1>

    <div v-if="loading" class="text-gray-500 text-sm">読み込み中...</div>
    <div v-if="error" class="bg-red-50 text-red-700 rounded p-3 text-sm">{{ error }}</div>

    <!-- サマリカード -->
    <div v-if="summaryData.length" class="grid grid-cols-2 sm:grid-cols-4 gap-2">
      <div
        v-for="s in summaryData"
        :key="s.symbol"
        class="card card-compact cursor-pointer"
        :class="selectedSymbol === s.symbol ? 'ring-2 ring-blue-400' : ''"
        @click="selectSymbol(s.symbol)"
      >
        <div class="label text-xs">{{ s.label }}</div>
        <div class="font-semibold text-sm font-mono">{{ formatClose(s.close) }}</div>
        <div class="text-xs mt-0.5" :class="changePctClass(s.change_pct)">
          {{ formatChangePct(s.change_pct) }}
        </div>
        <div class="text-xs text-gray-400">{{ s.date }}</div>
      </div>
    </div>

    <!-- チャート + ティッカー選択 -->
    <div class="card">
      <div class="flex items-center justify-between mb-2 flex-wrap gap-1">
        <div class="flex items-center gap-1 flex-wrap">
          <button
            v-for="c in COMMODITIES"
            :key="c.symbol"
            class="px-2 py-0.5 text-xs rounded"
            :class="selectedSymbol === c.symbol
              ? 'bg-blue-600 text-white'
              : 'bg-gray-100 text-gray-700 hover:bg-gray-200'"
            @click="selectSymbol(c.symbol)"
          >
            {{ c.label }}
          </button>
        </div>
        <PeriodSelector
          :periods="PERIODS.map(p => ({ value: p.days, label: p.label }))"
          :model-value="selectedPeriod"
          @update:model-value="selectPeriod($event as number)"
        />
      </div>

      <div v-if="chartBars.length" class="h-52">
        <PriceChart :prices="chartBars" />
      </div>
      <div v-else-if="chartLoading" class="h-52 flex items-center justify-center text-gray-400 text-sm">
        読み込み中...
      </div>
      <div v-else class="h-52 flex items-center justify-center text-gray-400 text-sm">
        データなし
      </div>
    </div>

    <!-- 価格テーブル -->
    <div v-if="chartData.length" class="card">
      <h2 class="text-sm font-semibold text-gray-700 mb-2">
        {{ selectedLabel }} 価格履歴
      </h2>
      <table class="w-full text-xs">
        <thead>
          <tr class="text-gray-500 border-b border-gray-100">
            <th class="text-left py-1 pr-3 font-medium">日付</th>
            <th class="text-right py-1 pr-3 font-medium">始値</th>
            <th class="text-right py-1 pr-3 font-medium">高値</th>
            <th class="text-right py-1 pr-3 font-medium">安値</th>
            <th class="text-right py-1 pr-3 font-medium">終値</th>
            <th class="text-right py-1 font-medium">前日比</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="row in tableRows"
            :key="row.date"
            class="border-b border-gray-50 hover:bg-gray-50"
          >
            <td class="py-1 pr-3">{{ row.date }}</td>
            <td class="text-right py-1 pr-3 font-mono">{{ row.open != null ? formatClose(row.open) : '—' }}</td>
            <td class="text-right py-1 pr-3 font-mono">{{ row.high != null ? formatClose(row.high) : '—' }}</td>
            <td class="text-right py-1 pr-3 font-mono">{{ row.low != null ? formatClose(row.low) : '—' }}</td>
            <td class="text-right py-1 pr-3 font-mono">{{ formatClose(row.close) }}</td>
            <td class="text-right py-1" :class="changePctClass(row.change_pct)">
              {{ formatChangePct(row.change_pct) }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import PriceChart from "../components/charts/PriceChart.vue";
import PeriodSelector from "../components/shared/PeriodSelector.vue";
import { useApi } from "../composables/useApi";
import type { CommodityBar, CommoditySummary, DailyPrice } from "../types";
import { changePctClass } from "../utils/colors";
import { formatChangePct } from "../utils/formatters";

const api = useApi();

// ── 定数 ──────────────────────────────────────────────────────────────────────

const COMMODITIES = [
	{ symbol: "GC=F", label: "金" },
	{ symbol: "CL=F", label: "原油 (WTI)" },
	{ symbol: "SI=F", label: "銀" },
	{ symbol: "HG=F", label: "銅" },
];

const PERIODS = [
	{ label: "1W", days: 7 },
	{ label: "1M", days: 30 },
	{ label: "3M", days: 90 },
	{ label: "1Y", days: 365 },
];

// ── 状態 ──────────────────────────────────────────────────────────────────────

const loading = ref(true);
const chartLoading = ref(false);
const error = ref("");

const summaryData = ref<CommoditySummary[]>([]);
const chartData = ref<CommodityBar[]>([]);

const selectedSymbol = ref("GC=F");
const selectedPeriod = ref(90);

// ── computed ──────────────────────────────────────────────────────────────────

const selectedLabel = computed(
	() =>
		COMMODITIES.find((c) => c.symbol === selectedSymbol.value)?.label ??
		selectedSymbol.value,
);

// CommodityBar → DailyPrice (PriceChart 互換)
const chartBars = computed<DailyPrice[]>(() =>
	chartData.value.map((d) => ({
		code: d.symbol,
		date: d.date,
		open: d.open ?? d.close,
		high: d.high ?? d.close,
		low: d.low ?? d.close,
		close: d.close,
		volume: d.volume ?? 0,
		return_rate: d.change_pct ?? 0,
		price_range: (d.high ?? d.close) - (d.low ?? d.close),
	})),
);

// 直近 30 件を降順で表示
const tableRows = computed(() => [...chartData.value].reverse().slice(0, 30));

// ── フォーマット ───────────────────────────────────────────────────────────────

function formatClose(v: number): string {
	return v.toLocaleString("en-US", {
		minimumFractionDigits: 2,
		maximumFractionDigits: 2,
	});
}

// ── ロード ────────────────────────────────────────────────────────────────────

async function loadSummary() {
	try {
		summaryData.value =
			(await api.getCommoditiesSummary()) as CommoditySummary[];
	} catch (e) {
		error.value = "サマリデータの取得に失敗しました";
		console.error(e);
	}
}

async function loadChart() {
	chartLoading.value = true;
	try {
		chartData.value = (await api.getCommodities(
			selectedSymbol.value,
			selectedPeriod.value,
		)) as CommodityBar[];
	} catch {
		chartData.value = [];
	} finally {
		chartLoading.value = false;
	}
}

// ── イベント ──────────────────────────────────────────────────────────────────

function selectSymbol(symbol: string) {
	selectedSymbol.value = symbol;
}

function selectPeriod(days: number) {
	selectedPeriod.value = days;
}

// ── ウォッチ ──────────────────────────────────────────────────────────────────

watch([selectedSymbol, selectedPeriod], loadChart);

// ── マウント ──────────────────────────────────────────────────────────────────

onMounted(async () => {
	loading.value = true;
	await Promise.all([loadSummary(), loadChart()]);
	loading.value = false;
});
</script>
