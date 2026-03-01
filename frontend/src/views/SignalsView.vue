<template>
  <div class="space-y-6">
    <h1 class="text-2xl font-bold">予測シグナル</h1>

    <!-- 的中率サマリ -->
    <div class="card">
      <h2 class="text-sm font-semibold text-gray-400 mb-3">的中率サマリ (Phase 11)</h2>
      <div v-if="accuracyLoading" class="text-gray-500 text-sm">読み込み中...</div>
      <div v-else-if="accuracy.length === 0" class="text-gray-600 text-sm">データなし</div>
      <div v-else class="overflow-x-auto">
        <table class="text-xs w-full">
          <thead>
            <tr class="text-gray-500 border-b border-gray-800">
              <th class="text-left py-1 pr-4">シグナルタイプ</th>
              <th class="text-right pr-4">5日</th>
              <th class="text-right pr-4">10日</th>
              <th class="text-right">20日</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in accuracyTable" :key="row.signal_type" class="border-b border-gray-800/50">
              <td class="py-1 pr-4">
                <span class="badge" :class="typeClass(row.signal_type)">{{ row.signal_type }}</span>
              </td>
              <td class="text-right pr-4" :class="hitRateColor(row.h5?.hit_rate)">
                {{ row.h5 ? (row.h5.hit_rate * 100).toFixed(0) + '%' : '—' }}
                <span v-if="row.h5" class="text-gray-600">({{ row.h5.total_signals }})</span>
              </td>
              <td class="text-right pr-4" :class="hitRateColor(row.h10?.hit_rate)">
                {{ row.h10 ? (row.h10.hit_rate * 100).toFixed(0) + '%' : '—' }}
                <span v-if="row.h10" class="text-gray-600">({{ row.h10.total_signals }})</span>
              </td>
              <td class="text-right" :class="hitRateColor(row.h20?.hit_rate)">
                {{ row.h20 ? (row.h20.hit_rate * 100).toFixed(0) + '%' : '—' }}
                <span v-if="row.h20" class="text-gray-600">({{ row.h20.total_signals }})</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- フィルタ -->
    <div class="card flex flex-wrap gap-4 items-end">
      <div>
        <label class="label">日付</label>
        <input v-model="filters.date" type="date" class="input" />
      </div>
      <div>
        <label class="label">タイプ</label>
        <select v-model="filters.type" class="input">
          <option value="">すべて</option>
          <option value="causality_chain">causality_chain</option>
          <option value="fund_flow">fund_flow</option>
          <option value="regime_shift">regime_shift</option>
          <option value="cluster_breakout">cluster_breakout</option>
          <option value="lead_lag">lead_lag</option>
        </select>
      </div>
      <div>
        <label class="label">方向</label>
        <select v-model="filters.direction" class="input">
          <option value="">すべて</option>
          <option value="bullish">bullish</option>
          <option value="bearish">bearish</option>
        </select>
      </div>
      <div>
        <label class="label">最低 confidence</label>
        <input v-model="filters.min_confidence" type="number" min="0" max="1" step="0.1" class="input w-24" />
      </div>
      <button @click="loadSignals" class="btn-primary">検索</button>
    </div>

    <div v-if="loading" class="text-gray-400">読み込み中...</div>
    <div v-else-if="error" class="text-red-400">{{ error }}</div>

    <template v-else>
      <div class="text-sm text-gray-500">{{ signals.length }} 件</div>

      <div class="space-y-2">
        <div
          v-for="s in signals"
          :key="s.id"
          class="card"
        >
          <div class="flex flex-wrap items-center gap-3 mb-2">
            <span class="text-gray-400 text-sm">{{ s.date }}</span>
            <span class="badge" :class="typeClass(s.signal_type)">{{ s.signal_type }}</span>
            <span class="badge" :class="s.direction === 'bullish' ? 'badge-green' : 'badge-red'">
              {{ s.direction }}
            </span>
            <span class="text-sm text-gray-300">
              confidence: <span class="font-bold">{{ (s.confidence * 100).toFixed(1) }}%</span>
            </span>
            <RouterLink v-if="s.code" :to="`/stock/${s.code}`" class="text-blue-400 text-sm hover:underline ml-auto">
              {{ s.code }}
            </RouterLink>
            <span v-if="s.sector" class="text-gray-500 text-sm">{{ s.sector }}</span>
          </div>

          <!-- reasoning 展開 -->
          <button @click="toggleReasoning(s.id)" class="text-xs text-gray-500 hover:text-gray-300 transition-colors">
            {{ expanded.has(s.id) ? '▼ reasoning を閉じる' : '▶ reasoning を展開' }}
          </button>
          <pre v-if="expanded.has(s.id)" class="mt-2 text-xs bg-gray-950 rounded p-3 overflow-x-auto text-gray-300">{{ formatReasoning(s.reasoning) }}</pre>
        </div>
      </div>

      <div v-if="signals.length === 0" class="text-gray-500">シグナルなし</div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { useApi } from '../composables/useApi'
import type { Signal } from '../types'

interface AccuracyRow {
  signal_type: string
  horizon_days: number
  total_signals: number
  hits: number
  hit_rate: number
  avg_return: number | null
}

interface AccuracyTableRow {
  signal_type: string
  h5?: AccuracyRow
  h10?: AccuracyRow
  h20?: AccuracyRow
}

const api = useApi()
const loading = ref(false)
const error = ref('')
const signals = ref<Signal[]>([])
const expanded = ref(new Set<number>())

const accuracyLoading = ref(false)
const accuracy = ref<AccuracyRow[]>([])

const accuracyTable = computed<AccuracyTableRow[]>(() => {
  const map = new Map<string, AccuracyTableRow>()
  for (const row of accuracy.value) {
    if (!map.has(row.signal_type)) map.set(row.signal_type, { signal_type: row.signal_type })
    const entry = map.get(row.signal_type)!
    if (row.horizon_days === 5)  entry.h5  = row
    if (row.horizon_days === 10) entry.h10 = row
    if (row.horizon_days === 20) entry.h20 = row
  }
  return Array.from(map.values())
})

async function loadAccuracy() {
  accuracyLoading.value = true
  try {
    accuracy.value = await api.getAccuracy()
  } catch {
    // 取得失敗時はサマリを非表示にするだけ
  } finally {
    accuracyLoading.value = false
  }
}

function hitRateColor(rate?: number) {
  if (rate === undefined) return ''
  if (rate >= 0.6) return 'text-green-400'
  if (rate >= 0.5) return 'text-gray-300'
  return 'text-red-400'
}

const filters = reactive({
  date: '',
  type: '',
  direction: '',
  min_confidence: '',
})

async function loadSignals() {
  loading.value = true
  error.value = ''
  const params: Record<string, string> = {}
  if (filters.date) params.date = filters.date
  if (filters.type) params.type = filters.type
  if (filters.direction) params.direction = filters.direction
  if (filters.min_confidence) params.min_confidence = filters.min_confidence
  try {
    signals.value = await api.getSignals(params)
  } catch (e: unknown) {
    error.value = e instanceof Error ? e.message : 'データ取得失敗'
  } finally {
    loading.value = false
  }
}

function toggleReasoning(id: number) {
  if (expanded.value.has(id)) expanded.value.delete(id)
  else expanded.value.add(id)
}

function formatReasoning(r: unknown) {
  if (typeof r === 'string') {
    try { return JSON.stringify(JSON.parse(r), null, 2) } catch { return r }
  }
  return JSON.stringify(r, null, 2)
}

function typeClass(t: string) {
  const map: Record<string, string> = {
    causality_chain: 'badge-blue',
    fund_flow: 'badge-yellow',
    regime_shift: 'badge-purple',
    cluster_breakout: 'badge-orange',
    lead_lag: 'badge-teal',
  }
  return map[t] ?? 'badge-gray'
}

onMounted(() => {
  loadSignals()
  loadAccuracy()
})
</script>

<style scoped>
.card { @apply bg-gray-900 rounded-lg p-4 border border-gray-800; }
.label { @apply block text-xs text-gray-500 mb-1; }
.input { @apply bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-sm focus:outline-none focus:border-blue-500; }
.btn-primary { @apply bg-blue-600 hover:bg-blue-500 text-white px-4 py-1.5 rounded text-sm transition-colors; }
.badge { @apply px-2 py-0.5 rounded text-xs font-medium; }
.badge-green { @apply bg-green-900/60 text-green-300; }
.badge-red { @apply bg-red-900/60 text-red-300; }
.badge-blue { @apply bg-blue-900/60 text-blue-300; }
.badge-yellow { @apply bg-yellow-900/60 text-yellow-300; }
.badge-purple { @apply bg-purple-900/60 text-purple-300; }
.badge-orange { @apply bg-orange-900/60 text-orange-300; }
.badge-teal { @apply bg-teal-900/60 text-teal-300; }
.badge-gray { @apply bg-gray-800 text-gray-300; }
</style>
