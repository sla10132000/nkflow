<template>
  <div class="space-y-4">
    <h1 class="text-2xl font-bold">ネットワーク可視化</h1>

    <!-- コントロール -->
    <div class="flex flex-wrap gap-3 items-center bg-gray-900 p-3 rounded-lg border border-gray-800">
      <!-- モード切替 -->
      <div class="flex gap-2">
        <button
          v-for="m in modes"
          :key="m.value"
          @click="setMode(m.value)"
          class="btn-tab"
          :class="{ 'btn-tab-active': mode === m.value }"
        >{{ m.label }}</button>
      </div>

      <!-- 相関 / 因果: 期間 + 閾値 -->
      <template v-if="mode !== 'fund_flow'">
        <div class="flex gap-2 ml-4">
          <button
            v-for="p in periods"
            :key="p"
            @click="setPeriod(p)"
            class="btn-tab"
            :class="{ 'btn-tab-active': period === p }"
          >{{ p }}</button>
        </div>
        <div class="flex items-center gap-2 ml-auto">
          <label class="text-sm text-gray-400">閾値:</label>
          <input
            v-model="threshold"
            @change="loadNetwork"
            type="range" min="0.3" max="0.9" step="0.05"
            class="w-24 accent-blue-500"
          />
          <span class="text-sm text-gray-300 w-10">{{ threshold }}</span>
        </div>
      </template>

      <!-- 資金フロー: 絞り込み方法 + 対応する入力 -->
      <template v-else>
        <!-- 絞り込み方法セレクタ -->
        <div class="flex ml-4 border border-gray-700 rounded overflow-hidden text-xs">
          <button
            v-for="ft in fundFlowFilters"
            :key="ft.value"
            @click="setFundFlowFilter(ft.value)"
            class="px-3 py-1 transition-colors"
            :class="fundFlowFilter === ft.value ? 'bg-blue-600 text-white' : 'text-gray-400 hover:text-white'"
          >{{ ft.label }}</button>
        </div>

        <!-- 期間 -->
        <div v-if="fundFlowFilter === 'period'" class="flex gap-2">
          <button
            v-for="p in periods"
            :key="p"
            @click="setPeriod(p)"
            class="btn-tab"
            :class="{ 'btn-tab-active': period === p }"
          >{{ p }}</button>
        </div>

        <!-- 範囲 -->
        <template v-else-if="fundFlowFilter === 'range'">
          <input
            v-model="dateFrom"
            @change="loadNetwork"
            type="date"
            class="bg-gray-800 border border-gray-700 rounded px-2 py-1 text-sm text-gray-300"
          />
          <span class="text-gray-500 text-sm">〜</span>
          <input
            v-model="dateTo"
            @change="loadNetwork"
            type="date"
            class="bg-gray-800 border border-gray-700 rounded px-2 py-1 text-sm text-gray-300"
          />
        </template>

        <!-- 日付 -->
        <template v-else-if="fundFlowFilter === 'date'">
          <input
            v-model="dateSingle"
            @change="loadNetwork"
            type="date"
            class="bg-gray-800 border border-gray-700 rounded px-2 py-1 text-sm text-gray-300"
          />
        </template>
      </template>
    </div>

    <!-- サイドパネル + グラフ -->
    <div class="flex gap-4 h-[600px]">
      <div class="flex-1 bg-gray-900 rounded-lg border border-gray-800 overflow-hidden">
        <div v-if="loading" class="flex items-center justify-center h-full text-gray-400">読み込み中...</div>
        <div v-else-if="error" class="flex items-center justify-center h-full text-red-400">{{ error }}</div>
        <GraphView
          v-else-if="networkData && networkData.nodes.length > 0"
          :data="networkData"
          :directed="mode === 'causality' || mode === 'fund_flow'"
          @node-click="onNodeClick"
          class="w-full h-full"
        />
        <div v-else class="flex items-center justify-center h-full text-gray-500">
          <span v-if="mode === 'fund_flow'">
            該当期間に資金フローなし（セクター間で出来高・騰落率の乖離が条件未満）
          </span>
          <span v-else>データなし</span>
        </div>
      </div>

      <!-- 詳細サイドパネル -->
      <div v-if="selectedNode" class="w-60 bg-gray-900 rounded-lg border border-gray-800 p-4 overflow-y-auto">
        <h3 class="font-semibold mb-2">{{ selectedNode }}</h3>
        <RouterLink :to="`/stock/${selectedNode}`" class="text-blue-400 text-sm hover:underline">詳細を見る →</RouterLink>
        <div class="mt-3 text-xs text-gray-400">
          <p>接続エッジ数: {{ connectedEdges }}</p>
        </div>
      </div>
    </div>

    <!-- 凡例 -->
    <div class="text-xs text-gray-500">
      ノード: 銘柄 (色=セクター) / エッジ太さ: {{ mode === 'causality' ? 'F統計量' : '相関係数' }}
      <span v-if="mode === 'causality'"> / 矢印: 因果の方向</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useApi } from '../composables/useApi'
import GraphView from '../components/network/GraphView.vue'
import type { NetworkData } from '../types'

const api = useApi()
const loading = ref(false)
const error = ref('')
const networkData = ref<NetworkData | null>(null)
const selectedNode = ref<string | null>(null)
const mode = ref('correlation')
const period = ref('20d')
const threshold = ref(0.5)
const fundFlowFilter = ref<'period' | 'range' | 'date'>('period')
const dateFrom = ref('')
const dateTo = ref('')
const dateSingle = ref('')

const modes = [
  { value: 'correlation', label: '相関' },
  { value: 'causality',   label: '因果' },
  { value: 'fund_flow',   label: '資金フロー' },
]
const periods = ['20d', '60d', '120d']
const fundFlowFilters = [
  { value: 'period', label: '期間' },
  { value: 'range',  label: '範囲' },
  { value: 'date',   label: '日付' },
]

/** "20d" → { from: 'YYYY-MM-DD', to: 'YYYY-MM-DD' } (カレンダー日で近似) */
function periodToDateRange(p: string): { from: string; to: string } {
  const days = parseInt(p) * 1.5  // 営業日→カレンダー日の近似
  const to = new Date()
  const from = new Date()
  from.setDate(to.getDate() - Math.ceil(days))
  const fmt = (d: Date) => d.toISOString().slice(0, 10)
  return { from: fmt(from), to: fmt(to) }
}

const connectedEdges = computed(() => {
  if (!networkData.value || !selectedNode.value) return 0
  return networkData.value.edges.filter(
    e => e.from === selectedNode.value || e.to === selectedNode.value
  ).length
})

async function loadNetwork() {
  loading.value = true
  error.value = ''
  selectedNode.value = null
  try {
    let df: string | undefined
    let dt: string | undefined
    if (mode.value === 'fund_flow') {
      if (fundFlowFilter.value === 'period') {
        const range = periodToDateRange(period.value)
        df = range.from
        dt = range.to
      } else if (fundFlowFilter.value === 'range') {
        df = dateFrom.value || undefined
        dt = dateTo.value || undefined
      } else {
        df = dateSingle.value || undefined
        dt = dateSingle.value || undefined
      }
    }
    networkData.value = await api.getNetwork(mode.value, period.value, String(threshold.value), df, dt)
  } catch (e: unknown) {
    error.value = e instanceof Error ? e.message : 'データ取得失敗'
  } finally {
    loading.value = false
  }
}

function setMode(m: string) {
  mode.value = m
  fundFlowFilter.value = 'period'
  loadNetwork()
}

function setPeriod(p: string) {
  period.value = p
  loadNetwork()
}

function setFundFlowFilter(f: string) {
  fundFlowFilter.value = f as 'period' | 'range' | 'date'
  loadNetwork()
}

function onNodeClick(id: string) {
  selectedNode.value = id
}

onMounted(loadNetwork)
</script>

<style scoped>
.btn-tab { @apply px-3 py-1 rounded text-sm border border-gray-700 text-gray-400 hover:text-white transition-colors; }
.btn-tab-active { @apply border-blue-500 text-blue-400 bg-blue-500/10; }
</style>
