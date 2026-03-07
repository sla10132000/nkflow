<template>
  <div class="space-y-2">
    <h1 class="text-lg font-bold">概要</h1>

    <LoadingState :loading="loading" :error="error">

    <!-- 直近の主なニュース -->
    <div v-if="topNews.length" class="card">
      <div class="flex items-center justify-between mb-1">
        <h2 class="text-sm font-semibold text-gray-700">直近の主なニュース</h2>
        <RouterLink to="/news" class="text-xs text-blue-600 hover:underline whitespace-nowrap">すべて見る →</RouterLink>
      </div>
      <ul class="space-y-1">
        <li v-for="article in topNews" :key="article.id" class="flex items-baseline gap-1.5 min-w-0">
          <span class="text-xs text-gray-400 whitespace-nowrap shrink-0">
            {{ article.source_name ?? article.source }} {{ formatDateTime(article.published_at) }}
          </span>
          <a
            :href="article.url"
            target="_blank"
            rel="noopener noreferrer"
            class="text-sm text-blue-700 hover:underline leading-tight truncate flex-1 min-w-0"
          >
            {{ article.title_ja ?? article.title }}
          </a>
        </li>
      </ul>
    </div>

    <template v-if="marketStore.summary">
      <!-- サマリ + 恐怖指数を1行に統合 -->
      <div class="grid grid-cols-3 md:grid-cols-6 gap-2">
        <div class="card card-compact">
          <div class="label">日付</div>
          <div class="value-sm">{{ marketStore.summary.date }}</div>
        </div>
        <div class="card card-compact">
          <div class="label">日経終値</div>
          <div class="value-sm">{{ marketStore.summary.nikkei_close?.toLocaleString() ?? '—' }}</div>
        </div>
        <div class="card card-compact">
          <div class="label">騰落率</div>
          <div class="value-sm" :class="returnClass(marketStore.summary.nikkei_return)">
            {{ formatReturn(marketStore.summary.nikkei_return) }}
          </div>
        </div>
        <div class="card card-compact">
          <div class="label">レジーム</div>
          <div class="value-sm" :class="regimeClass(marketStore.summary.regime)">{{ marketStore.summary.regime ?? '—' }}</div>
        </div>
        <!-- VIX -->
        <div v-if="marketStore.fearIndices" class="card card-compact">
          <div class="label">VIX</div>
          <template v-if="marketStore.fearIndices.vix">
            <div class="value-sm" :class="vixClass(marketStore.fearIndices.vix.value)">
              {{ marketStore.fearIndices.vix.value.toFixed(1) }}
              <span v-if="marketStore.fearIndices.vix.change_pct != null" class="text-xs font-normal" :class="marketStore.fearIndices.vix.change_pct >= 0 ? 'text-red-500' : 'text-green-500'">
                {{ marketStore.fearIndices.vix.change_pct >= 0 ? '+' : '' }}{{ marketStore.fearIndices.vix.change_pct.toFixed(1) }}%
              </span>
            </div>
          </template>
          <div v-else class="text-gray-400 text-xs">—</div>
        </div>
        <!-- BTC Fear & Greed -->
        <div v-if="marketStore.fearIndices" class="card card-compact">
          <div class="label">Fear&amp;Greed</div>
          <template v-if="marketStore.fearIndices.btc_fear_greed">
            <div class="value-sm" :class="fngClass(marketStore.fearIndices.btc_fear_greed.value)">
              {{ marketStore.fearIndices.btc_fear_greed.value }}
              <span class="text-xs font-normal">{{ marketStore.fearIndices.btc_fear_greed.classification }}</span>
            </div>
          </template>
          <div v-else class="text-gray-400 text-xs">—</div>
        </div>
      </div>

      <!-- 日経平均チャート + 業種トレンド 横並び -->
      <div class="grid gap-2" style="grid-template-columns: 2fr 3fr">
        <div class="card card-compact">
          <h2 class="text-xs font-semibold text-gray-500 mb-1">日経平均</h2>
          <NikkeiAreaChart :initial-data="marketStore.overviewSnapshot?.nikkei_ohlcv" />
        </div>
        <div v-if="jpSectorData.length" class="card" style="overflow: hidden">
          <SectorTrendBar :sectors="jpSectorData" :columns="4" />
        </div>
      </div>

      <!-- 上昇/下落上位 + 年初来高値 -->
      <div class="grid md:grid-cols-3 gap-2">
        <div class="card">
          <h2 class="text-sm font-semibold mb-1 text-green-600">上昇上位</h2>
          <table class="w-full text-xs">
            <thead><tr class="text-gray-500 text-left"><th class="pb-0.5">コード</th><th class="pb-0.5">名称</th><th class="pb-0.5 text-right">騰落率</th></tr></thead>
            <tbody>
              <tr v-for="g in marketStore.summary.top_gainers" :key="g.code" class="border-t border-gray-100">
                <td class="py-0.5">
                  <RouterLink :to="`/stock/${g.code}`" class="text-blue-600 hover:underline">{{ g.code }}</RouterLink>
                </td>
                <td class="py-0.5 text-gray-700 truncate max-w-[140px]">{{ g.name }}</td>
                <td class="py-0.5 text-right text-green-600 font-medium">{{ formatReturn(g.return_rate) }}</td>
              </tr>
            </tbody>
          </table>
        </div>

        <div class="card">
          <h2 class="text-sm font-semibold mb-1 text-red-600">下落上位</h2>
          <table class="w-full text-xs">
            <thead><tr class="text-gray-500 text-left"><th class="pb-0.5">コード</th><th class="pb-0.5">名称</th><th class="pb-0.5 text-right">騰落率</th></tr></thead>
            <tbody>
              <tr v-for="l in marketStore.summary.top_losers" :key="l.code" class="border-t border-gray-100">
                <td class="py-0.5">
                  <RouterLink :to="`/stock/${l.code}`" class="text-blue-600 hover:underline">{{ l.code }}</RouterLink>
                </td>
                <td class="py-0.5 text-gray-700 truncate max-w-[140px]">{{ l.name }}</td>
                <td class="py-0.5 text-right text-red-600 font-medium">{{ formatReturn(l.return_rate) }}</td>
              </tr>
            </tbody>
          </table>
        </div>

        <div class="card">
          <h2 class="text-sm font-semibold mb-0.5 text-amber-600">年初来高値圏</h2>
          <p class="text-xs text-gray-400 mb-1">年初来高値との差 (★=高値更新中)</p>
          <table class="w-full text-xs">
            <thead><tr class="text-gray-500 text-left"><th class="pb-0.5">コード</th><th class="pb-0.5">名称</th><th class="pb-0.5 text-right">高値比</th></tr></thead>
            <tbody>
              <tr v-for="h in ytdHighs" :key="h.code" class="border-t border-gray-100">
                <td class="py-0.5">
                  <RouterLink :to="`/stock/${h.code}`" class="text-blue-600 hover:underline">{{ h.code }}</RouterLink>
                </td>
                <td class="py-0.5 text-gray-700 truncate max-w-[140px]">{{ h.name }}</td>
                <td class="py-0.5 text-right font-medium" :class="h.gap_pct >= 0 ? 'text-amber-600' : 'text-gray-600'">
                  {{ h.gap_pct >= 0 ? '★' : '' }}{{ h.gap_pct.toFixed(1) }}%
                </td>
              </tr>
              <tr v-if="!ytdHighs.length">
                <td colspan="3" class="py-1 text-gray-400">データなし</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- セクター騰落率 (日本 + 米国) + マーケット情報パネル -->
      <div class="card">
        <div class="flex items-center justify-between mb-2">
          <h2 class="text-sm font-semibold">セクター騰落率</h2>
          <PeriodSelector :periods="sectorPeriods" :model-value="activeSectorPeriod" @update:model-value="setSectorPeriod($event as SectorPeriod)" />
        </div>

        <div v-if="sectorLoading" class="text-gray-400 text-xs mb-2">読み込み中...</div>
        <template v-else>
          <div class="flex gap-4 min-w-0">

            <!-- 左: セクター騰落率 (日本→米国 上下配置, 横幅を狭く) -->
            <div class="shrink-0 space-y-3" style="width: 460px">
              <!-- 日本セクター ヒートマップ -->
              <div>
                <div class="text-xs text-gray-500 font-medium mb-1">日本</div>
                <HeatMap v-if="jpSectorData.length" :sectors="jpSectorData" />
                <div v-else class="text-gray-400 text-xs">データなし</div>
              </div>

              <!-- 米国セクター -->
              <div>
                <div class="flex items-baseline gap-1 mb-1">
                  <div class="text-xs text-gray-500 font-medium">米国</div>
                  <span v-if="usSectorData" class="text-xs text-gray-400">{{ usSectorData.date }}</span>
                </div>
                <div v-if="!usSectorData || !usSectorData.sectors?.length" class="text-gray-400 text-xs">データなし</div>
                <div v-else class="space-y-0.5">
                  <div
                    v-for="s in usSectorData.sectors"
                    :key="s.ticker"
                    class="flex items-center gap-1.5 text-xs"
                  >
                    <span class="w-10 text-gray-500 shrink-0 font-mono">{{ s.ticker }}</span>
                    <span class="w-16 text-gray-700 shrink-0 truncate">{{ s.sector }}</span>
                    <div class="flex-1 flex items-center gap-1 min-w-0">
                      <div class="flex-1 h-3 bg-gray-100 rounded overflow-hidden">
                        <div
                          class="h-full rounded transition-all"
                          :class="(s.change_pct ?? 0) >= 0 ? 'bg-green-400' : 'bg-red-400'"
                          :style="{ width: `${Math.min(Math.abs(s.change_pct ?? 0) / usSectorMaxAbs * 100, 100)}%` }"
                        />
                      </div>
                      <span
                        class="w-14 text-right font-medium shrink-0"
                        :class="(s.change_pct ?? 0) >= 0 ? 'text-green-600' : 'text-red-600'"
                      >
                        {{ s.change_pct != null ? `${s.change_pct >= 0 ? '+' : ''}${s.change_pct.toFixed(2)}%` : '—' }}
                      </span>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            <!-- 右: マーケット情報パネル -->
            <div class="flex-1 min-w-0 space-y-4 border-l border-gray-100 pl-4">

              <!-- 今日の資金フロー (日本セクター騰落上位) -->
              <div v-if="jpSectorData.length">
                <div class="flex items-center gap-1 mb-1.5">
                  <span class="w-2 h-2 rounded-sm bg-gray-400 shrink-0" />
                  <span class="text-xs font-semibold text-gray-700">今日の資金フロー</span>
                </div>
                <div class="space-y-0.5">
                  <div
                    v-for="s in topFlowSectors"
                    :key="s.sector"
                    class="flex items-center gap-2 text-sm"
                  >
                    <span class="text-gray-700 min-w-0 truncate flex-1">{{ s.sector }}</span>
                    <span
                      class="font-bold text-base shrink-0"
                      :class="s.avg_return >= 0 ? 'text-green-500' : 'text-red-500'"
                    >{{ s.avg_return >= 0 ? '↑' : '↓' }}</span>
                  </div>
                </div>
              </div>

              <!-- コモディティ -->
              <div>
                <div class="flex items-center gap-1 mb-1.5">
                  <span class="w-2 h-2 rounded-sm bg-gray-400 shrink-0" />
                  <span class="text-xs font-semibold text-gray-700">コモディティ</span>
                </div>
                <div v-if="!commoditySummary.length" class="text-gray-400 text-xs">データなし</div>
                <div v-else class="space-y-0.5">
                  <div
                    v-for="c in commoditySummary"
                    :key="c.symbol"
                    class="flex items-center gap-2 text-xs"
                  >
                    <span class="text-gray-700 w-20 shrink-0">{{ c.label }}</span>
                    <span
                      class="font-medium"
                      :class="(c.change_pct ?? 0) >= 0 ? 'text-green-600' : 'text-red-600'"
                    >
                      {{ c.change_pct != null ? `${c.change_pct >= 0 ? '+' : ''}${c.change_pct.toFixed(2)}%` : '—' }}
                    </span>
                  </div>
                </div>
              </div>

              <!-- 市場温度 -->
              <div>
                <div class="flex items-center gap-1 mb-1.5">
                  <span class="w-2 h-2 rounded-sm bg-gray-400 shrink-0" />
                  <span class="text-xs font-semibold text-gray-700">市場温度</span>
                </div>
                <div class="flex items-center gap-1.5 text-sm font-bold">
                  <span :class="marketStore.summary?.regime === 'risk_on' ? 'text-green-600' : 'text-gray-300'">Risk ON</span>
                  <span class="text-gray-400 font-normal">/</span>
                  <span :class="marketStore.summary?.regime === 'risk_off' ? 'text-red-500' : 'text-gray-300'">Risk OFF</span>
                </div>
              </div>

            </div>
          </div>
        </template>
      </div>
    </template>
    </LoadingState>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import HeatMap from "../components/overview/HeatMap.vue";
import NikkeiAreaChart from "../components/overview/NikkeiAreaChart.vue";
import SectorTrendBar from "../components/overview/SectorTrendBar.vue";
import LoadingState from "../components/shared/LoadingState.vue";
import PeriodSelector from "../components/shared/PeriodSelector.vue";
import { useApi } from "../composables/useApi";
import { useMarketStore } from "../stores/useMarketStore";
import type { NewsArticle, UsSectorPerformance, YtdHighStock } from "../types";
import { fngClass, regimeClass, returnClass, vixClass } from "../utils/colors";
import { formatDateTime, formatReturn } from "../utils/formatters";

const api = useApi();
const marketStore = useMarketStore();
const loading = ref(!marketStore.summary);
const error = ref("");
const topNews = ref<NewsArticle[]>([]);
const ytdHighs = ref<YtdHighStock[]>([]);

// 共通期間セレクタ (日本 + 米国セクター)
type SectorPeriod = "1d" | "1w" | "1m" | "3m";
const activeSectorPeriod = ref<SectorPeriod>("1d");
const sectorPeriods = [
	{ value: "1d" as const, label: "1D" },
	{ value: "1w" as const, label: "1W" },
	{ value: "1m" as const, label: "1M" },
	{ value: "3m" as const, label: "3M" },
];
const sectorLoading = ref(false);

// 日本セクター (期間別)
interface JpSectorItem {
	sector: string;
	avg_return: number;
}
const jpSectorData = ref<JpSectorItem[]>([]);

// Phase 23b: 米国セクター ETF
const usSectorData = ref<UsSectorPerformance | null>(null);

// Phase 26: コモディティサマリー (金・天然ガス・原油)
const COMMODITY_SYMBOLS = ["GC=F", "NG=F", "CL=F"];
interface CommodityItem {
	symbol: string;
	label: string;
	change_pct: number | null;
}
const commoditySummary = ref<CommodityItem[]>([]);

// 日本セクター 騰落上位 (絶対値上位5件)
const topFlowSectors = computed(() =>
	[...jpSectorData.value]
		.sort((a, b) => Math.abs(b.avg_return) - Math.abs(a.avg_return))
		.slice(0, 5),
);

const usSectorMaxAbs = computed(() => {
	if (!usSectorData.value?.sectors.length) return 1;
	const max = Math.max(
		...usSectorData.value.sectors.map((s) => Math.abs(s.change_pct ?? 0)),
	);
	return max > 0 ? max : 1;
});

function applySnapshotSectorData(period: SectorPeriod) {
	const snap = marketStore.overviewSnapshot;
	if (!snap?.sector_performance) return false;
	const jp = snap.sector_performance.jp?.[period];
	const us = snap.sector_performance.us?.[period];
	if (jp) jpSectorData.value = jp;
	if (us) usSectorData.value = us;
	return !!(jp || us);
}

async function fetchSectorData(period: SectorPeriod) {
	// スナップショットに全期間のデータが含まれているので API コールは不要
	if (applySnapshotSectorData(period)) return;

	// フォールバック: スナップショット未取得時は従来の API を呼ぶ
	sectorLoading.value = true;
	try {
		const [jpData, usData] = await Promise.all([
			api.getJpSectorPerformance(period).catch(() => []),
			api.getUsSectorPerformance(period).catch(() => null),
		]);
		jpSectorData.value = Array.isArray(jpData) ? jpData : [];
		usSectorData.value = usData;
	} finally {
		sectorLoading.value = false;
	}
}

async function setSectorPeriod(period: SectorPeriod) {
	activeSectorPeriod.value = period;
	await fetchSectorData(period);
}

onMounted(async () => {
	// コモディティサマリーを並行取得
	api
		.getCommoditiesSummary()
		.then((data: CommodityItem[]) => {
			commoditySummary.value = Array.isArray(data)
				? data.filter((c) => COMMODITY_SYMBOLS.includes(c.symbol))
				: [];
		})
		.catch(() => {});

	try {
		// スナップショット 1 本で全データを取得 (DB クエリゼロ、HTTP 1 回)
		await marketStore.fetchOverviewSnapshot();
		const snap = marketStore.overviewSnapshot;
		if (snap) {
			topNews.value = Array.isArray(snap.news)
				? [...snap.news].sort((a, b) => b.published_at.localeCompare(a.published_at)).slice(0, 5)
				: [];
			ytdHighs.value = Array.isArray(snap.ytd_highs) ? snap.ytd_highs : [];
			applySnapshotSectorData(activeSectorPeriod.value);
			loading.value = false;
			return;
		}
	} catch {
		// スナップショット未生成 (初回バッチ前) はフォールバックへ
	}

	// フォールバック: スナップショット取得失敗時は従来の個別 API
	try {
		const [, newsData, , ytdData] = await Promise.all([
			marketStore.fetchSummary(30),
			api.getNews({ limit: 5 }),
			marketStore.fetchFearIndices(),
			api.getYtdHighs(10).catch(() => []),
		]);
		topNews.value = Array.isArray(newsData)
			? [...newsData].sort((a, b) => b.published_at.localeCompare(a.published_at)).slice(0, 5)
			: [];
		ytdHighs.value = Array.isArray(ytdData) ? ytdData : [];
	} catch (e: unknown) {
		error.value = e instanceof Error ? e.message : "データ取得失敗";
	} finally {
		loading.value = false;
	}
	fetchSectorData(activeSectorPeriod.value);
});
</script>

<style scoped>
.card { @apply bg-white rounded-lg p-2 border border-gray-200 shadow-sm; }
.card-compact { @apply py-1.5 px-2; }
.label { @apply text-gray-500 text-xs leading-tight; }
.value-sm { @apply text-base font-bold leading-tight; }
</style>
