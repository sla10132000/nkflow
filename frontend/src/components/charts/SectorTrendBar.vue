<template>
  <div>
    <div class="flex items-baseline gap-2 mb-1">
      <h2 class="text-sm font-semibold">業種トレンド</h2>
      <span class="text-xs">
        <span class="text-green-600 font-medium">上昇{{ upCount }}</span>
        <span class="text-gray-400 mx-0.5">/</span>
        <span class="text-red-600 font-medium">下降{{ downCount }}</span>
      </span>
    </div>
    <div class="grid grid-cols-1 sm:grid-cols-2 gap-x-4">
      <div v-for="(column, ci) in columns" :key="ci" class="space-y-px">
        <div
          v-for="s in column"
          :key="s.sector"
          class="flex items-center gap-1 text-xs h-4"
        >
          <span class="w-20 text-gray-600 truncate shrink-0 text-right text-[11px]">{{ s.sector }}</span>
          <div class="flex-1 flex items-center h-3">
            <!-- Left half (negative) -->
            <div class="w-1/2 flex justify-end">
              <div
                v-if="s.avg_return < 0"
                class="h-full bg-red-400 rounded-l"
                :style="{ width: `${barPct(s.avg_return)}%` }"
              />
            </div>
            <!-- Center line -->
            <div class="w-px h-full bg-gray-300 shrink-0" />
            <!-- Right half (positive) -->
            <div class="w-1/2">
              <div
                v-if="s.avg_return >= 0"
                class="h-full bg-green-400 rounded-r"
                :style="{ width: `${barPct(s.avg_return)}%` }"
              />
            </div>
          </div>
          <span
            class="w-12 text-right font-medium shrink-0 text-[11px]"
            :class="s.avg_return >= 0 ? 'text-green-600' : 'text-red-600'"
          >
            {{ s.avg_return >= 0 ? '+' : '' }}{{ (s.avg_return * 100).toFixed(1) }}%
          </span>
        </div>
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
	stock_count?: number;
}

const props = defineProps<{ sectors: SectorItem[] }>();

const sorted = computed(() =>
	[...props.sectors].sort((a, b) => b.avg_return - a.avg_return),
);

const columns = computed(() => {
	const half = Math.ceil(sorted.value.length / 2);
	return [sorted.value.slice(0, half), sorted.value.slice(half)];
});

const upCount = computed(
	() => props.sectors.filter((s) => s.avg_return > 0).length,
);
const downCount = computed(
	() => props.sectors.filter((s) => s.avg_return <= 0).length,
);

const maxAbs = computed(() => {
	const m = Math.max(...props.sectors.map((s) => Math.abs(s.avg_return)));
	return m > 0 ? m : 0.01;
});

function barPct(val: number): number {
	return Math.min((Math.abs(val) / maxAbs.value) * 100, 100);
}
</script>
