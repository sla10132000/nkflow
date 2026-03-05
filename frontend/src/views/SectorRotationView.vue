<template>
  <div class="space-y-3">

    <!-- ヘッダー -->
    <div class="flex items-center gap-3 flex-wrap">
      <h1 class="text-xl font-bold">セクターローテーション</h1>
      <span v-if="prediction?.current"
        class="px-2 py-1 rounded border text-xs font-medium"
        :style="{ background: stateColorBg(prediction.current.state_id), borderColor: stateColor(prediction.current.state_id), color: stateColor(prediction.current.state_id) }">
        現在: {{ prediction.current.state_name }}
      </span>
    </div>

    <!-- 予測パネル -->
    <div v-if="prediction?.available" class="grid grid-cols-1 md:grid-cols-3 gap-3">

      <!-- 現在の状態 -->
      <div class="bg-white rounded-lg border border-gray-200 shadow-sm p-3">
        <div class="text-xs text-gray-500 mb-1">現在のローテーション状態</div>
        <div class="flex items-center gap-2 mb-2">
          <span class="inline-block w-3 h-3 rounded-sm"
            :style="{ background: stateColor(prediction.current!.state_id) }"></span>
          <span class="text-sm font-medium text-gray-800">{{ prediction.current!.state_name }}</span>
        </div>
        <div class="text-xs text-gray-500">
          上位セクター
        </div>
        <div class="mt-1 space-y-1">
          <div v-for="sec in (prediction.top_sectors ?? []).slice(0, 3)" :key="sec.sector"
               class="flex items-center justify-between text-xs">
            <span class="text-gray-600">{{ sec.sector }}</span>
            <span :class="sec.avg_return >= 0 ? 'text-green-600' : 'text-red-600'">
              {{ (sec.avg_return * 100).toFixed(2) }}%
            </span>
          </div>
        </div>
      </div>

      <!-- 次期予測 -->
      <div class="bg-white rounded-lg border border-gray-200 shadow-sm p-3">
        <div class="text-xs text-gray-500 mb-1">次期予測状態</div>
        <div class="flex items-center gap-2 mb-2">
          <span class="inline-block w-3 h-3 rounded-sm"
            :style="{ background: stateColor(prediction.prediction!.state_id) }"></span>
          <span class="text-sm font-medium text-gray-800">{{ prediction.prediction!.state_name }}</span>
        </div>
        <div class="flex items-center gap-2 mb-2">
          <!-- 確率バー -->
          <div class="flex-1 h-2 bg-gray-200 rounded-full overflow-hidden">
            <div class="h-full rounded-full bg-blue-500"
              :style="{ width: `${(prediction.prediction!.confidence * 100).toFixed(0)}%` }"></div>
          </div>
          <span class="text-xs text-blue-600 font-mono">{{ (prediction.prediction!.confidence * 100).toFixed(0) }}%</span>
        </div>
        <div class="text-[10px] text-gray-400">
          モデル精度: {{ prediction.model_accuracy != null ? (prediction.model_accuracy * 100).toFixed(0) + '%' : '—' }}
          (Walk-Forward)
        </div>
      </div>

      <!-- 全状態確率 -->
      <div class="bg-white rounded-lg border border-gray-200 shadow-sm p-3">
        <div class="text-xs text-gray-500 mb-2">状態別確率</div>
        <div class="space-y-1.5">
          <div v-for="p in sortedProba" :key="p.state_id" class="flex items-center gap-2 text-xs">
            <span class="inline-block w-2 h-2 rounded-sm flex-shrink-0"
              :style="{ background: stateColor(p.state_id) }"></span>
            <span class="text-gray-600 truncate flex-1 min-w-0 text-[10px]">{{ p.state_name }}</span>
            <div class="w-16 h-1.5 bg-gray-200 rounded-full overflow-hidden flex-shrink-0">
              <div class="h-full rounded-full"
                :style="{ width: `${(p.probability * 100).toFixed(0)}%`, background: stateColor(p.state_id) }"></div>
            </div>
            <span class="text-gray-500 font-mono text-[10px] w-8 text-right">{{ (p.probability * 100).toFixed(0) }}%</span>
          </div>
        </div>
      </div>
    </div>

    <!-- タブコントロール -->
    <div class="flex gap-1 border-b border-gray-200">
      <button
        v-for="t in tabs" :key="t.value"
        @click="activeTab = t.value"
        class="px-4 py-2 text-sm transition-colors border-b-2 -mb-px"
        :class="activeTab === t.value
          ? 'border-blue-500 text-blue-600'
          : 'border-transparent text-gray-500 hover:text-gray-700'"
      >{{ t.label }}</button>
    </div>

    <!-- ヒートマップタブ -->
    <div v-if="activeTab === 'heatmap'" class="bg-white rounded-lg border border-gray-200 shadow-sm p-3">
      <div class="flex items-center gap-3 mb-2">
        <span class="text-sm text-gray-700 font-medium">セクター別リターン</span>
        <!-- 期間タイプ -->
        <div class="flex rounded overflow-hidden border border-gray-300 text-xs ml-auto">
          <button v-for="pt in periodTypes" :key="pt.value"
            @click="periodType = pt.value"
            class="px-3 py-1 transition-colors"
            :class="periodType === pt.value ? 'bg-blue-600 text-white' : 'bg-gray-100 text-gray-600 hover:bg-gray-200'">
            {{ pt.label }}
          </button>
        </div>
        <!-- 期間数 -->
        <div class="flex rounded overflow-hidden border border-gray-300 text-xs">
          <button v-for="n in [8, 12, 24]" :key="n"
            @click="heatmapPeriods = n"
            class="px-3 py-1 transition-colors"
            :class="heatmapPeriods === n ? 'bg-blue-600 text-white' : 'bg-gray-100 text-gray-600 hover:bg-gray-200'">
            {{ n }}
          </button>
        </div>
      </div>
      <SectorReturnHeatmap :periods="heatmapPeriods" :period-type="periodType" />
    </div>

    <!-- タイムラインタブ -->
    <div v-if="activeTab === 'timeline'" class="bg-white rounded-lg border border-gray-200 shadow-sm p-3">
      <div class="flex items-center gap-3 mb-2">
        <span class="text-sm text-gray-700 font-medium">ローテーション状態タイムライン</span>
        <div class="flex rounded overflow-hidden border border-gray-300 text-xs ml-auto">
          <button v-for="n in [26, 52, 104]" :key="n"
            @click="timelineWeeks = n"
            class="px-3 py-1 transition-colors"
            :class="timelineWeeks === n ? 'bg-blue-600 text-white' : 'bg-gray-100 text-gray-600 hover:bg-gray-200'">
            {{ n }}週
          </button>
        </div>
      </div>
      <SectorRotationTimeline :limit="timelineWeeks" />
    </div>

    <!-- 遷移行列タブ -->
    <div v-if="activeTab === 'transitions'" class="bg-white rounded-lg border border-gray-200 shadow-sm p-3">
      <div class="text-sm text-gray-700 font-medium mb-2">遷移確率行列</div>
      <div v-if="loadingTransitions" class="text-gray-500 text-sm">読み込み中...</div>
      <div v-else-if="transitions" class="overflow-x-auto">
        <table class="text-xs border-collapse">
          <thead>
            <tr>
              <th class="text-left text-gray-500 font-normal px-2 py-1">現在 → 次</th>
              <th v-for="(name, id) in transitions.state_names" :key="id"
                class="text-center text-gray-600 font-normal px-2 py-1 max-w-[6rem] truncate"
                :title="name">
                <span class="inline-block w-2 h-2 rounded-sm mr-1"
                  :style="{ background: stateColor(Number(id)) }"></span>
                {{ name.split('主導')[0] }}
              </th>
              <th class="text-gray-500 font-normal px-2 py-1">平均<br>継続</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(fromName, fromId) in transitions.state_names" :key="fromId"
                class="hover:bg-gray-50">
              <td class="text-gray-600 px-2 py-1 whitespace-nowrap">
                <span class="inline-block w-2 h-2 rounded-sm mr-1"
                  :style="{ background: stateColor(Number(fromId)) }"></span>
                {{ fromName }}
              </td>
              <td v-for="(_, toId) in transitions.state_names" :key="toId"
                class="text-center px-2 py-1 font-mono"
                :style="transitionCellStyle(Number(fromId), Number(toId))">
                {{ transitionProb(Number(fromId), Number(toId)) }}
              </td>
              <td class="text-center text-gray-500 px-2 py-1">
                {{ transitions.avg_durations[Number(fromId)] ?? '—' }}週
              </td>
            </tr>
          </tbody>
        </table>
        <p class="text-[10px] text-gray-400 mt-2">
          対角線 = 自己遷移確率 (同状態継続)。値は過去の実績に基づく推定値。
        </p>
      </div>
    </div>

  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { useApi } from "../composables/useApi";
import SectorReturnHeatmap from "../components/charts/SectorReturnHeatmap.vue";
import SectorRotationTimeline from "../components/charts/SectorRotationTimeline.vue";
import type {
	SectorRotationPrediction,
	SectorRotationTransitions,
} from "../types";
import { stateColor, stateColorBg } from "../utils/colors";

const api = useApi();

// ── 状態 ───────────────────────────────────────────────────────────
const prediction = ref<SectorRotationPrediction | null>(null);
const transitions = ref<SectorRotationTransitions | null>(null);
const loadingTransitions = ref(false);

const activeTab = ref<"heatmap" | "timeline" | "transitions">("heatmap");
const periodType = ref<"weekly" | "monthly">("weekly");
const heatmapPeriods = ref(12);
const timelineWeeks = ref(52);

const tabs = [
	{ value: "heatmap", label: "ヒートマップ" },
	{ value: "timeline", label: "タイムライン" },
	{ value: "transitions", label: "遷移行列" },
] as const;

const periodTypes = [
	{ value: "weekly" as const, label: "週次" },
	{ value: "monthly" as const, label: "月次" },
];

// ── 予測の確率ソート ────────────────────────────────────────────────
const sortedProba = computed(() =>
	[...(prediction.value?.all_probabilities ?? [])].sort(
		(a, b) => b.probability - a.probability,
	),
);

// ── 遷移行列ヘルパー ────────────────────────────────────────────────
function transitionProb(from: number, to: number): string {
	const entry = transitions.value?.transitions.find(
		(t) => t.from_state === from && t.to_state === to,
	);
	if (!entry || entry.probability < 0.001) return "—";
	return `${(entry.probability * 100).toFixed(0)}%`;
}

function transitionCellStyle(from: number, to: number): Record<string, string> {
	const entry = transitions.value?.transitions.find(
		(t) => t.from_state === from && t.to_state === to,
	);
	const prob = entry?.probability ?? 0;
	const isDiag = from === to;
	if (prob < 0.001) return { color: "#d1d5db" };
	const alpha = Math.min(1, prob * 3).toFixed(2);
	const color = isDiag
		? `rgba(59,130,246,${alpha})`
		: `rgba(107,114,128,${alpha})`;
	return { background: color, color: prob > 0.25 ? "#ffffff" : "#6b7280" };
}

// ── データ読み込み ──────────────────────────────────────────────────
async function loadPrediction() {
	try {
		prediction.value = await api.getSectorRotationPrediction();
	} catch (_) {
		/* noop */
	}
}

async function loadTransitions() {
	if (transitions.value) return;
	loadingTransitions.value = true;
	try {
		transitions.value = await api.getSectorRotationTransitions();
	} finally {
		loadingTransitions.value = false;
	}
}

// 遷移行列タブに切り替えたら自動ロード
watch(activeTab, (tab) => {
	if (tab === "transitions") loadTransitions();
});

onMounted(() => {
	loadPrediction();
});
</script>
