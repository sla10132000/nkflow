<template>
  <div class="space-y-3">
    <!-- ヘッダー行: タイトル + バッジ + 資金フロー分析フィルタ -->
    <div class="flex flex-wrap items-center gap-2">
      <h1 class="text-xl font-bold text-gray-900">資金フロー</h1>
      <span v-if="currentRegime"
        :class="regimeBadgeClass"
        class="px-2 py-0.5 rounded border text-xs font-medium">
        {{ regimeLabel }}
      </span>
      <span v-if="anchorDate"
        class="bg-indigo-100 text-indigo-700 px-2 py-0.5 rounded border border-indigo-200 text-xs">
        📍 {{ anchorDate }} 以降
      </span>
      <span v-if="isCreditOverheating"
        class="animate-pulse bg-red-100 text-red-700 px-2 py-0.5 rounded border border-red-300 text-xs font-bold">
        ⚠ 信用過熱
      </span>

    </div>

    <!-- メインコンテンツ: ゲージ(左) + 時系列フロー(右) -->
    <div class="grid grid-cols-[280px_1fr] gap-3 items-start">

      <!-- 左カラム: 市場圧力ゲージ -->
      <div class="bg-white rounded-lg border border-gray-200 shadow-sm p-3">
        <h2 class="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">市場圧力 (信用評価損益)</h2>
        <div v-if="latestPressure" class="flex flex-col items-center">
          <MarketPressureGauge
            :pl-ratio="latestPressure.pl_ratio"
            :pl-zone="latestPressure.pl_zone"
            :buy-growth-4w="latestPressure.buy_growth_4w"
          />
          <div class="mt-2 w-full text-xs text-gray-500 space-y-1 border-t pt-2">
            <div class="flex justify-between">
              <span>信用倍率</span>
              <span class="text-gray-800 font-medium">{{ fmtNum(latestPressure.margin_ratio) }}</span>
            </div>
            <div class="flex justify-between">
              <span>倍率トレンド</span>
              <span :class="trendClass" class="font-medium">{{ fmtNum(latestPressure.margin_ratio_trend, 3) }}</span>
            </div>
          </div>
        </div>
        <div v-else class="flex items-center justify-center py-8 text-xs text-gray-400">
          信用残高データなし
        </div>
      </div>

      <!-- 右カラム: 時系列フロー -->
      <div class="bg-white rounded-lg border border-gray-200 shadow-sm p-3">
        <h2 class="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">時系列フロー</h2>
        <FundFlowTimeline @anchor-changed="onAnchorChanged" />
      </div>
    </div>

    <!-- 信用圧力タイムライン + 投資主体別フロー (共有期間ボタンでグループ化) -->
    <div class="rounded-lg border border-gray-200 bg-white shadow-sm">
      <!-- 共有ヘッダー: 期間ボタン -->
      <div class="flex items-center gap-3 px-3 py-2 border-b border-gray-100">
        <span class="text-xs font-semibold text-gray-500 uppercase tracking-wide shrink-0">期間</span>
        <div class="flex gap-1">
          <button v-for="w in [4, 9, 13, 26]" :key="w"
            @click="setSharedWeeks(w)"
            class="px-2 py-0.5 text-xs rounded border transition-colors"
            :class="sharedWeeks === w
              ? 'border-blue-500 text-blue-600 bg-blue-50'
              : 'border-gray-300 text-gray-600 hover:border-blue-500 hover:text-blue-600'"
          >{{ w }}週</button>
        </div>
      </div>

      <!-- 縦並び: 投資主体別フロー (上) + 信用圧力タイムライン (下) -->
      <div class="flex flex-col divide-y divide-gray-100">

        <!-- 上: 投資主体別フロー -->
        <div class="p-3">
          <div class="flex flex-wrap items-center gap-2 mb-2">
            <h2 class="text-xs font-semibold text-gray-500 uppercase tracking-wide shrink-0">投資主体別フロー (東証プライム)</h2>
            <template v-if="latestFlow">
              <span :class="regimeFlowBadgeClass(latestFlow.indicators.flow_regime)" class="text-xs px-2 py-0.5 rounded-full font-medium">
                {{ flowRegimeLabel(latestFlow.indicators.flow_regime) }}
              </span>
              <span class="text-xs text-gray-400">乖離: {{ latestFlow.indicators.divergence_score != null ? latestFlow.indicators.divergence_score.toFixed(2) : '—' }}</span>
            </template>
          </div>
          <InvestorFlowChart v-if="flowIndicators.length" :indicators="flowIndicators" :weeks="sharedWeeks" />
          <p v-else-if="!loadingFlow" class="text-sm text-gray-500">データなし</p>
          <p v-if="loadingFlow" class="text-sm text-gray-500">読み込み中...</p>
        </div>

        <!-- 下: 信用圧力タイムライン -->
        <div class="p-3">
          <h2 class="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">信用圧力タイムライン</h2>
          <MarketPressureTimeline :days="pressureDays" />
        </div>

      </div>
    </div>

    <!-- 資金フロー分析 (フィルタ + サンキー + ネットワーク) -->
    <div class="rounded-lg border border-blue-200 bg-blue-50/30 space-y-3 p-3">
      <!-- フィルタ -->
      <div class="flex flex-wrap gap-3 items-center bg-white p-3 rounded-lg border border-gray-200 shadow-sm">
        <h2 class="text-sm font-semibold text-gray-700">資金フロー分析</h2>
        <div class="flex rounded overflow-hidden border border-gray-300 text-xs font-medium">
          <button
            v-for="ft in fundFlowFilters" :key="ft.value"
            @click="setFundFlowFilter(ft.value)"
            class="px-3 py-1.5 transition-colors"
            :class="fundFlowFilter === ft.value
              ? 'bg-blue-600 text-white'
              : 'bg-gray-100 text-gray-600 hover:bg-gray-200'"
          >{{ ft.label }}</button>
        </div>

        <template v-if="fundFlowFilter === 'period'">
          <div class="flex gap-1">
            <button v-for="p in periods" :key="p" @click="setPeriod(p)"
              class="btn-tab" :class="{ 'btn-tab-active': period === p }">{{ p }}</button>
          </div>
        </template>

        <template v-else-if="fundFlowFilter === 'range'">
          <div class="flex gap-1">
            <button v-for="pr in rangePresets" :key="pr.label" @click="applyRangePreset(pr)"
              class="px-2 py-0.5 text-xs rounded border border-gray-300 text-gray-600 hover:border-blue-500 hover:text-blue-600 transition-colors"
            >{{ pr.label }}</button>
          </div>
          <div class="flex items-center gap-1">
            <input v-model="dateFrom" @change="loadNetwork" type="date" class="date-input" />
            <span class="text-gray-400 text-xs">→</span>
            <input v-model="dateTo" @change="loadNetwork" type="date" class="date-input" />
          </div>
        </template>

        <template v-else-if="fundFlowFilter === 'date'">
          <div class="flex gap-1">
            <button v-for="pr in datePresets" :key="pr.label" @click="applyDatePreset(pr)"
              class="px-2 py-0.5 text-xs rounded border border-gray-300 text-gray-600 hover:border-blue-500 hover:text-blue-600 transition-colors"
            >{{ pr.label }}</button>
          </div>
          <input v-model="dateSingle" @change="loadNetwork" type="date" class="date-input" />
        </template>
      </div>

      <!-- タブ切替: サンキー図 / ネットワーク -->
      <div class="bg-white rounded-lg border border-gray-200 shadow-sm">
        <!-- タブヘッダー -->
        <div class="flex border-b border-gray-200">
          <button
            @click="activeVisualizationTab = 'sankey'"
            class="px-4 py-2.5 text-sm font-medium transition-colors border-b-2 -mb-px"
            :class="activeVisualizationTab === 'sankey'
              ? 'border-blue-500 text-blue-600'
              : 'border-transparent text-gray-500 hover:text-gray-700'"
          >サンキー図</button>
          <button
            @click="activeVisualizationTab = 'network'"
            class="px-4 py-2.5 text-sm font-medium transition-colors border-b-2 -mb-px"
            :class="activeVisualizationTab === 'network'
              ? 'border-blue-500 text-blue-600'
              : 'border-transparent text-gray-500 hover:text-gray-700'"
          >ネットワーク</button>
        </div>

        <!-- サンキー図タブ -->
        <div v-if="activeVisualizationTab === 'sankey'" class="p-3">
          <p class="text-xs text-gray-400 mb-2">帯の幅 = フロー発生回数（太いほど強い流れ）</p>
          <div v-if="loading" class="flex items-center justify-center h-32 text-gray-500 text-sm">読み込み中...</div>
          <div v-else-if="error" class="flex items-center justify-center h-32 text-red-600 text-sm">{{ error }}</div>
          <FundFlowSankey v-else-if="networkData" :edges="networkData.edges" />
          <div v-else class="flex items-center justify-center h-32 text-gray-400 text-sm">データなし</div>
        </div>

        <!-- ネットワークタブ -->
        <div v-else-if="activeVisualizationTab === 'network'">
          <div class="flex gap-3 h-[520px] p-3">
            <div class="flex-1 overflow-hidden rounded">
              <GraphView
                v-if="networkData && networkData.nodes.length > 0"
                :data="networkData"
                :directed="true"
                :anchor-mode="!!anchorDate"
                @node-click="onNodeClick"
                class="w-full h-full"
              />
              <div v-else class="flex items-center justify-center h-full text-gray-500 text-sm">
                {{ loading ? '読み込み中...' : '該当期間に資金フローなし' }}
              </div>
            </div>
            <div v-if="selectedNode" class="w-44 bg-gray-50 rounded border border-gray-200 p-3 text-xs text-gray-600 space-y-1 shrink-0">
              <p class="font-semibold text-gray-800 mb-2">{{ selectedNode }}</p>
              <p>接続: {{ connectedEdges }}本</p>
              <p>流入: {{ inflowCount }}本</p>
              <p>流出: {{ outflowCount }}本</p>
            </div>
          </div>
          <div class="px-4 pb-2.5 text-xs text-gray-400">
            エッジ太さ: 出現頻度 / 矢印: 資金フロー方向 / ノード枠: 流入集中度
          </div>
        </div>
      </div>
  </div>
  </div>
</template>




<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import DivergenceGauge from "../components/charts/DivergenceGauge.vue";
import InvestorFlowChart from "../components/charts/InvestorFlowChart.vue";
import FundFlowSankey from "../components/fund-flow/FundFlowSankey.vue";
import FundFlowTimeline from "../components/fund-flow/FundFlowTimeline.vue";
import MarketPressureGauge from "../components/market-pressure/MarketPressureGauge.vue";
import MarketPressureTimeline from "../components/market-pressure/MarketPressureTimeline.vue";
import GraphView from "../components/network/GraphView.vue";
import { useApi } from "../composables/useApi";
import { useMarketStore } from "../stores/useMarketStore";
import type {
	InvestorFlowIndicator,
	InvestorFlowLatest,
	MarketPressureTimeseries,
	NetworkData,
} from "../types";
import { fmt, lastBusinessDay, periodToDateRange } from "../utils/dateRange";
import { fmtNum } from "../utils/formatters";

const api = useApi();
const marketStore = useMarketStore();
const loading = ref(false);
const error = ref("");
const networkData = ref<NetworkData | null>(null);
const selectedNode = ref<string | null>(null);
const activeVisualizationTab = ref<"sankey" | "network">("sankey");
const showPressureTimeline = ref(true);
const sharedWeeks = ref(13);
const pressureDays = computed(() => sharedWeeks.value * 7);
const period = ref("20d");
const fundFlowFilter = ref<"period" | "range" | "date">("range");
const dateFrom = ref("");
const dateTo = ref("");
const dateSingle = ref("");
const anchorDate = ref<string | null>(null);
const pressureData = ref<MarketPressureTimeseries | null>(null);
const latestFlow = ref<InvestorFlowLatest | null>(null);
const flowIndicators = ref<InvestorFlowIndicator[]>([]);
const loadingFlow = ref(false);

const currentRegime = computed(() => marketStore.regime);

const periods = ["20d", "60d", "120d"];
const fundFlowFilters = [
	{ value: "period", label: "期間" },
	{ value: "range", label: "範囲" },
	{ value: "date", label: "日付" },
];
const rangePresets = [
	{ label: "直近5営業日", days: 7 },
	{ label: "先月", days: 30 },
	{ label: "3ヶ月", days: 90 },
];
const datePresets = [
	{ label: "今日", offsetDays: 0 },
	{ label: "昨日", offsetDays: 1 },
	{ label: "先週末", offsetDays: -1 },
];

const latestPressure = computed(() => {
	if (!pressureData.value || pressureData.value.dates.length === 0) return null;
	const last = pressureData.value.dates.length - 1;
	return {
		pl_ratio: pressureData.value.pl_ratio[last] ?? null,
		pl_zone: pressureData.value.pl_zone[last] ?? "neutral",
		buy_growth_4w: pressureData.value.buy_growth_4w[last] ?? null,
		margin_ratio: pressureData.value.margin_ratio[last] ?? null,
		margin_ratio_trend: pressureData.value.margin_ratio_trend[last] ?? null,
	};
});

const isCreditOverheating = computed(() => {
	if (!pressureData.value || pressureData.value.signal_flags.length === 0)
		return false;
	const last = pressureData.value.signal_flags.length - 1;
	return pressureData.value.signal_flags[last]?.credit_overheating === true;
});

const trendClass = computed(() => {
	const t = latestPressure.value?.margin_ratio_trend ?? 0;
	return t > 0 ? "text-red-600" : t < 0 ? "text-green-600" : "text-gray-600";
});

const regimeBadgeClass = computed(() => {
	if (currentRegime.value === "risk_on")
		return "bg-green-100 text-green-700 border-green-200";
	if (currentRegime.value === "risk_off")
		return "bg-red-100 text-red-700 border-red-200";
	return "bg-gray-100 text-gray-600 border-gray-300";
});

function regimeFlowBadgeClass(regime: string | null): string {
	if (regime === "bullish") return "bg-blue-100 text-blue-700";
	if (regime === "bearish") return "bg-red-100 text-red-700";
	if (regime === "diverging") return "bg-amber-100 text-amber-700";
	return "bg-gray-100 text-gray-600";
}

function flowRegimeLabel(regime: string | null): string {
	if (regime === "bullish" || regime === "bull") return "強気 (海外買い優勢)";
	if (regime === "bearish" || regime === "bear") return "弱気 (個人買い・海外売り)";
	if (regime === "diverging") return "乖離拡大";
	if (regime === "neutral") return "中立";
	return regime?.toUpperCase() ?? "N/A";
}
const regimeLabel = computed(() => {
	if (currentRegime.value === "risk_on") return "🟢 Risk-on";
	if (currentRegime.value === "risk_off") return "🔴 Risk-off";
	return "⚪ Neutral";
});

const connectedEdges = computed(() => {
	if (!networkData.value || !selectedNode.value) return 0;
	return networkData.value.edges.filter(
		(e) => e.from === selectedNode.value || e.to === selectedNode.value,
	).length;
});
const inflowCount = computed(() => {
	if (!networkData.value || !selectedNode.value) return 0;
	return networkData.value.edges.filter((e) => e.to === selectedNode.value)
		.length;
});
const outflowCount = computed(() => {
	if (!networkData.value || !selectedNode.value) return 0;
	return networkData.value.edges.filter((e) => e.from === selectedNode.value)
		.length;
});

function setRangeDates(pr: { days: number }) {
	const to = new Date();
	const from = new Date();
	from.setDate(to.getDate() - pr.days);
	dateTo.value = fmt(to);
	dateFrom.value = fmt(from);
}

function applyRangePreset(pr: { days: number }) {
	setRangeDates(pr);
	loadNetwork();
}

function applyDatePreset(pr: { label: string; offsetDays: number }) {
	if (pr.label === "先週末") {
		const d = new Date();
		const dow = d.getDay();
		const daysToFriday =
			dow === 0 ? 2 : dow === 6 ? 1 : dow - 5 + (dow < 5 ? 7 : 0);
		d.setDate(d.getDate() - daysToFriday);
		dateSingle.value = fmt(d);
	} else {
		const d = new Date();
		d.setDate(d.getDate() - pr.offsetDays);
		dateSingle.value = fmt(lastBusinessDay(d));
	}
	loadNetwork();
}

function onAnchorChanged(date: string | null) {
	anchorDate.value = date;
}

async function loadPressure() {
	try {
		pressureData.value = await api.getMarketPressureTimeseries(
			pressureDays.value,
		);
	} catch {
		pressureData.value = null;
	}
}

async function loadInvestorFlows() {
	loadingFlow.value = true;
	try {
		const [latest, indicators] = await Promise.all([
			api.getInvestorFlowsLatest(),
			// 常に26週分ロード; 表示件数は sharedWeeks で制御
			api.getInvestorFlowsIndicators(26),
		]);
		latestFlow.value = latest;
		flowIndicators.value = indicators;
	} catch {
		// 非クリティカル: 既存セクションに影響させない
	} finally {
		loadingFlow.value = false;
	}
}

function setSharedWeeks(w: number) {
	sharedWeeks.value = w;
	loadPressure();
}

async function loadNetwork() {
	loading.value = true;
	error.value = "";
	selectedNode.value = null;
	try {
		let df: string | undefined;
		let dt: string | undefined;
		if (fundFlowFilter.value === "period") {
			const range = periodToDateRange(period.value);
			df = range.from;
			dt = range.to;
		} else if (fundFlowFilter.value === "range") {
			df = dateFrom.value || undefined;
			dt = dateTo.value || undefined;
		} else {
			df = dateSingle.value || undefined;
			dt = dateSingle.value || undefined;
		}
		networkData.value = await api.getNetwork(
			"fund_flow",
			undefined,
			undefined,
			df,
			dt,
		);
	} catch (e: unknown) {
		error.value = e instanceof Error ? e.message : "データ取得失敗";
	} finally {
		loading.value = false;
	}
}

function setPeriod(p: string) {
	period.value = p;
	loadNetwork();
}

function setFundFlowFilter(f: string) {
	fundFlowFilter.value = f as "period" | "range" | "date";
	loadNetwork();
}

function onNodeClick(id: string) {
	selectedNode.value = id;
}

onMounted(() => {
	setRangeDates({ days: 7 });
	Promise.all([
		loadNetwork(),
		marketStore.fetchSummary(),
		loadPressure(),
		loadInvestorFlows(),
	]);
});
</script>

<style scoped>
.btn-tab { @apply px-2.5 py-0.5 rounded text-xs border border-gray-300 text-gray-600 hover:text-gray-900 transition-colors; }
.btn-tab-active { @apply border-blue-500 text-blue-600 bg-blue-50; }

.date-input {
  @apply bg-white border border-gray-300 rounded px-2 py-1 text-xs text-gray-800;
}
.date-input:focus {
  @apply outline-none border-blue-500 ring-1 ring-blue-500/40;
}
</style>
