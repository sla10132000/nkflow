<template>
  <div class="space-y-2">
    <h1 class="text-lg font-bold">米国市場</h1>

    <div v-if="loading" class="text-gray-500 text-sm">読み込み中...</div>
    <div v-if="error" class="text-red-600 text-sm">{{ error }}</div>

    <!-- 主要指数カード -->
    <div v-if="summary.length" class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-2">
      <div
        v-for="s in summaryCards"
        :key="s.ticker"
        class="card card-compact cursor-pointer"
        :class="selectedTicker === s.ticker ? 'ring-2 ring-blue-400' : ''"
        @click="selectTicker(s.ticker)"
      >
        <div class="label text-xs truncate">{{ s.label }}</div>
        <div class="font-semibold text-sm">{{ formatClose(s.close, s.ticker) }}</div>
        <div class="flex items-center gap-1 text-xs mt-0.5">
          <span :class="changePctClass(s.change_pct)">
            {{ formatChangePct(s.change_pct) }}
          </span>
          <span v-if="s.ytd_return_pct != null" class="text-gray-400">
            / YTD {{ formatChangePct(s.ytd_return_pct) }}
          </span>
        </div>
        <div class="text-xs text-gray-400">{{ s.date }}</div>
      </div>
    </div>

    <!-- 指数チャート -->
    <div class="card">
      <div class="flex items-center justify-between mb-2 flex-wrap gap-1">
        <div class="flex items-center gap-1 flex-wrap">
          <button
            v-for="t in TICKERS"
            :key="t.ticker"
            class="px-2 py-0.5 text-xs rounded"
            :class="selectedTicker === t.ticker
              ? 'bg-blue-600 text-white'
              : 'bg-gray-100 text-gray-700 hover:bg-gray-200'"
            @click="selectTicker(t.ticker)"
          >
            {{ t.label }}
          </button>
        </div>
        <div class="flex gap-1">
          <button
            v-for="p in PERIODS"
            :key="p.label"
            class="px-2 py-0.5 text-xs rounded"
            :class="selectedPeriod === p.days
              ? 'bg-blue-600 text-white'
              : 'bg-gray-100 text-gray-700 hover:bg-gray-200'"
            @click="selectPeriod(p.days)"
          >
            {{ p.label }}
          </button>
        </div>
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

    <!-- 恐怖指数 + 為替 -->
    <div class="grid grid-cols-2 sm:grid-cols-4 gap-2">
      <!-- VIX -->
      <div class="card card-compact">
        <div class="label">VIX 恐怖指数</div>
        <template v-if="fearIndices?.vix">
          <div class="font-semibold text-sm" :class="vixClass(fearIndices.vix.value)">
            {{ fearIndices.vix.value.toFixed(2) }}
          </div>
          <div class="text-xs" :class="fearIndices.vix.change_pct != null && fearIndices.vix.change_pct >= 0 ? 'text-red-500' : 'text-green-500'">
            {{ fearIndices.vix.change_pct != null
              ? (fearIndices.vix.change_pct >= 0 ? '+' : '') + fearIndices.vix.change_pct.toFixed(2) + '%'
              : '—' }}
          </div>
          <div class="text-xs text-gray-400">{{ fearIndices.vix.date }}</div>
        </template>
        <div v-else class="text-gray-400 text-sm">—</div>
      </div>

      <!-- BTC Fear & Greed -->
      <div class="card card-compact">
        <div class="label">BTC Fear&amp;Greed</div>
        <template v-if="fearIndices?.btc_fear_greed">
          <div class="font-semibold text-sm" :class="fngClass(fearIndices.btc_fear_greed.value)">
            {{ fearIndices.btc_fear_greed.value }}
          </div>
          <div class="text-xs text-gray-500">{{ fearIndices.btc_fear_greed.classification }}</div>
          <div class="text-xs text-gray-400">{{ fearIndices.btc_fear_greed.date }}</div>
        </template>
        <div v-else class="text-gray-400 text-sm">—</div>
      </div>

      <!-- USD/JPY -->
      <div class="card card-compact">
        <div class="label">USD/JPY</div>
        <template v-if="forexLatest">
          <div class="font-semibold text-sm">{{ forexLatest.close.toFixed(2) }}</div>
          <div class="text-xs" :class="(forexLatest.change_rate ?? 0) >= 0 ? 'text-green-600' : 'text-red-600'">
            {{ formatChangeRate(forexLatest.change_rate) }}
          </div>
          <div class="text-xs text-gray-400">{{ forexLatest.date }}</div>
        </template>
        <div v-else class="text-gray-400 text-sm">—</div>
      </div>

      <!-- EUR/USD -->
      <div class="card card-compact">
        <div class="label">EUR/USD</div>
        <template v-if="eurUsdLatest">
          <div class="font-semibold text-sm">{{ eurUsdLatest.close.toFixed(4) }}</div>
          <div class="text-xs" :class="(eurUsdLatest.change_rate ?? 0) >= 0 ? 'text-green-600' : 'text-red-600'">
            {{ formatChangeRate(eurUsdLatest.change_rate) }}
          </div>
          <div class="text-xs text-gray-400">{{ eurUsdLatest.date }}</div>
        </template>
        <div v-else class="text-gray-400 text-sm">—</div>
      </div>
    </div>

    <!-- USD/JPY チャート -->
    <div class="card">
      <div class="flex items-center justify-between mb-2 flex-wrap gap-1">
        <h2 class="text-sm font-semibold text-gray-700">USD/JPY チャート</h2>
        <div class="flex gap-1">
          <button
            v-for="p in PERIODS"
            :key="p.label"
            class="px-2 py-0.5 text-xs rounded"
            :class="forexPeriod === p.days
              ? 'bg-blue-600 text-white'
              : 'bg-gray-100 text-gray-700 hover:bg-gray-200'"
            @click="selectForexPeriod(p.days)"
          >
            {{ p.label }}
          </button>
        </div>
      </div>
      <div v-if="forexBars.length" class="h-40">
        <PriceChart :prices="forexBars" />
      </div>
      <div v-else class="h-40 flex items-center justify-center text-gray-400 text-sm">データなし</div>
    </div>

    <!-- 全指数テーブル -->
    <div v-if="summary.length" class="card">
      <h2 class="text-sm font-semibold text-gray-700 mb-2">指数一覧</h2>
      <table class="w-full text-xs">
        <thead>
          <tr class="text-gray-500 border-b border-gray-100">
            <th class="text-left py-1 pr-3 font-medium">指数</th>
            <th class="text-right py-1 pr-3 font-medium">終値</th>
            <th class="text-right py-1 pr-3 font-medium">前日比</th>
            <th class="text-right py-1 font-medium">年初来</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="s in summary" :key="s.ticker" class="border-b border-gray-50 hover:bg-gray-50">
            <td class="py-1 pr-3">
              <div class="font-medium">{{ TICKER_LABELS[s.ticker] ?? s.ticker }}</div>
              <div class="text-gray-400">{{ s.ticker }}</div>
            </td>
            <td class="text-right py-1 pr-3 font-mono">{{ formatClose(s.close, s.ticker) }}</td>
            <td class="text-right py-1 pr-3" :class="changePctClass(s.change_pct)">
              {{ formatChangePct(s.change_pct) }}
            </td>
            <td class="text-right py-1" :class="changePctClass(s.ytd_return_pct)">
              {{ formatChangePct(s.ytd_return_pct) }}
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
import { useApi } from "../composables/useApi";
import type { DailyPrice, FearIndices, ForexBar, UsIndexBar, UsIndexSummary } from "../types";

const api = useApi();

// ── 定数 ──────────────────────────────────────────────────────────────────────

const TICKERS = [
  { ticker: "^GSPC", label: "S&P 500" },
  { ticker: "^IXIC", label: "NASDAQ" },
  { ticker: "^DJI",  label: "Dow" },
  { ticker: "^RUT",  label: "Russell" },
  { ticker: "^VIX",  label: "VIX" },
];

const TICKER_LABELS: Record<string, string> = {
  "^GSPC": "S&P 500",
  "^IXIC": "NASDAQ Composite",
  "^DJI":  "Dow Jones",
  "^RUT":  "Russell 2000",
  "^VIX":  "VIX",
};

const PERIODS = [
  { label: "1M", days: 20 },
  { label: "3M", days: 60 },
  { label: "6M", days: 120 },
  { label: "1Y", days: 252 },
];

// ── 状態 ──────────────────────────────────────────────────────────────────────

const loading = ref(true);
const chartLoading = ref(false);
const error = ref("");

const summary = ref<UsIndexSummary[]>([]);
const fearIndices = ref<FearIndices | null>(null);
const forexLatest = ref<ForexBar | null>(null);
const eurUsdLatest = ref<ForexBar | null>(null);

const selectedTicker = ref("^GSPC");
const selectedPeriod = ref(60);
const chartData = ref<UsIndexBar[]>([]);

const forexPeriod = ref(60);
const forexData = ref<ForexBar[]>([]);

// ── computed ──────────────────────────────────────────────────────────────────

const summaryCards = computed(() =>
  TICKERS.map((t) => {
    const s = summary.value.find((x) => x.ticker === t.ticker);
    return {
      ticker: t.ticker,
      label: t.label,
      close: s?.close ?? null,
      change_pct: s?.change_pct ?? null,
      ytd_return_pct: s?.ytd_return_pct ?? null,
      date: s?.date ?? null,
    };
  }),
);

// UsIndexBar → DailyPrice (PriceChart 互換)
const chartBars = computed<DailyPrice[]>(() =>
  chartData.value.map((d) => ({
    code: d.ticker,
    date: d.date,
    open: d.open,
    high: d.high,
    low: d.low,
    close: d.close,
    volume: d.volume,
    return_rate: d.change_pct ?? 0,
    price_range: d.high - d.low,
  })),
);

// ForexBar → DailyPrice
const forexBars = computed<DailyPrice[]>(() =>
  forexData.value.map((d) => ({
    code: d.pair,
    date: d.date,
    open: d.open,
    high: d.high,
    low: d.low,
    close: d.close,
    volume: 0,
    return_rate: d.change_rate ?? 0,
    price_range: d.high - d.low,
  })),
);

// ── ロード ────────────────────────────────────────────────────────────────────

async function loadSummary() {
  try {
    const [s, fi, fx] = await Promise.all([
      api.getUsIndicesSummary() as Promise<UsIndexSummary[]>,
      api.getFearIndices() as Promise<FearIndices>,
      api.getForexLatest() as Promise<ForexBar[]>,
    ]);
    summary.value = s;
    fearIndices.value = fi;
    forexLatest.value = fx.find((f) => f.pair === "USDJPY") ?? null;
    eurUsdLatest.value = fx.find((f) => f.pair === "EURUSD") ?? null;
  } catch (e) {
    error.value = "データの取得に失敗しました";
    console.error(e);
  }
}

async function loadChart() {
  chartLoading.value = true;
  try {
    chartData.value = await api.getUsIndices(selectedTicker.value, selectedPeriod.value) as UsIndexBar[];
  } catch {
    chartData.value = [];
  } finally {
    chartLoading.value = false;
  }
}

async function loadForex() {
  try {
    forexData.value = await api.getForex("USDJPY", forexPeriod.value) as ForexBar[];
  } catch {
    forexData.value = [];
  }
}

// ── イベント ──────────────────────────────────────────────────────────────────

function selectTicker(ticker: string) {
  selectedTicker.value = ticker;
}

function selectPeriod(days: number) {
  selectedPeriod.value = days;
}

function selectForexPeriod(days: number) {
  forexPeriod.value = days;
}

// ── ウォッチ ──────────────────────────────────────────────────────────────────

watch([selectedTicker, selectedPeriod], loadChart);
watch(forexPeriod, loadForex);

// ── マウント ──────────────────────────────────────────────────────────────────

onMounted(async () => {
  loading.value = true;
  await Promise.all([loadSummary(), loadChart(), loadForex()]);
  loading.value = false;
});

// ── フォーマッタ ───────────────────────────────────────────────────────────────

function formatClose(v: number | null, ticker: string): string {
  if (v == null) return "—";
  if (ticker === "^VIX") return v.toFixed(2);
  return v.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function formatChangePct(v: number | null | undefined): string {
  if (v == null) return "—";
  return (v >= 0 ? "+" : "") + v.toFixed(2) + "%";
}

function formatChangeRate(v: number | null | undefined): string {
  if (v == null) return "—";
  const pct = v * 100;
  return (pct >= 0 ? "+" : "") + pct.toFixed(2) + "%";
}

function changePctClass(v: number | null | undefined) {
  if (v == null) return "text-gray-400";
  if (v > 0) return "text-green-600 font-medium";
  if (v < 0) return "text-red-600 font-medium";
  return "text-gray-500";
}

function vixClass(v: number) {
  if (v >= 30) return "text-red-600 font-semibold";
  if (v >= 20) return "text-amber-600 font-semibold";
  return "text-green-600 font-semibold";
}

function fngClass(v: number) {
  if (v <= 25) return "text-red-600 font-semibold";
  if (v <= 45) return "text-orange-500 font-semibold";
  if (v <= 55) return "text-gray-600 font-semibold";
  if (v <= 75) return "text-green-500 font-semibold";
  return "text-green-700 font-semibold";
}
</script>
