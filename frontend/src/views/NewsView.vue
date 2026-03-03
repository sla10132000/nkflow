<template>
  <div class="space-y-6">
    <h1 class="text-2xl font-bold">ニュース</h1>

    <!-- サマリ -->
    <div class="card">
      <h2 class="text-sm font-semibold text-gray-400 mb-3">本日のニュース (Phase 18)</h2>
      <div v-if="summaryLoading" class="text-gray-500 text-sm">読み込み中...</div>
      <div v-else-if="summary" class="flex flex-wrap gap-6 text-sm">
        <div>
          <span class="text-gray-400">合計</span>
          <span class="ml-2 font-bold text-white">{{ summary.total }} 件</span>
        </div>
        <div v-for="s in summary.sources.slice(0, 5)" :key="s.source" class="text-gray-300">
          <span class="text-gray-500">{{ s.source }}</span>
          <span class="ml-1">{{ s.count }}</span>
        </div>
      </div>
    </div>

    <!-- フィルタ -->
    <div class="card flex flex-wrap gap-4 items-end">
      <div>
        <label class="label">日付</label>
        <input v-model="filterDate" type="date" class="input" />
      </div>
      <button @click="load" class="btn-primary">絞り込み</button>
      <button @click="clearFilter" class="btn-secondary">クリア</button>
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
                {{ article.title }}
              </a>
              <div class="mt-1 flex flex-wrap gap-2 text-xs text-gray-500">
                <span>{{ article.source_name || article.source }}</span>
                <span>{{ formatDate(article.published_at) }}</span>
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
import { ref, onMounted } from 'vue'
import { useApi } from '../composables/useApi'
import type { NewsArticle, NewsSummary } from '../types'

const api = useApi()

const articles = ref<NewsArticle[]>([])
const summary = ref<NewsSummary | null>(null)
const loading = ref(false)
const summaryLoading = ref(false)
const filterDate = ref('')

async function load() {
  loading.value = true
  summaryLoading.value = true
  try {
    const params: { date?: string; limit?: number } = { limit: 50 }
    if (filterDate.value) params.date = filterDate.value

    const [arts, sum] = await Promise.all([
      api.getNews(params),
      api.getNewsSummary(filterDate.value || undefined),
    ])
    articles.value = arts
    summary.value = sum
  } finally {
    loading.value = false
    summaryLoading.value = false
  }
}

function clearFilter() {
  filterDate.value = ''
  load()
}

function formatDate(dt: string) {
  if (!dt) return ''
  return dt.replace('T', ' ').slice(0, 16)
}

function sentimentClass(s: number) {
  if (s > 0.1) return 'text-green-400'
  if (s < -0.1) return 'text-red-400'
  return 'text-gray-400'
}

function sentimentLabel(s: number) {
  if (s > 0.1) return '▲ ポジティブ'
  if (s < -0.1) return '▼ ネガティブ'
  return '— ニュートラル'
}

onMounted(load)
</script>
