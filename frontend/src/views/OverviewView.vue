<template>
  <div class="space-y-6">
    <h1 class="text-2xl font-bold">概要</h1>

    <div v-if="loading" class="text-gray-400">読み込み中...</div>
    <div v-else-if="error" class="text-red-400">{{ error }}</div>

    <template v-else-if="summary">
      <!-- 上部サマリカード -->
      <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
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

      <!-- シグナル件数 -->
      <div class="card flex items-center justify-between">
        <span class="text-gray-400">アクティブシグナル</span>
        <RouterLink to="/signals" class="text-blue-400 font-bold text-xl hover:underline">
          {{ summary.active_signals }} 件
        </RouterLink>
      </div>

      <!-- 上昇/下落上位 -->
      <div class="grid md:grid-cols-2 gap-4">
        <div class="card">
          <h2 class="font-semibold mb-3 text-green-400">上昇上位</h2>
          <table class="w-full text-sm">
            <thead><tr class="text-gray-500 text-left"><th>コード</th><th>名称</th><th class="text-right">騰落率</th></tr></thead>
            <tbody>
              <tr v-for="g in summary.top_gainers" :key="g.code" class="border-t border-gray-800">
                <td class="py-1">
                  <RouterLink :to="`/stock/${g.code}`" class="text-blue-400 hover:underline">{{ g.code }}</RouterLink>
                </td>
                <td class="py-1 text-gray-300 truncate max-w-[120px]">{{ g.name }}</td>
                <td class="py-1 text-right text-green-400">{{ formatReturn(g.return_rate) }}</td>
              </tr>
            </tbody>
          </table>
        </div>

        <div class="card">
          <h2 class="font-semibold mb-3 text-red-400">下落上位</h2>
          <table class="w-full text-sm">
            <thead><tr class="text-gray-500 text-left"><th>コード</th><th>名称</th><th class="text-right">騰落率</th></tr></thead>
            <tbody>
              <tr v-for="l in summary.top_losers" :key="l.code" class="border-t border-gray-800">
                <td class="py-1">
                  <RouterLink :to="`/stock/${l.code}`" class="text-blue-400 hover:underline">{{ l.code }}</RouterLink>
                </td>
                <td class="py-1 text-gray-300 truncate max-w-[120px]">{{ l.name }}</td>
                <td class="py-1 text-right text-red-400">{{ formatReturn(l.return_rate) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- セクターヒートマップ -->
      <div class="card">
        <h2 class="font-semibold mb-3">セクター騰落率</h2>
        <HeatMap v-if="sectorData.length" :sectors="sectorData" />
        <div v-else class="text-gray-500 text-sm">データなし</div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useApi } from '../composables/useApi'
import HeatMap from '../components/charts/HeatMap.vue'
import type { DailySummary } from '../types'

const api = useApi()
const loading = ref(true)
const error = ref('')
const summary = ref<DailySummary | null>(null)

const sectorData = computed(() => {
  if (!summary.value?.sector_rotation) return []
  try {
    const data = typeof summary.value.sector_rotation === 'string'
      ? JSON.parse(summary.value.sector_rotation)
      : summary.value.sector_rotation
    return Array.isArray(data) ? data : []
  } catch { return [] }
})

function formatReturn(r: number | null | undefined) {
  if (r == null) return '—'
  return (r >= 0 ? '+' : '') + (r * 100).toFixed(2) + '%'
}

function returnClass(r: number | null | undefined) {
  if (r == null) return ''
  return r >= 0 ? 'text-green-400' : 'text-red-400'
}

function regimeClass(regime: string | null | undefined) {
  if (regime === 'risk_on') return 'text-green-400'
  if (regime === 'risk_off') return 'text-red-400'
  return 'text-yellow-400'
}

onMounted(async () => {
  try {
    const data = await api.getSummary(1)
    summary.value = Array.isArray(data) ? data[0] : data
  } catch (e: unknown) {
    error.value = e instanceof Error ? e.message : 'データ取得失敗'
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.card { @apply bg-gray-900 rounded-lg p-4 border border-gray-800; }
.label { @apply text-gray-500 text-xs mb-1; }
.value { @apply text-xl font-bold; }
</style>
