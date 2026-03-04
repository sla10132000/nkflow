<template>
  <div class="space-y-2">
    <h1 class="text-lg font-bold">概要</h1>

    <div v-if="loading" class="text-gray-500">読み込み中...</div>
    <div v-else-if="error" class="text-red-600">{{ error }}</div>

    <!-- 昨日の主なニュース -->
    <div v-if="topNews.length" class="card">
      <div class="flex items-center justify-between mb-1">
        <h2 class="text-sm font-semibold text-gray-700">
          昨日の主なニュース
          <span class="text-xs text-gray-400 ml-1 font-normal">{{ yesterdayLabel }}</span>
        </h2>
        <RouterLink to="/news" class="text-xs text-blue-600 hover:underline whitespace-nowrap">すべて見る →</RouterLink>
      </div>
      <ul class="space-y-1">
        <li v-for="article in topNews" :key="article.id" class="flex items-baseline gap-2">
          <a
            :href="article.url"
            target="_blank"
            rel="noopener noreferrer"
            class="text-sm text-blue-700 hover:underline leading-tight line-clamp-1 flex-1 min-w-0"
          >
            {{ article.title_ja ?? article.title }}
          </a>
          <span class="text-xs text-gray-400 whitespace-nowrap">
            {{ article.source_name ?? article.source }} {{ formatTime(article.published_at) }}
          </span>
        </li>
      </ul>
    </div>

    <template v-if="summary">
      <!-- サマリ + 恐怖指数を1行に統合 -->
      <div class="grid grid-cols-3 md:grid-cols-6 gap-2">
        <div class="card card-compact">
          <div class="label">日付</div>
          <div class="value-sm">{{ summary.date }}</div>
        </div>
        <div class="card card-compact">
          <div class="label">日経終値</div>
          <div class="value-sm">{{ summary.nikkei_close?.toLocaleString() ?? '—' }}</div>
        </div>
        <div class="card card-compact">
          <div class="label">騰落率</div>
          <div class="value-sm" :class="returnClass(summary.nikkei_return)">
            {{ formatReturn(summary.nikkei_return) }}
          </div>
        </div>
        <div class="card card-compact">
          <div class="label">レジーム</div>
          <div class="value-sm" :class="regimeClass(summary.regime)">{{ summary.regime ?? '—' }}</div>
        </div>
        <!-- VIX -->
        <div v-if="fearIndices" class="card card-compact">
          <div class="label">VIX</div>
          <template v-if="fearIndices.vix">
            <div class="value-sm" :class="vixClass(fearIndices.vix.value)">
              {{ fearIndices.vix.value.toFixed(1) }}
              <span v-if="fearIndices.vix.change_pct != null" class="text-xs font-normal" :class="fearIndices.vix.change_pct >= 0 ? 'text-red-500' : 'text-green-500'">
                {{ fearIndices.vix.change_pct >= 0 ? '+' : '' }}{{ fearIndices.vix.change_pct.toFixed(1) }}%
              </span>
            </div>
          </template>
          <div v-else class="text-gray-400 text-xs">—</div>
        </div>
        <!-- BTC Fear & Greed -->
        <div v-if="fearIndices" class="card card-compact">
          <div class="label">Fear&amp;Greed</div>
          <template v-if="fearIndices.btc_fear_greed">
            <div class="value-sm" :class="fngClass(fearIndices.btc_fear_greed.value)">
              {{ fearIndices.btc_fear_greed.value }}
              <span class="text-xs font-normal">{{ fearIndices.btc_fear_greed.classification }}</span>
            </div>
          </template>
          <div v-else class="text-gray-400 text-xs">—</div>
        </div>
      </div>

      <!-- 上昇/下落上位 -->
      <div class="grid md:grid-cols-2 gap-2">
        <div class="card">
          <h2 class="text-sm font-semibold mb-1 text-green-600">上昇上位</h2>
          <table class="w-full text-xs">
            <thead><tr class="text-gray-500 text-left"><th class="pb-0.5">コード</th><th class="pb-0.5">名称</th><th class="pb-0.5 text-right">騰落率</th></tr></thead>
            <tbody>
              <tr v-for="g in summary.top_gainers" :key="g.code" class="border-t border-gray-100">
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
              <tr v-for="l in summary.top_losers" :key="l.code" class="border-t border-gray-100">
                <td class="py-0.5">
                  <RouterLink :to="`/stock/${l.code}`" class="text-blue-600 hover:underline">{{ l.code }}</RouterLink>
                </td>
                <td class="py-0.5 text-gray-700 truncate max-w-[140px]">{{ l.name }}</td>
                <td class="py-0.5 text-right text-red-600 font-medium">{{ formatReturn(l.return_rate) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- セクターヒートマップ -->
      <div class="card">
        <h2 class="text-sm font-semibold mb-1">セクター騰落率</h2>
        <HeatMap v-if="sectorData.length" :sectors="sectorData" />
        <div v-else class="text-gray-500 text-xs">データなし</div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import HeatMap from "../components/charts/HeatMap.vue";
import { useApi } from "../composables/useApi";
import type { DailySummary, FearIndices, NewsArticle } from "../types";

const api = useApi();
const loading = ref(true);
const error = ref("");
const summary = ref<DailySummary | null>(null);
const topNews = ref<NewsArticle[]>([]);
const fearIndices = ref<FearIndices | null>(null);

// JST で昨日の日付を求める
function getYesterdayJST(): string {
	const now = new Date();
	const jstOffset = 9 * 60 * 60 * 1000;
	const jstNow = new Date(now.getTime() + jstOffset);
	jstNow.setUTCDate(jstNow.getUTCDate() - 1);
	return jstNow.toISOString().slice(0, 10);
}

const yesterday = getYesterdayJST();
const yesterdayLabel = yesterday;

const sectorData = computed(() => {
	if (!summary.value?.sector_rotation) return [];
	try {
		const data =
			typeof summary.value.sector_rotation === "string"
				? JSON.parse(summary.value.sector_rotation)
				: summary.value.sector_rotation;
		return Array.isArray(data) ? data : [];
	} catch {
		return [];
	}
});

function formatReturn(r: number | null | undefined) {
	if (r == null) return "—";
	return `${(r >= 0 ? "+" : "") + (r * 100).toFixed(2)}%`;
}

function returnClass(r: number | null | undefined) {
	if (r == null) return "";
	return r >= 0 ? "text-green-600" : "text-red-600";
}

function regimeClass(regime: string | null | undefined) {
	if (regime === "risk_on") return "text-green-600";
	if (regime === "risk_off") return "text-red-600";
	return "text-amber-600";
}

function formatTime(publishedAt: string): string {
	try {
		const d = new Date(publishedAt);
		return d.toLocaleTimeString("ja-JP", {
			hour: "2-digit",
			minute: "2-digit",
			timeZone: "Asia/Tokyo",
		});
	} catch {
		return "";
	}
}

function sentimentClass(s: number): string {
	if (s > 0.1) return "bg-green-100 text-green-700";
	if (s < -0.1) return "bg-red-100 text-red-700";
	return "bg-gray-100 text-gray-500";
}

// VIX: 低い = 安心(緑), 高い = 危険(赤)
function vixClass(value: number): string {
	if (value < 20) return "text-green-600";
	if (value < 30) return "text-amber-500";
	return "text-red-600";
}

// BTC Fear & Greed: 高い(Greed) = 緑, 低い(Fear) = 赤
function fngClass(value: number): string {
	if (value > 60) return "text-green-600";
	if (value > 40) return "text-amber-500";
	return "text-red-600";
}

onMounted(async () => {
	try {
		const [summaryData, newsData, fearData] = await Promise.all([
			api.getSummary(1),
			api.getNews({ date: yesterday, limit: 3 }),
			api.getFearIndices().catch(() => null),
		]);
		summary.value = Array.isArray(summaryData) ? summaryData[0] : summaryData;
		topNews.value = Array.isArray(newsData) ? newsData.slice(0, 3) : [];
		fearIndices.value = fearData;
	} catch (e: unknown) {
		error.value = e instanceof Error ? e.message : "データ取得失敗";
	} finally {
		loading.value = false;
	}
});
</script>

<style scoped>
.card { @apply bg-white rounded-lg p-2 border border-gray-200 shadow-sm; }
.card-compact { @apply py-1.5 px-2; }
.label { @apply text-gray-500 text-xs leading-tight; }
.value-sm { @apply text-base font-bold leading-tight; }
</style>
