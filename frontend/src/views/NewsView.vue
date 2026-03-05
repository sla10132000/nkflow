<template>
  <div class="space-y-3">
    <h1 class="text-xl font-bold">ニュース</h1>

    <!-- フィルタ -->
    <div class="card flex flex-wrap gap-3 items-center">
      <button
        v-for="preset in datePresets"
        :key="preset.label"
        :class="filterDate === preset.value ? 'btn-primary' : 'btn-secondary'"
        @click="filterDate = preset.value"
      >
        {{ preset.label }}
      </button>
      <input v-model="filterDate" type="date" class="input" />
    </div>

    <!-- サマリ -->
    <div v-if="summary" class="card">
      <div class="flex flex-wrap gap-4 text-sm">
        <span class="font-medium">合計: {{ summary.total }}件</span>
        <template v-if="summary.sentiment_dist">
          <span class="text-green-600">▲ {{ summary.sentiment_dist.positive }}</span>
          <span class="text-red-600">▼ {{ summary.sentiment_dist.negative }}</span>
          <span class="text-gray-400">— {{ summary.sentiment_dist.neutral }}</span>
        </template>
      </div>
      <div v-if="summary.categories && summary.categories.length > 0" class="mt-2 flex flex-wrap gap-1.5">
        <button
          v-for="cat in summary.categories"
          :key="cat.category"
          :class="filterCategory === cat.category ? 'badge-active' : 'badge'"
          @click="toggleCategory(cat.category)"
        >
          {{ cat.category }} {{ cat.count }}
        </button>
      </div>
    </div>

    <!-- コンテンツ -->
    <div class="card">
      <div v-if="loading" class="text-gray-500 text-sm">読み込み中...</div>
      <div v-else-if="articles.length === 0" class="text-gray-600 text-sm">記事なし</div>

      <template v-else>
        <div class="space-y-1">
          <div
            v-for="article in articles"
            :key="article.id"
            class="flex items-start gap-2 border-b border-gray-100 pb-1.5 last:border-0"
          >
            <img
              v-if="article.image_url"
              :src="article.image_url"
              class="w-10 h-8 object-cover rounded flex-shrink-0 bg-gray-100"
              alt=""
              @error="(e: Event) => ((e.target as HTMLImageElement).style.display = 'none')"
            />
            <div class="flex-1 min-w-0">
              <div class="flex items-center gap-1.5 flex-wrap">
                <span v-if="article.category" :class="['cat-badge', catColor(article.category)]">
                  {{ article.category }}
                </span>
                <a
                  :href="article.url"
                  target="_blank"
                  rel="noopener noreferrer"
                  class="text-sm font-medium text-blue-400 hover:text-blue-300 line-clamp-1"
                >
                  {{ article.title_ja ?? article.title }}
                </a>
                <span v-if="article.sentiment && Math.abs(article.sentiment) > 0.1"
                  :class="article.sentiment > 0 ? 'text-green-400 text-xs' : 'text-red-400 text-xs'"
                >
                  {{ article.sentiment > 0 ? '▲' : '▼' }}{{ article.sentiment.toFixed(1) }}
                </span>
              </div>
              <div class="mt-0.5 flex flex-wrap gap-2 text-xs text-gray-500">
                <span>{{ article.source_name || article.source }}</span>
                <span :title="formatDateFull(article.published_at)">{{ formatTime(article.published_at) }}</span>
                <span v-if="article.tickers" class="text-blue-400">{{ article.tickers }}</span>
              </div>
            </div>
          </div>
        </div>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { useApi } from "../composables/useApi";
import type { NewsArticle, NewsSummary } from "../types";

const api = useApi();

const articles = ref<NewsArticle[]>([]);
const summary = ref<NewsSummary | null>(null);
const loading = ref(false);
const filterDate = ref("");
const filterCategory = ref("");

function todayJst() {
	return new Date().toLocaleDateString("sv-SE", { timeZone: "Asia/Tokyo" });
}

function daysAgoJst(days: number) {
	const d = new Date();
	d.setDate(d.getDate() - days);
	return d.toLocaleDateString("sv-SE", { timeZone: "Asia/Tokyo" });
}

const datePresets = computed(() => [
	{ label: "最新", value: "" },
	{ label: "今日", value: todayJst() },
	{ label: "昨日", value: daysAgoJst(1) },
	{ label: "2日前", value: daysAgoJst(2) },
	{ label: "1週間", value: daysAgoJst(7) },
]);

function toggleCategory(cat: string) {
	filterCategory.value = filterCategory.value === cat ? "" : cat;
}

async function load() {
	loading.value = true;
	try {
		const params: { date?: string; category?: string; limit?: number } = {
			limit: 100,
		};
		if (filterDate.value) params.date = filterDate.value;
		if (filterCategory.value) params.category = filterCategory.value;

		const [arts, sum] = await Promise.all([
			api.getNews(params),
			api.getNewsSummary(filterDate.value || undefined),
		]);
		articles.value = arts;
		summary.value = sum;
	} finally {
		loading.value = false;
	}
}


function formatTime(dt: string) {
	if (!dt) return "";
	return new Date(dt).toLocaleString("ja-JP", {
		timeZone: "Asia/Tokyo",
		month: "2-digit",
		day: "2-digit",
		hour: "2-digit",
		minute: "2-digit",
	});
}

function formatDateFull(dt: string) {
	if (!dt) return "";
	return new Date(dt).toLocaleString("ja-JP", {
		timeZone: "Asia/Tokyo",
		year: "numeric",
		month: "2-digit",
		day: "2-digit",
		hour: "2-digit",
		minute: "2-digit",
	});
}

const CAT_COLORS: Record<string, string> = {
	決算: "bg-purple-100 text-purple-700",
	金融政策: "bg-blue-100 text-blue-700",
	為替: "bg-cyan-100 text-cyan-700",
	米国市場: "bg-indigo-100 text-indigo-700",
	半導体: "bg-orange-100 text-orange-700",
	AI: "bg-pink-100 text-pink-700",
	エネルギー: "bg-amber-100 text-amber-700",
	地政学: "bg-red-100 text-red-700",
};

function catColor(cat: string | null): string {
	return CAT_COLORS[cat || ""] || "bg-gray-100 text-gray-600";
}

watch(filterDate, () => {
	filterCategory.value = "";
	load();
});
watch(filterCategory, load);
onMounted(load);
</script>

<style scoped>
.card { @apply bg-white rounded-lg p-3 border border-gray-200 shadow-sm; }
.btn-primary { @apply bg-blue-600 text-white px-3 py-1 rounded text-sm; }
.btn-secondary { @apply bg-gray-100 text-gray-700 px-3 py-1 rounded text-sm; }
.input { @apply bg-white border border-gray-300 rounded px-2 py-1 text-sm; }
.badge { @apply text-xs px-2 py-0.5 rounded-full bg-gray-100 text-gray-600 cursor-pointer hover:bg-gray-200; }
.badge-active { @apply text-xs px-2 py-0.5 rounded-full bg-blue-600 text-white cursor-pointer; }
.tab { @apply px-3 py-1.5 text-sm text-gray-500 hover:text-gray-700 border-b-2 border-transparent; }
.tab-active { @apply px-3 py-1.5 text-sm text-blue-600 font-medium border-b-2 border-blue-600; }
.cat-badge { @apply text-xs px-1.5 py-0.5 rounded-full; }
</style>
