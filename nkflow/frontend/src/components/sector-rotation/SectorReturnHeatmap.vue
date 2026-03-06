<template>
  <div>
    <div v-if="loading" class="flex items-center justify-center h-48 text-gray-500 text-sm">
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
    <div v-else class="overflow-x-auto relative" @mouseleave="tooltip.visible = false">
      <table class="text-xs w-full border-collapse">
        <thead>
          <tr>
            <th class="text-left text-gray-500 font-normal px-1 py-0.5 sticky left-0 bg-white z-10 min-w-[7rem]">
              業種
            </th>
            <th
              v-for="p in data.periods" :key="p"
              class="text-center font-normal px-0.5 py-0.5 whitespace-nowrap min-w-[3.5rem]"
              :class="tooltip.visible && tooltip.period === p ? 'text-blue-600 bg-blue-50' : 'text-gray-500'"
            >
              {{ formatPeriod(p) }}
            </th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="sector in data.sectors" :key="sector"
            :class="tooltip.visible && tooltip.sector === sector ? 'bg-blue-50' : 'hover:bg-gray-50'"
          >
            <td
              class="px-1 py-0.5 sticky left-0 z-10 whitespace-nowrap transition-colors"
              :class="tooltip.visible && tooltip.sector === sector
                ? 'text-blue-700 bg-blue-50 font-semibold'
                : 'text-gray-700 bg-white font-normal'"
            >
              {{ sector }}
            </td>
            <td
              v-for="p in data.periods" :key="p"
              class="text-center py-0.5 px-0.5 cursor-default"
              :style="cellStyle(sector, p)"
              @mouseenter="(e) => showTooltip(e, sector, p)"
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
          <div class="flex-1" style="background:#d1d5db"></div>
          <div class="flex-1" style="background:#14532d"></div>
          <div class="flex-1" style="background:#166534"></div>
        </div>
        <span>強</span>
      </div>
    </div>

    <!-- フローティングツールチップ -->
    <Teleport to="body">
      <div
        v-if="tooltip.visible"
        ref="tooltipEl"
        class="fixed z-50 pointer-events-none px-2 py-1 rounded shadow-md text-[11px] border border-gray-200 bg-white/95 backdrop-blur-sm"
        :style="tooltipStyle"
      >
        <span class="text-gray-500">{{ tooltip.sector }}</span>
        <span class="text-gray-300 mx-1">·</span>
        <span class="text-gray-400">{{ tooltip.periodLabel }}</span>
        <span
          class="ml-1.5 font-mono font-bold"
          :class="(tooltip.returnRate ?? 0) >= 0 ? 'text-green-600' : 'text-red-600'"
        >{{ tooltip.returnLabel }}</span>
      </div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch, nextTick } from "vue";
import { useApi } from "../../composables/useApi";
import type { SectorReturnEntry, SectorRotationHeatmap } from "../../types";

const props = defineProps<{
	periods?: number;
	periodType?: "weekly" | "monthly";
}>();

const api = useApi();
const loading = ref(false);
const data = ref<SectorRotationHeatmap | null>(null);
const error = ref(false);
const tooltipEl = ref<HTMLElement | null>(null);

const tooltip = reactive({
	visible: false,
	x: 0,
	y: 0,
	sector: "",
	period: "",
	periodLabel: "",
	returnRate: null as number | null,
	returnLabel: "",
});

const TOOLTIP_OFFSET = 10;

const tooltipStyle = computed(() => {
	const vw = window.innerWidth;
	const vh = window.innerHeight;
	const tw = tooltipEl.value?.offsetWidth ?? 180;
	const th = tooltipEl.value?.offsetHeight ?? 28;
	let x = tooltip.x + TOOLTIP_OFFSET;
	let y = tooltip.y - th - TOOLTIP_OFFSET;
	if (x + tw > vw - 8) x = tooltip.x - tw - TOOLTIP_OFFSET;
	if (y < 8) y = tooltip.y + TOOLTIP_OFFSET;
	return { left: `${x}px`, top: `${y}px` };
});

function showTooltip(e: MouseEvent, sector: string, period: string) {
	const entry = getEntry(sector, period);
	tooltip.x = e.clientX;
	tooltip.y = e.clientY;
	tooltip.sector = sector;
	tooltip.period = period;
	tooltip.periodLabel = formatPeriod(period);
	tooltip.returnRate = entry?.return_rate ?? null;
	tooltip.returnLabel = formatReturn(entry?.return_rate);
	tooltip.visible = true;
}

// (sector, period) → entry の高速ルックアップ
const entryMap = computed(() => {
	const m = new Map<string, SectorReturnEntry>();
	for (const e of data.value?.data ?? []) m.set(`${e.sector}::${e.period}`, e);
	return m;
});

function getEntry(
	sector: string,
	period: string,
): SectorReturnEntry | undefined {
	return entryMap.value.get(`${sector}::${period}`);
}

function formatReturn(v: number | undefined): string {
	if (v == null) return "—";
	return `${(v * 100).toFixed(1)}%`;
}

function formatPeriod(p: string): string {
	// weekly: YYYY-MM-DD → MM/DD
	// monthly: YYYY-MM → MM月
	if (p.length === 7) return `${p.slice(5)}月`;
	return p.slice(5).replace("-", "/");
}

function cellStyle(sector: string, period: string): Record<string, string> {
	const entry = getEntry(sector, period);
	if (!entry) return { background: "#f9fafb" };
	const v = entry.return_rate;
	const bg = returnToColor(v);
	return { background: bg, color: Math.abs(v) > 0.02 ? "#f9fafb" : "#6b7280" };
}

function returnToColor(v: number): string {
	if (v >= 0.04) return "#166534"; // very green
	if (v >= 0.02) return "#14532d"; // green
	if (v >= 0.005) return "#052e16"; // light green
	if (v >= -0.005) return "#f3f4f6"; // neutral (light gray)
	if (v >= -0.02) return "#450a0a"; // light red
	if (v >= -0.04) return "#991b1b"; // red
	return "#7f1d1d"; // very red
}

async function load() {
	loading.value = true;
	error.value = false;
	try {
		data.value = await api.getSectorRotationHeatmap(
			props.periods ?? 12,
			props.periodType ?? "weekly",
		);
	} catch (_) {
		error.value = true;
	} finally {
		loading.value = false;
	}
}

watch(() => [props.periods, props.periodType], load);
onMounted(load);
</script>
