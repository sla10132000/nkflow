<template>
  <div class="space-y-2">
    <div class="flex items-center justify-between">
      <h1 class="text-lg font-bold">コモディティ</h1>
      <!-- タブ切替 -->
      <div class="flex gap-1">
        <button
          v-for="tab in TABS"
          :key="tab.id"
          class="px-3 py-1 text-sm rounded-md font-medium transition-colors"
          :class="activeTab === tab.id
            ? 'bg-blue-600 text-white'
            : 'bg-gray-100 text-gray-700 hover:bg-gray-200'"
          @click="activeTab = tab.id"
        >
          {{ tab.label }}
        </button>
      </div>
    </div>

    <div v-if="loading" class="text-gray-500 text-sm">読み込み中...</div>
    <div v-if="error" class="bg-red-50 text-red-700 rounded p-3 text-sm">{{ error }}</div>

    <!-- ═════════ 価格タブ ═════════ -->
    <template v-if="activeTab === 'price'">
      <!-- サマリカード -->
      <div v-if="summaryData.length" class="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-2">
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

    </template>

    <!-- ═════════ サイクル分析タブ ═════════ -->
    <template v-if="activeTab === 'cycle'">
      <div v-if="scLoading" class="text-gray-500 text-sm">読み込み中...</div>
      <div v-else-if="scError" class="bg-red-50 text-red-700 rounded p-3 text-sm">{{ scError }}</div>

      <template v-if="scOverview">
        <!-- フェーズポジションチャート -->
        <div class="card">
          <h2 class="text-sm font-semibold text-gray-700 mb-3">フェーズポジション</h2>
          <SupercyclePhaseChart
            :phases="scOverview.phases"
            :sectors="scOverview.sectors"
          />
        </div>

        <!-- セクター別カード (5列) -->
        <div class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-2">
          <div
            v-for="sector in sortedSectors"
            :key="sector.id"
            class="card card-compact cursor-pointer transition-shadow"
            :class="selectedSector === sector.id ? 'ring-2 ring-blue-400' : 'hover:shadow-md'"
            @click="selectSector(sector.id)"
          >
            <div class="text-xs font-semibold text-gray-800 mb-1">{{ sector.label }}</div>
            <div class="flex items-center gap-1">
              <span
                class="text-xs px-1.5 py-0.5 rounded-full text-white font-semibold"
                :style="{ backgroundColor: scOverview.phases[String(sector.phase)]?.color ?? '#6b7280' }"
              >
                Phase {{ sector.phase }}
              </span>
            </div>
            <div class="text-xs text-gray-500 mt-1">
              {{ scOverview.phases[String(sector.phase)]?.name }}（{{ scOverview.phases[String(sector.phase)]?.subtitle }}）
            </div>
            <!-- コモディティ一覧 (ティッカー) -->
            <div class="flex flex-wrap gap-1 mt-1">
              <span
                v-for="c in sector.commodities"
                :key="c.ticker"
                class="text-xs font-mono bg-gray-100 px-1 rounded"
              >{{ c.ticker }}</span>
            </div>
          </div>
        </div>

        <!-- セクター詳細 (カード選択で切替) -->
        <div class="card">
          <div class="flex items-center gap-2 mb-3">
            <h2 class="text-sm font-semibold text-gray-700">セクター詳細:</h2>
            <span class="text-sm font-semibold text-blue-600">
              {{ scOverview.sectors.find(s => s.id === selectedSector)?.label ?? '' }}
            </span>
          </div>

          <SupercycleSectorDetail
            :sector-returns="sectorReturns"
            :performance="scPerformance"
            :selected-days="sectorDays"
            @update:selected-days="onSectorDaysChange"
          />
        </div>

        <!-- シナリオ分析 -->
        <div class="card">
          <h2 class="text-sm font-semibold text-gray-700 mb-3">シナリオ分析</h2>
          <div class="flex gap-2 mb-3 flex-wrap">
            <button
              v-for="sc in scOverview.scenarios"
              :key="sc.id"
              class="px-3 py-1 text-xs rounded-full border transition-colors"
              :class="selectedScenario === sc.id
                ? 'bg-blue-600 text-white border-blue-600'
                : 'bg-white text-gray-700 border-gray-300 hover:bg-gray-50'"
              @click="selectedScenario = sc.id"
            >
              {{ sc.name }} {{ sc.probability }}%
            </button>
          </div>
          <div v-if="activeScenario" class="bg-gray-50 rounded-lg p-3">
            <div class="flex items-center gap-3 mb-1">
              <span class="text-sm font-semibold text-gray-800">{{ activeScenario.name }}</span>
              <span class="text-xs bg-blue-100 text-blue-700 px-2 py-0.5 rounded-full">
                ピーク: {{ activeScenario.peak }}
              </span>
              <span class="text-xs bg-gray-200 text-gray-600 px-2 py-0.5 rounded-full">
                確率 {{ activeScenario.probability }}%
              </span>
            </div>
            <p class="text-xs text-gray-600 leading-relaxed">{{ activeScenario.description }}</p>
          </div>
        </div>

        <!-- セクター間相関 -->
        <div class="card">
          <h2 class="text-sm font-semibold text-gray-700 mb-3">セクター間相関</h2>
          <ul class="space-y-2">
            <li
              v-for="(corr, i) in scOverview.correlations"
              :key="i"
              class="flex items-start gap-2 text-xs text-gray-700"
            >
              <span class="mt-0.5 text-gray-400">→</span>
              <span>{{ corr.description }}</span>
            </li>
          </ul>
          <div class="mt-2 text-xs text-gray-400">
            最終更新: {{ scOverview.updated }}
          </div>
        </div>
      </template>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import PriceChart from "../components/charts/PriceChart.vue";
import PeriodSelector from "../components/shared/PeriodSelector.vue";
import SupercyclePhaseChart from "../components/charts/SupercyclePhaseChart.vue";
import SupercycleSectorDetail from "../components/charts/SupercycleSectorDetail.vue";
import { useApi } from "../composables/useApi";
import type {
  CommodityBar,
  CommoditySummary,
  DailyPrice,
  SupercycleOverview,
  SupercycleSectorReturns,
  SupercyclePerformanceItem,
} from "../types";
import { changePctClass } from "../utils/colors";
import { formatChangePct } from "../utils/formatters";

const api = useApi();

// ── タブ定義 ──────────────────────────────────────────────────────────────────

const TABS = [
  { id: "price", label: "価格" },
  { id: "cycle", label: "サイクル分析" },
] as const;

type TabId = typeof TABS[number]["id"];
const activeTab = ref<TabId>("price");

// ── 定数 ──────────────────────────────────────────────────────────────────────

const COMMODITIES = [
  { symbol: "GC=F", label: "金" },
  { symbol: "CL=F", label: "原油 (WTI)" },
  { symbol: "SI=F", label: "銀" },
  { symbol: "HG=F", label: "銅" },
  { symbol: "NG=F", label: "天然ガス" },
  { symbol: "ZW=F", label: "小麦" },
  { symbol: "ZC=F", label: "コーン" },
];

const PERIODS = [
  { label: "1W", days: 7 },
  { label: "1M", days: 30 },
  { label: "3M", days: 90 },
  { label: "1Y", days: 365 },
];

// ── 価格タブ 状態 ─────────────────────────────────────────────────────────────

const loading = ref(true);
const chartLoading = ref(false);
const error = ref("");

const summaryData = ref<CommoditySummary[]>([]);
const chartData = ref<CommodityBar[]>([]);

const selectedSymbol = ref("GC=F");
const selectedPeriod = ref(90);

// ── サイクル分析タブ 状態 ─────────────────────────────────────────────────────

const scLoading = ref(false);
const scError = ref("");
const scOverview = ref<SupercycleOverview | null>(null);
const sectorReturns = ref<SupercycleSectorReturns | null>(null);
const scPerformance = ref<SupercyclePerformanceItem[]>([]);
const selectedSector = ref("energy");
const sectorDays = ref(1825);
const selectedScenario = ref("main");

// ── 価格タブ computed ─────────────────────────────────────────────────────────

const selectedLabel = computed(
  () =>
    COMMODITIES.find((c) => c.symbol === selectedSymbol.value)?.label ??
    selectedSymbol.value,
);

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

// ── サイクル分析 computed ─────────────────────────────────────────────────────

const sortedSectors = computed(() =>
  scOverview.value
    ? [...scOverview.value.sectors].sort((a, b) => a.phase - b.phase)
    : [],
);

const activeScenario = computed(
  () => scOverview.value?.scenarios.find((s) => s.id === selectedScenario.value) ?? null,
);

// ── フォーマット ───────────────────────────────────────────────────────────────

function formatClose(v: number): string {
  return v.toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

// ── 価格タブ ロード ───────────────────────────────────────────────────────────

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

// ── サイクル分析 ロード ───────────────────────────────────────────────────────

async function loadSupercycle() {
  if (scOverview.value) return; // 一度ロード済みなら再取得しない
  scLoading.value = true;
  scError.value = "";
  try {
    const [overview, perf] = await Promise.all([
      api.getSupercycleOverview(),
      api.getSupercyclePerformance(),
    ]);
    scOverview.value = overview;
    scPerformance.value = perf;
    selectedScenario.value = overview.scenarios[0]?.id ?? "main";
    await loadSectorReturns();
  } catch (e) {
    scError.value = "スーパーサイクルデータの取得に失敗しました";
    console.error(e);
  } finally {
    scLoading.value = false;
  }
}

async function loadSectorReturns() {
  try {
    sectorReturns.value = await api.getSupercycleSectorReturns(
      selectedSector.value,
      sectorDays.value,
    );
  } catch {
    sectorReturns.value = null;
  }
}

// ── イベント ──────────────────────────────────────────────────────────────────

function selectSymbol(symbol: string) {
  selectedSymbol.value = symbol;
}

function selectPeriod(days: number) {
  selectedPeriod.value = days;
}

function selectSector(sectorId: string) {
  selectedSector.value = sectorId;
}

function onSectorDaysChange(days: number) {
  sectorDays.value = days;
}

// ── ウォッチ ──────────────────────────────────────────────────────────────────

watch([selectedSymbol, selectedPeriod], loadChart);
watch([selectedSector, sectorDays], loadSectorReturns);
watch(activeTab, (tab) => {
  if (tab === "cycle") loadSupercycle();
});

// ── マウント ──────────────────────────────────────────────────────────────────

onMounted(async () => {
  loading.value = true;
  await Promise.all([loadSummary(), loadChart()]);
  loading.value = false;
});
</script>
