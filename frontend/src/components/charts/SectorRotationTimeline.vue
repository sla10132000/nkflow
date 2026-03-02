<template>
  <div>
    <div v-if="loading" class="flex items-center justify-center h-32 text-gray-400 text-sm">
      読み込み中...
    </div>
    <div v-else-if="!states.length"
         class="flex items-center justify-center h-32 text-gray-500 text-sm">
      データなし
    </div>
    <div v-else>
      <!-- タイムラインバー -->
      <div class="relative h-10 rounded overflow-hidden flex" title="各週のローテーション状態">
        <div
          v-for="s in states" :key="s.period"
          class="flex-1 cursor-pointer transition-opacity hover:opacity-80"
          :style="{ background: stateColor(s.state_id) }"
          :title="`${s.period}\n${s.state_name}`"
          @click="selectedState = s"
        ></div>
      </div>

      <!-- X軸ラベル (間引き) -->
      <div class="relative h-4 flex mt-0.5">
        <div
          v-for="(s, i) in states" :key="s.period"
          class="flex-1 text-[9px] text-gray-600 text-center"
        >
          {{ i % tickInterval === 0 ? s.period.slice(2, 7) : '' }}
        </div>
      </div>

      <!-- 凡例 -->
      <div class="flex flex-wrap gap-3 mt-2 text-xs text-gray-400">
        <span
          v-for="(name, id) in stateNames" :key="id"
          class="flex items-center gap-1"
        >
          <span class="inline-block w-3 h-3 rounded-sm" :style="{ background: stateColor(Number(id)) }"></span>
          {{ name }}
        </span>
      </div>

      <!-- 選択状態の詳細 -->
      <div v-if="selectedState" class="mt-3 p-3 rounded-lg bg-gray-900 border border-gray-800 text-xs">
        <div class="flex items-center gap-2 mb-2">
          <span class="inline-block w-3 h-3 rounded-sm" :style="{ background: stateColor(selectedState.state_id) }"></span>
          <span class="text-gray-300 font-medium">{{ selectedState.period }}</span>
          <span class="text-gray-400">{{ selectedState.state_name }}</span>
        </div>
        <div class="grid grid-cols-5 gap-1">
          <div
            v-for="sec in selectedState.top_sectors" :key="sec.sector"
            class="text-center p-1 rounded bg-gray-800"
          >
            <div class="text-gray-300 truncate">{{ sec.sector }}</div>
            <div :class="sec.avg_return >= 0 ? 'text-green-400' : 'text-red-400'">
              {{ (sec.avg_return * 100).toFixed(1) }}%
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useApi } from '../../composables/useApi'
import type { SectorRotationState } from '../../types'

const props = defineProps<{ limit?: number; clusterMethod?: string }>()

const api = useApi()
const loading = ref(false)
const states = ref<SectorRotationState[]>([])
const selectedState = ref<SectorRotationState | null>(null)

// 状態ID → 状態名 (最新の代表名)
const stateNames = computed<Record<number, string>>(() => {
  const m: Record<number, string> = {}
  states.value.forEach(s => { m[s.state_id] = s.state_name })
  return m
})

const tickInterval = computed(() => Math.max(1, Math.ceil(states.value.length / 20)))

const STATE_COLORS = [
  '#3b82f6', // blue-500
  '#22c55e', // green-500
  '#f59e0b', // amber-500
  '#ef4444', // red-500
  '#a855f7', // purple-500
]

function stateColor(id: number): string {
  return STATE_COLORS[id % STATE_COLORS.length] ?? '#6b7280'
}

async function load() {
  loading.value = true
  try {
    const res = await api.getSectorRotationStates(
      props.clusterMethod ?? 'kmeans',
      props.limit ?? 52,
    )
    states.value = res.states ?? []
    if (states.value.length > 0) {
      selectedState.value = states.value[states.value.length - 1]
    }
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>
