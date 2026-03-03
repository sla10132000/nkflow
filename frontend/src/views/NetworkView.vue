<template>
  <div class="space-y-4">
    <div class="flex items-center gap-3 flex-wrap">
      <h1 class="text-2xl font-bold">資金フロー</h1>
      <span v-if="currentRegime"
        :class="regimeBadgeClass"
        class="px-2 py-1 rounded border text-xs font-medium">
        {{ regimeLabel }}
      </span>
      <span v-if="anchorDate"
        class="bg-indigo-100 text-indigo-700 px-2 py-1 rounded border border-indigo-200 text-xs">
        📍 {{ anchorDate }} 以降
      </span>
      <!-- 信用過熱警報バッジ -->
      <span v-if="isCreditOverheating"
        class="animate-pulse bg-red-100 text-red-700 px-2 py-1 rounded border border-red-300 text-xs font-bold">
        ⚠ 信用過熱警報
      </span>
    </div>

    <!-- コントロール -->
    <div class="flex flex-wrap gap-3 items-center bg-white p-3 rounded-lg border border-gray-200 shadow-sm">
      <div class="flex rounded-lg overflow-hidden border border-gray-300 text-xs font-medium">
        <button
          v-for="ft in fundFlowFilters" :key="ft.value"
          @click="setFundFlowFilter(ft.value)"
          class="px-4 py-1.5 transition-colors"
          :class="fundFlowFilter === ft.value
            ? 'bg-blue-600 text-white'
            : 'bg-gray-100 text-gray-600 hover:bg-gray-200 hover:text-gray-900'"
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
            class="px-2 py-1 text-xs rounded border border-gray-300 text-gray-600 hover:border-blue-500 hover:text-blue-600 transition-colors"
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
            class="px-2 py-1 text-xs rounded border border-gray-300 text-gray-600 hover:border-blue-500 hover:text-blue-600 transition-colors"
          >{{ pr.label }}</button>
        </div>
        <div class="flex flex-col gap-0.5">
          <label class="text-[10px] text-gray-500 leading-none">日付</label>
          <input v-model="dateSingle" @change="loadNetwork" type="date" class="date-input" />
        </div>
      </template>
    </div>

    <!-- ① 市場圧力ゲージ -->
    <div class="bg-white rounded-lg border border-gray-200 shadow-sm p-4">
      <h2 class="text-sm font-semibold text-gray-700 mb-3">市場圧力 (信用評価損益)</h2>
      <div v-if="latestPressure" class="flex items-start gap-6 flex-wrap">
        <MarketPressureGauge
          :pl-ratio="latestPressure.pl_ratio"
          :pl-zone="latestPressure.pl_zone"
          :buy-growth-4w="latestPressure.buy_growth_4w"
        />
        <div class="text-xs text-gray-500 space-y-1 mt-2">
          <p>信用倍率: <span class="text-gray-800">{{ fmtNum(latestPressure.margin_ratio) }}</span></p>
          <p>倍率トレンド: <span :class="trendClass">{{ fmtNum(latestPressure.margin_ratio_trend, 3) }}</span></p>
        </div>
      </div>
      <div v-else class="text-xs text-gray-400 py-4">信用残高データなし</div>
    </div>

    <!-- ② メイン: 時系列フロー -->
    <div class="bg-white rounded-lg border border-gray-200 shadow-sm p-4">
      <h2 class="text-sm font-semibold text-gray-700 mb-3">時系列フロー</h2>
      <FundFlowTimeline @anchor-changed="onAnchorChanged" />
    </div>

    <!-- ③ 市場圧力タイムライン (折りたたみ) -->
    <div class="bg-white rounded-lg border border-gray-200 shadow-sm">
      <div class="flex items-center justify-between px-4 py-3">
        <div class="flex items-center gap-3 flex-wrap">
          <button
            @click="showPressureTimeline = !showPressureTimeline"
            class="text-sm font-medium text-gray-600 hover:text-gray-900 transition-colors"
          >信用圧力タイムライン {{ showPressureTimeline ? '▲' : '▼' }}</button>
          <div class="flex gap-1">
            <button v-for="d in [30, 60, 90, 180]" :key="d"
              @click="pressureDays = d; loadPressure()"
              class="px-2 py-0.5 text-xs rounded border transition-colors"
              :class="pressureDays === d
                ? 'border-blue-500 text-blue-600 bg-blue-50'
                : 'border-gray-300 text-gray-600 hover:border-blue-500 hover:text-blue-600'"
            >{{ d }}日</button>
          </div>
        </div>
      </div>
      <div v-if="showPressureTimeline" class="border-t border-gray-200 p-4">
        <MarketPressureTimeline :days="pressureDays" />
      </div>
    </div>

    <!-- ⑤ メイン: サンキー図 -->
    <div class="bg-white rounded-lg border border-gray-200 shadow-sm p-4">
      <h2 class="text-sm font-semibold text-gray-700 mb-1">資金の合流 — サンキー図</h2>
      <p class="text-xs text-gray-400 mb-3">帯の幅 = フロー発生回数（太いほど強い流れ）</p>
      <div v-if="loading" class="flex items-center justify-center h-32 text-gray-500 text-sm">読み込み中...</div>
      <div v-else-if="error" class="flex items-center justify-center h-32 text-red-600 text-sm">{{ error }}</div>
      <FundFlowSankey v-else-if="networkData" :edges="networkData.edges" />
    </div>

    <!-- ⑥ サブ: ネットワーク（折りたたみ） -->
    <div class="bg-white rounded-lg border border-gray-200 shadow-sm">
      <button
        @click="showNetwork = !showNetwork"
        class="w-full flex items-center justify-between px-4 py-3 text-sm text-gray-600 hover:text-gray-900 transition-colors"
      >
        <span class="font-medium">ネットワーク <span class="text-xs text-gray-400 ml-1">解析用</span></span>
        <span class="text-gray-400">{{ showNetwork ? '▲' : '▼' }}</span>
      </button>

      <div v-if="showNetwork" class="border-t border-gray-200">
        <div class="flex gap-4 h-[520px] p-3">
          <div class="flex-1 overflow-hidden rounded">
            <GraphView
              v-if="networkData && networkData.nodes.length > 0"
              :data="networkData"
              :directed="true"
              :anchor-mode="!!anchorDate"
              @node-click="onNodeClick"
              class="w-full h-full"
            />
            <div v-else class="flex items-center justify-center h-full text-gray-500 text-sm">
              {{ loading ? '読み込み中...' : '該当期間に資金フローなし' }}
            </div>
          </div>

          <!-- 選択セクター詳細 -->
          <div v-if="selectedNode" class="w-48 bg-gray-100 rounded p-3 text-xs text-gray-600 space-y-1 shrink-0">
            <p class="font-semibold text-gray-800 mb-2">{{ selectedNode }}</p>
            <p>接続: {{ connectedEdges }}本</p>
            <p>流入: {{ inflowCount }}本</p>
            <p>流出: {{ outflowCount }}本</p>
          </div>
        </div>
        <div class="px-4 pb-3 text-xs text-gray-400">
          エッジ太さ: 出現頻度 / 矢印: 資金フロー方向 / ノード枠: 流入集中度
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useApi } from '../composables/useApi'
import GraphView from '../components/network/GraphView.vue'
import FundFlowTimeline from '../components/charts/FundFlowTimeline.vue'
import FundFlowSankey from '../components/charts/FundFlowSankey.vue'
import MarketPressureGauge from '../components/charts/MarketPressureGauge.vue'
import MarketPressureTimeline from '../components/charts/MarketPressureTimeline.vue'
import type { NetworkData, MarketPressureTimeseries } from '../types'

const api = useApi()
const loading = ref(false)
const error = ref('')
const networkData = ref<NetworkData | null>(null)
const selectedNode = ref<string | null>(null)
const showNetwork = ref(false)
const showPressureTimeline = ref(true)
const pressureDays = ref(90)
const period = ref('20d')
const fundFlowFilter = ref<'period' | 'range' | 'date'>('range')
const dateFrom = ref('')
const dateTo = ref('')
const dateSingle = ref('')
const anchorDate = ref<string | null>(null)
const currentRegime = ref<string | null>(null)
const pressureData = ref<MarketPressureTimeseries | null>(null)

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

const latestPressure = computed(() => {
  if (!pressureData.value || pressureData.value.dates.length === 0) return null
  const last = pressureData.value.dates.length - 1
  return {
    pl_ratio: pressureData.value.pl_ratio[last] ?? null,
    pl_zone:  pressureData.value.pl_zone[last] ?? 'neutral',
    buy_growth_4w: pressureData.value.buy_growth_4w[last] ?? null,
    margin_ratio: pressureData.value.margin_ratio[last] ?? null,
    margin_ratio_trend: pressureData.value.margin_ratio_trend[last] ?? null,
  }
})

const isCreditOverheating = computed(() => {
  if (!pressureData.value || pressureData.value.signal_flags.length === 0) return false
  const last = pressureData.value.signal_flags.length - 1
  return pressureData.value.signal_flags[last]?.credit_overheating === true
})

const trendClass = computed(() => {
  const t = latestPressure.value?.margin_ratio_trend ?? 0
  return t > 0 ? 'text-red-600' : t < 0 ? 'text-green-600' : 'text-gray-600'
})

function fmtNum(v: number | null, decimals = 2): string {
  if (v == null) return '—'
  return v.toFixed(decimals)
}

const regimeBadgeClass = computed(() => {
  if (currentRegime.value === 'risk_on')  return 'bg-green-100 text-green-700 border-green-200'
  if (currentRegime.value === 'risk_off') return 'bg-red-100 text-red-700 border-red-200'
  return 'bg-gray-100 text-gray-600 border-gray-300'
})
const regimeLabel = computed(() => {
  if (currentRegime.value === 'risk_on')  return '🟢 Risk-on'
  if (currentRegime.value === 'risk_off') return '🔴 Risk-off'
  return '⚪ Neutral'
})

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

async function loadPressure() {
  try {
    pressureData.value = await api.getMarketPressureTimeseries(pressureDays.value)
  } catch {
    pressureData.value = null
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
  loadPressure()
})
</script>

<style scoped>
.btn-tab { @apply px-3 py-1 rounded text-sm border border-gray-300 text-gray-600 hover:text-gray-900 transition-colors; }
.btn-tab-active { @apply border-blue-500 text-blue-600 bg-blue-50; }

.date-input {
  @apply bg-white border border-gray-300 rounded px-2 py-1 text-sm text-gray-800;
}
.date-input:focus {
  @apply outline-none border-blue-500 ring-1 ring-blue-500/40;
}
</style>
