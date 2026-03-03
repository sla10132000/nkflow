<template>
  <div>
    <div v-if="loading" class="flex items-center justify-center h-48 text-gray-400 text-sm">
      読み込み中...
    </div>
    <div v-else-if="error"
         class="flex items-center justify-center h-48 text-red-500 text-sm">
      データ取得エラー
    </div>
    <div v-else-if="!data || data.periods.length === 0"
         class="flex items-center justify-center h-48 text-gray-500 text-sm">
      データなし
    </div>
    <div v-else class="overflow-x-auto">
      <table class="text-xs w-full border-collapse">
        <thead>
          <tr>
            <th class="text-left text-gray-500 font-normal px-1 py-0.5 sticky left-0 bg-gray-950 z-10 min-w-[7rem]">
              業種
            </th>
            <th
              v-for="p in data.periods" :key="p"
              class="text-center text-gray-500 font-normal px-0.5 py-0.5 whitespace-nowrap min-w-[3.5rem]"
            >
              {{ formatPeriod(p) }}
            </th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="sector in data.sectors" :key="sector" class="hover:bg-gray-900/40">
            <td class="text-gray-300 px-1 py-0.5 sticky left-0 bg-gray-950 z-10 whitespace-nowrap">
              {{ sector }}
            </td>
            <td
              v-for="p in data.periods" :key="p"
              class="text-center py-0.5 px-0.5 cursor-default"
              :style="cellStyle(sector, p)"
              :title="`${sector} ${p}: ${formatReturn(getEntry(sector, p)?.return_rate)}`"
            >
              <span class="text-[10px] font-mono">
                {{ formatReturn(getEntry(sector, p)?.return_rate) }}
              </span>
            </td>
          </tr>
        </tbody>
      </table>

      <!-- カラースケール凡例 -->
      <div class="flex items-center gap-2 mt-2 text-[10px] text-gray-500">
        <span>弱</span>
        <div class="flex h-2 rounded overflow-hidden" style="width:120px">
          <div class="flex-1" style="background:#7f1d1d"></div>
          <div class="flex-1" style="background:#991b1b"></div>
          <div class="flex-1" style="background:#374151"></div>
          <div class="flex-1" style="background:#14532d"></div>
          <div class="flex-1" style="background:#166534"></div>
        </div>
        <span>強</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useApi } from '../../composables/useApi'
import type { SectorRotationHeatmap, SectorReturnEntry } from '../../types'

const props = defineProps<{
  periods?: number
  periodType?: 'weekly' | 'monthly'
}>()

const api = useApi()
const loading = ref(false)
const data = ref<SectorRotationHeatmap | null>(null)
const error = ref(false)

// (sector, period) → entry の高速ルックアップ
const entryMap = computed(() => {
  const m = new Map<string, SectorReturnEntry>()
  data.value?.data.forEach(e => m.set(`${e.sector}::${e.period}`, e))
  return m
})

function getEntry(sector: string, period: string): SectorReturnEntry | undefined {
  return entryMap.value.get(`${sector}::${period}`)
}

function formatReturn(v: number | undefined): string {
  if (v == null) return '—'
  return `${(v * 100).toFixed(1)}%`
}

function formatPeriod(p: string): string {
  // weekly: YYYY-MM-DD → MM/DD
  // monthly: YYYY-MM → MM月
  if (p.length === 7) return p.slice(5) + '月'
  return p.slice(5).replace('-', '/')
}

function cellStyle(sector: string, period: string): Record<string, string> {
  const entry = getEntry(sector, period)
  if (!entry) return { background: '#111827' }
  const v = entry.return_rate
  const bg = returnToColor(v)
  return { background: bg, color: Math.abs(v) > 0.02 ? '#f9fafb' : '#9ca3af' }
}

function returnToColor(v: number): string {
  if (v >= 0.04)  return '#166534'  // very green
  if (v >= 0.02)  return '#14532d'  // green
  if (v >= 0.005) return '#052e16'  // light green
  if (v >= -0.005) return '#111827' // neutral
  if (v >= -0.02) return '#450a0a'  // light red
  if (v >= -0.04) return '#991b1b'  // red
  return '#7f1d1d'                   // very red
}

async function load() {
  loading.value = true
  error.value = false
  try {
    data.value = await api.getSectorRotationHeatmap(
      props.periods ?? 12,
      props.periodType ?? 'weekly',
    )
  } catch (_) {
    error.value = true
  } finally {
    loading.value = false
  }
}

watch(() => [props.periods, props.periodType], load)
onMounted(load)
</script>
