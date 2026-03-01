<template>
  <div class="grid gap-1" :style="gridStyle">
    <div
      v-for="item in sectors"
      :key="item.sector"
      class="rounded p-2 text-center text-xs font-medium flex flex-col justify-center min-h-[56px]"
      :style="{ backgroundColor: bgColor(item.avg_return) }"
    >
      <div class="truncate text-white font-semibold">{{ shortName(item.sector) }}</div>
      <div class="text-white/80">{{ formatReturn(item.avg_return) }}</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

interface SectorItem {
  sector: string
  avg_return: number
  total_volume?: number
}

const props = defineProps<{ sectors: SectorItem[] }>()

const gridStyle = computed(() => ({
  gridTemplateColumns: `repeat(${Math.min(props.sectors.length, 6)}, minmax(0, 1fr))`,
}))

function bgColor(r: number): string {
  if (r > 0.02)  return '#166534'
  if (r > 0.01)  return '#15803d'
  if (r > 0.005) return '#16a34a'
  if (r > 0)     return '#4d7c0f'
  if (r > -0.005) return '#92400e'
  if (r > -0.01)  return '#b45309'
  if (r > -0.02)  return '#b91c1c'
  return '#991b1b'
}

function formatReturn(r: number): string {
  return (r >= 0 ? '+' : '') + (r * 100).toFixed(2) + '%'
}

function shortName(s: string): string {
  return s.length > 8 ? s.slice(0, 7) + '…' : s
}
</script>
