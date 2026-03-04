<template>
  <div class="space-y-6">
    <h1 class="text-2xl font-bold">ニュース</h1>

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
      <div class="flex items-center gap-2">
        <input v-model="filterDate" type="date" class="input" />
      </div>
    </div>

    <!-- 記事一覧 -->
    <div class="card">
      <div v-if="loading" class="text-gray-500 text-sm">読み込み中...</div>
      <div v-else-if="articles.length === 0" class="text-gray-600 text-sm">記事なし</div>
      <div v-else class="space-y-3">
        <div
          v-for="article in articles"
          :key="article.id"
          class="border-b border-gray-800 pb-3 last:border-0"
        >
          <div class="flex items-start gap-3">
            <img
              v-if="article.image_url"
              :src="article.image_url"
              class="w-16 h-12 object-cover rounded flex-shrink-0 bg-gray-800"
              alt=""
              @error="(e: Event) => ((e.target as HTMLImageElement).style.display = 'none')"
            />
            <div class="flex-1 min-w-0">
              <a
                :href="article.url"
                target="_blank"
                rel="noopener noreferrer"
                class="text-sm font-medium text-blue-400 hover:text-blue-300 line-clamp-2"
              >
                {{ article.title_ja ?? article.title }}
              </a>
              <div class="mt-1 flex flex-wrap gap-2 text-xs text-gray-500">
                <span>{{ article.source_name || article.source }}</span>
                <span :title="formatDateFull(article.published_at)">{{ formatDateRelative(article.published_at) }}</span>
                <span v-if="article.sentiment !== null" :class="sentimentClass(article.sentiment)">
                  {{ sentimentLabel(article.sentiment) }}
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { useApi } from "../composables/useApi";
import type { NewsArticle } from "../types";

const api = useApi();

const articles = ref<NewsArticle[]>([]);
const loading = ref(false);

function todayJst() {
	return new Date().toLocaleDateString("sv-SE", { timeZone: "Asia/Tokyo" });
}

function daysAgoJst(days: number) {
	const d = new Date();
	d.setDate(d.getDate() - days);
	return d.toLocaleDateString("sv-SE", { timeZone: "Asia/Tokyo" });
}

const filterDate = ref(todayJst());

const datePresets = computed(() => [
	{ label: "今日", value: todayJst() },
	{ label: "昨日", value: daysAgoJst(1) },
	{ label: "2日前", value: daysAgoJst(2) },
	{ label: "1週間", value: daysAgoJst(7) },
]);

async function load() {
	loading.value = true;
	try {
		const params: { date?: string; limit?: number } = { limit: 50 };
		if (filterDate.value) params.date = filterDate.value;
		articles.value = await api.getNews(params);
	} finally {
		loading.value = false;
	}
}

function formatDateRelative(dt: string) {
	if (!dt) return "";
	const now = new Date();
	const date = new Date(dt);
	const diffMs = now.getTime() - date.getTime();
	const diffMin = Math.floor(diffMs / 60000);
	const diffHour = Math.floor(diffMs / 3600000);

	if (diffMin < 1) return "たった今";
	if (diffMin < 60) return `${diffMin}分前`;
	if (diffHour < 24) return `${diffHour}時間前`;

	const diffDay = Math.floor(diffMs / 86400000);
	const timeStr = date.toLocaleTimeString("ja-JP", {
		timeZone: "Asia/Tokyo",
		hour: "2-digit",
		minute: "2-digit",
	});

	if (diffDay === 1) return `昨日 ${timeStr}`;
	if (diffDay < 7) return `${diffDay}日前 ${timeStr}`;

	return date.toLocaleDateString("ja-JP", {
		timeZone: "Asia/Tokyo",
		month: "numeric",
		day: "numeric",
	}) + ` ${timeStr}`;
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

function sentimentClass(s: number) {
	if (s > 0.1) return "text-green-400";
	if (s < -0.1) return "text-red-400";
	return "text-gray-400";
}

function sentimentLabel(s: number) {
	if (s > 0.1) return "▲ ポジティブ";
	if (s < -0.1) return "▼ ネガティブ";
	return "— ニュートラル";
}

watch(filterDate, load);
onMounted(load);
</script>
