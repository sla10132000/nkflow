<template>
  <div class="space-y-3">
    <h1 class="text-xl font-bold">概要</h1>

    <div v-if="loading" class="text-gray-500">読み込み中...</div>
    <div v-else-if="error" class="text-red-600">{{ error }}</div>

    <!-- 昨日の主なニュース -->
    <div v-if="topNews.length" class="card">
      <h2 class="font-semibold mb-2 text-gray-700">
        昨日の主なニュース
        <span class="text-xs text-gray-400 ml-2 font-normal">{{ yesterdayLabel }}</span>
      </h2>
      <ul class="space-y-2">
        <li v-for="article in topNews" :key="article.id">
          <a
            :href="article.url"
            target="_blank"
            rel="noopener noreferrer"
            class="text-sm font-medium text-blue-700 hover:underline leading-snug line-clamp-2"
          >
            {{ article.title_ja ?? article.title }}
          </a>
          <div class="mt-0.5 flex items-center gap-2 text-xs text-gray-400">
            <span>{{ article.source_name ?? article.source }}</span>
            <span>{{ formatTime(article.published_at) }}</span>
            <span
              v-if="article.sentiment != null"
              :class="sentimentClass(article.sentiment)"
              class="px-1.5 py-0.5 rounded-full font-medium"
            >
              {{ article.sentiment > 0.1 ? '+' : article.sentiment < -0.1 ? '−' : '中立' }}
              {{ article.sentiment > 0.1 || article.sentiment < -0.1 ? Math.abs(article.sentiment).toFixed(1) : '' }}
            </span>
          </div>
        </li>
      </ul>
      <div class="mt-2 text-right">
        <RouterLink to="/news" class="text-xs text-blue-600 hover:underline">すべてのニュースを見る →</RouterLink>
      </div>
    </div>

    <template v-if="summary">
      <!-- 上部サマリカード -->
      <div class="grid grid-cols-2 md:grid-cols-4 gap-3">
        <div class="card">
          <div class="label">日付</div>
          <div class="value text-base">{{ summary.date }}</div>
        </div>
        <div class="card">
          <div class="label">日経終値</div>
          <div class="value">{{ summary.nikkei_close?.toLocaleString() ?? '—' }}</div>
        </div>
        <div class="card">
          <div class="label">騰落率</div>
          <div class="value" :class="returnClass(summary.nikkei_return)">
            {{ formatReturn(summary.nikkei_return) }}
          </div>
        </div>
        <div class="card">
          <div class="label">レジーム</div>
          <div class="value" :class="regimeClass(summary.regime)">{{ summary.regime ?? '—' }}</div>
        </div>
      </div>

      <!-- 上昇/下落上位 -->
      <div class="grid md:grid-cols-2 gap-3">
        <div class="card">
          <h2 class="font-semibold mb-2 text-green-600">上昇上位</h2>
          <table class="w-full text-sm">
            <thead><tr class="text-gray-500 text-left"><th>コード</th><th>名称</th><th class="text-right">騰落率</th></tr></thead>
            <tbody>
              <tr v-for="g in summary.top_gainers" :key="g.code" class="border-t border-gray-200">
                <td class="py-1">
                  <RouterLink :to="`/stock/${g.code}`" class="text-blue-600 hover:underline">{{ g.code }}</RouterLink>
                </td>
                <td class="py-1 text-gray-700 truncate max-w-[120px]">{{ g.name }}</td>
                <td class="py-1 text-right text-green-600">{{ formatReturn(g.return_rate) }}</td>
              </tr>
            </tbody>
          </table>
        </div>

        <div class="card">
          <h2 class="font-semibold mb-2 text-red-600">下落上位</h2>
          <table class="w-full text-sm">
            <thead><tr class="text-gray-500 text-left"><th>コード</th><th>名称</th><th class="text-right">騰落率</th></tr></thead>
            <tbody>
              <tr v-for="l in summary.top_losers" :key="l.code" class="border-t border-gray-200">
                <td class="py-1">
                  <RouterLink :to="`/stock/${l.code}`" class="text-blue-600 hover:underline">{{ l.code }}</RouterLink>
                </td>
                <td class="py-1 text-gray-700 truncate max-w-[120px]">{{ l.name }}</td>
                <td class="py-1 text-right text-red-600">{{ formatReturn(l.return_rate) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- セクターヒートマップ -->
      <div class="card">
        <h2 class="font-semibold mb-2">セクター騰落率</h2>
        <HeatMap v-if="sectorData.length" :sectors="sectorData" />
        <div v-else class="text-gray-500 text-sm">データなし</div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import HeatMap from "../components/charts/HeatMap.vue";
import { useApi } from "../composables/useApi";
import type { DailySummary, NewsArticle } from "../types";

const api = useApi();
const loading = ref(true);
const error = ref("");
const summary = ref<DailySummary | null>(null);
const topNews = ref<NewsArticle[]>([]);

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

onMounted(async () => {
	try {
		const [summaryData, newsData] = await Promise.all([
			api.getSummary(1),
			api.getNews({ date: yesterday, limit: 3 }),
		]);
		summary.value = Array.isArray(summaryData) ? summaryData[0] : summaryData;
		topNews.value = Array.isArray(newsData) ? newsData.slice(0, 3) : [];
	} catch (e: unknown) {
		error.value = e instanceof Error ? e.message : "データ取得失敗";
	} finally {
		loading.value = false;
	}
});
</script>

<style scoped>
.card { @apply bg-white rounded-lg p-3 border border-gray-200 shadow-sm; }
.label { @apply text-gray-500 text-xs mb-1; }
.value { @apply text-xl font-bold; }
</style>
