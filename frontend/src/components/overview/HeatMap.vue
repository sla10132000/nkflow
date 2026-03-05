<template>
  <div class="space-y-0.5">
    <div
      v-for="item in sorted"
      :key="item.sector"
      class="flex items-center gap-1.5 text-xs"
    >
      <span class="w-20 text-gray-700 shrink-0 truncate">{{ item.sector }}</span>
      <div class="flex-1 flex items-center gap-1 min-w-0">
        <div class="flex-1 h-3 bg-gray-100 rounded overflow-hidden">
          <div
            class="h-full rounded transition-all"
            :class="item.avg_return >= 0 ? 'bg-green-400' : 'bg-red-400'"
            :style="{ width: `${Math.min(Math.abs(item.avg_return) / maxAbs * 100, 100)}%` }"
          />
        </div>
        <span
          class="w-14 text-right font-medium shrink-0"
          :class="item.avg_return >= 0 ? 'text-green-600' : 'text-red-600'"
        >
          {{ formatReturn(item.avg_return) }}
        </span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";

interface SectorItem {
	sector: string;
	avg_return: number;
	total_volume?: number;
}

const props = defineProps<{ sectors: SectorItem[] }>();

const sorted = computed(() =>
	[...props.sectors].sort((a, b) => b.avg_return - a.avg_return),
);

const maxAbs = computed(() => {
	if (!props.sectors.length) return 1;
	const m = Math.max(...props.sectors.map((s) => Math.abs(s.avg_return)));
	return m > 0 ? m : 1;
});

function formatReturn(r: number): string {
	return `${(r >= 0 ? "+" : "") + (r * 100).toFixed(2)}%`;
}
</script>
