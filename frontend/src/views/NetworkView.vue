<template>
  <div class="space-y-4">
    <h1 class="text-2xl font-bold">資金フロー</h1>

    <!-- コントロール -->
    <div class="flex flex-wrap gap-3 items-center bg-gray-900 p-3 rounded-lg border border-gray-800">
      <!-- フィルター切替 -->
      <div class="flex rounded-lg overflow-hidden border border-gray-600 text-xs font-medium">
        <button
          v-for="ft in fundFlowFilters" :key="ft.value"
          @click="setFundFlowFilter(ft.value)"
          class="px-4 py-1.5 transition-colors"
          :class="fundFlowFilter === ft.value
            ? 'bg-blue-600 text-white'
            : 'bg-gray-800 text-gray-400 hover:bg-gray-700 hover:text-white'"
        >{{ ft.label }}</button>
      </div>

      <!-- 期間 -->
      <div v-if="fundFlowFilter === 'period'" class="flex gap-2">
        <button v-for="p in periods" :key="p" @click="setPeriod(p)"
          class="btn-tab" :class="{ 'btn-tab-active': period === p }">{{ p }}</button>
      </div>

      <!-- 範囲 -->
      <template v-else-if="fundFlowFilter === 'range'">
        <div class="flex gap-1">
          <button v-for="pr in rangePresets" :key="pr.label" @click="applyRangePreset(pr)"
            class="px-2 py-1 text-xs rounded border border-gray-700 text-gray-400 hover:border-blue-500 hover:text-blue-400 transition-colors"
          >{{ pr.label }}</button>
        </div>
        <div class="flex items-center gap-2">
          <div class="flex flex-col gap-0.5">
            <label class="text-[10px] text-gray-500 leading-none">From</label>
            <input v-model="dateFrom" @change="loadNetwork" type="date" class="date-input" />
          </div>
          <span class="text-gray-500 text-sm mt-3">→</span>
          <div class="flex flex-col gap-0.5">
            <label class="text-[10px] text-gray-500 leading-none">To</label>
            <input v-model="dateTo" @change="loadNetwork" type="date" class="date-input" />
          </div>
        </div>
      </template>

      <!-- 日付 -->
      <template v-else-if="fundFlowFilter === 'date'">
        <div class="flex gap-1">
          <button v-for="pr in datePresets" :key="pr.label" @click="applyDatePreset(pr)"
            class="px-2 py-1 text-xs rounded border border-gray-700 text-gray-400 hover:border-blue-500 hover:text-blue-400 transition-colors"
          >{{ pr.label }}</button>
        </div>
        <div class="flex flex-col gap-0.5">
          <label class="text-[10px] text-gray-500 leading-none">日付</label>
          <input v-model="dateSingle" @change="loadNetwork" type="date" class="date-input" />
        </div>
      </template>

      <!-- アンカーバッジ + レジームインジケーター -->
      <div v-if="anchorDate || currentRegime" class="flex items-center gap-2 ml-auto text-xs">
        <span v-if="anchorDate"
          class="bg-indigo-950 text-indigo-300 px-2 py-1 rounded border border-indigo-700">
          📍 {{ anchorDate }} 以降
        </span>
        <span v-if="currentRegime"
          :class="regimeBadgeClass"
          class="px-2 py-1 rounded border font-medium">
          {{ regimeLabel }}
        </span>
      </div>
    </div>

    <!-- ネットワークグラフ -->
    <div class="flex gap-4 h-[600px]">
      <div class="flex-1 bg-gray-900 rounded-lg border border-gray-800 overflow-hidden">
        <div v-if="loading" class="flex items-center justify-center h-full text-gray-400">読み込み中...</div>
        <div v-else-if="error" class="flex items-center justify-center h-full text-red-400">{{ error }}</div>
        <GraphView
          v-else-if="networkData && networkData.nodes.length > 0"
          :data="networkData"
          :directed="true"
          :anchor-mode="!!anchorDate"
          @node-click="onNodeClick"
          class="w-full h-full"
        />
        <div v-else class="flex items-center justify-center h-full text-gray-500">
          該当期間に資金フローなし（セクター間で出来高・騰落率の乖離が条件未満）
        </div>
      </div>

      <!-- 選択セクターのサイドパネル -->
      <div v-if="selectedNode" class="w-52 bg-gray-900 rounded-lg border border-gray-800 p-4 overflow-y-auto">
        <h3 class="font-semibold mb-3 text-sm">{{ selectedNode }}</h3>
        <div class="text-xs text-gray-400 space-y-1">
          <p>接続エッジ数: {{ connectedEdges }}</p>
          <p>流入: {{ inflowCount }}本</p>
          <p>流出: {{ outflowCount }}本</p>
        </div>
      </div>
    </div>

    <!-- サンキー図 -->
    <div v-if="networkData && networkData.edges.length > 0"
         class="bg-gray-900 rounded-lg border border-gray-800 p-4">
      <h2 class="text-sm font-semibold text-gray-300 mb-1">資金の合流 — サンキー図</h2>
      <p class="text-xs text-gray-600 mb-3">帯の幅 = フロー発生回数（太いほど強い流れ）</p>
      <FundFlowSankey :edges="networkData.edges" />
    </div>

    <!-- 時系列トレンド -->
    <div class="bg-gray-900 rounded-lg border border-gray-800 p-4">
      <h2 class="text-sm font-semibold text-gray-300 mb-3">時系列トレンド — セクター間資金フロー</h2>
      <FundFlowTimeline @anchor-changed="onAnchorChanged" />
    </div>

    <!-- 凡例 -->
    <div class="text-xs text-gray-500">
      ノード: セクター (色=セクター) / エッジ太さ: 出現頻度 (日数) / 矢印: 資金フロー方向
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useApi } from '../composables/useApi'
import GraphView from '../components/network/GraphView.vue'
import FundFlowTimeline from '../components/charts/FundFlowTimeline.vue'
import FundFlowSankey from '../components/charts/FundFlowSankey.vue'
import type { NetworkData } from '../types'

const api = useApi()
const loading = ref(false)
const error = ref('')
const networkData = ref<NetworkData | null>(null)
const selectedNode = ref<string | null>(null)
const period = ref('20d')
const fundFlowFilter = ref<'period' | 'range' | 'date'>('range')
const dateFrom = ref('')
const dateTo = ref('')
const dateSingle = ref('')
const anchorDate = ref<string | null>(null)
const currentRegime = ref<string | null>(null)

const periods = ['20d', '60d', '120d']
const fundFlowFilters = [
  { value: 'period', label: '期間' },
  { value: 'range',  label: '範囲' },
  { value: 'date',   label: '日付' },
]
const rangePresets = [
  { label: '直近5営業日', days: 7 },
  { label: '先月',        days: 30 },
  { label: '3ヶ月',       days: 90 },
]
const datePresets = [
  { label: '今日',   offsetDays: 0 },
  { label: '昨日',   offsetDays: 1 },
  { label: '先週末', offsetDays: -1 },
]

const regimeBadgeClass = computed(() => {
  if (currentRegime.value === 'risk_on')  return 'bg-green-950 text-green-300 border-green-700'
  if (currentRegime.value === 'risk_off') return 'bg-red-950 text-red-300 border-red-700'
  return 'bg-gray-800 text-gray-400 border-gray-600'
})
const regimeLabel = computed(() => {
  if (currentRegime.value === 'risk_on')  return '🟢 Risk-on'
  if (currentRegime.value === 'risk_off') return '🔴 Risk-off'
  return '⚪ Neutral'
})

const fmt = (d: Date) => d.toISOString().slice(0, 10)

function lastBusinessDay(from: Date = new Date()): Date {
  const d = new Date(from)
  const dow = d.getDay()
  if (dow === 0) d.setDate(d.getDate() - 2)
  else if (dow === 6) d.setDate(d.getDate() - 1)
  return d
}

function periodToDateRange(p: string): { from: string; to: string } {
  const days = parseInt(p) * 1.5
  const to = new Date()
  const from = new Date()
  from.setDate(to.getDate() - Math.ceil(days))
  return { from: fmt(from), to: fmt(to) }
}

function applyRangePreset(pr: { days: number }) {
  const to = new Date()
  const from = new Date()
  from.setDate(to.getDate() - pr.days)
  dateTo.value = fmt(to)
  dateFrom.value = fmt(from)
  loadNetwork()
}

function applyDatePreset(pr: { label: string; offsetDays: number }) {
  if (pr.label === '先週末') {
    const d = new Date()
    const dow = d.getDay()
    const daysToFriday = dow === 0 ? 2 : dow === 6 ? 1 : dow - 5 + (dow < 5 ? 7 : 0)
    d.setDate(d.getDate() - daysToFriday)
    dateSingle.value = fmt(d)
  } else {
    const d = new Date()
    d.setDate(d.getDate() - pr.offsetDays)
    dateSingle.value = fmt(lastBusinessDay(d))
  }
  loadNetwork()
}

const connectedEdges = computed(() => {
  if (!networkData.value || !selectedNode.value) return 0
  return networkData.value.edges.filter(
    e => e.from === selectedNode.value || e.to === selectedNode.value
  ).length
})
const inflowCount = computed(() => {
  if (!networkData.value || !selectedNode.value) return 0
  return networkData.value.edges.filter(e => e.to === selectedNode.value).length
})
const outflowCount = computed(() => {
  if (!networkData.value || !selectedNode.value) return 0
  return networkData.value.edges.filter(e => e.from === selectedNode.value).length
})

function onAnchorChanged(date: string | null) {
  anchorDate.value = date
}

async function loadRegime() {
  try {
    const summary = await api.getSummary(1)
    currentRegime.value = summary?.regime ?? null
  } catch {
    currentRegime.value = null
  }
}

async function loadNetwork() {
  loading.value = true
  error.value = ''
  selectedNode.value = null
  try {
    let df: string | undefined
    let dt: string | undefined
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
    networkData.value = await api.getNetwork('fund_flow', undefined, undefined, df, dt)
  } catch (e: unknown) {
    error.value = e instanceof Error ? e.message : 'データ取得失敗'
  } finally {
    loading.value = false
  }
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

onMounted(() => {
  applyRangePreset({ days: 7 })
  loadRegime()
})
</script>

<style scoped>
.btn-tab { @apply px-3 py-1 rounded text-sm border border-gray-700 text-gray-400 hover:text-white transition-colors; }
.btn-tab-active { @apply border-blue-500 text-blue-400 bg-blue-500/10; }

.date-input {
  @apply bg-gray-800 border border-gray-600 rounded px-2 py-1 text-sm text-gray-200;
  color-scheme: dark;
}
.date-input:focus {
  @apply outline-none border-blue-500 ring-1 ring-blue-500/40;
}
</style>
