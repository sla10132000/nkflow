<template>
  <div class="space-y-3">
    <div class="flex items-center gap-3">
      <button @click="$router.back()" class="text-gray-500 hover:text-gray-900">← 戻る</button>
      <h1 class="text-xl font-bold">{{ code }}</h1>
      <span v-if="detail?.name" class="text-gray-600">{{ detail.name }}</span>
      <span v-if="detail?.sector" class="badge-sector">{{ detail.sector }}</span>
    </div>

    <LoadingState :loading="loading" :error="error">
    <template v-if="detail">
      <!-- 最新データ -->
      <div class="grid grid-cols-2 md:grid-cols-4 gap-3" v-if="latest">
        <div class="card">
          <div class="label">終値</div>
          <div class="value">¥{{ latest.close?.toLocaleString() }}</div>
        </div>
        <div class="card">
          <div class="label">騰落率</div>
          <div class="value" :class="latest.return_rate >= 0 ? 'text-green-600' : 'text-red-600'">
            {{ formatReturn(latest.return_rate) }}
          </div>
        </div>
        <div class="card">
          <div class="label">値幅</div>
          <div class="value">{{ latest.price_range?.toLocaleString() }}</div>
        </div>
        <div class="card">
          <div class="label">出来高</div>
          <div class="value text-base">{{ latest.volume?.toLocaleString() }}</div>
        </div>
      </div>

      <!-- 株価チャート (TD Sequential 統合) -->
      <div class="card">
        <div class="flex items-center gap-3 mb-2 flex-wrap">
          <h2 class="font-semibold">株価チャート</h2>
          <!-- TD Sequential トグル + ステータス + 凡例 (日足のみ) -->
          <template v-if="timeframe === 'daily'">
            <button
              v-if="tdData.length"
              @click="showTd = !showTd"
              class="text-xs px-1.5 py-0.5 rounded border transition-colors"
              :class="showTd ? 'border-blue-400 text-blue-600 bg-blue-50' : 'border-gray-300 text-gray-400'"
            >TD</button>
            <div v-if="showTd && tdLatest" class="flex items-center gap-2 text-xs flex-wrap">
              <span class="text-gray-400 text-xs">TD</span>
              <template v-if="tdLatest.setup_bull > 0">
                <span class="font-mono font-bold text-green-600">
                  ▲S {{ tdLatest.setup_bull }}/9<span v-if="tdLatest.setup_bull === 9"> ✓</span>
                </span>
              </template>
              <template v-if="tdLatest.countdown_bull > 0">
                <span class="font-mono font-bold text-sky-600">
                  ▲CD {{ tdLatest.countdown_bull }}/13<span v-if="tdLatest.countdown_bull === 13"> 🔔</span>
                </span>
              </template>
              <template v-if="tdLatest.setup_bear > 0">
                <span class="font-mono font-bold text-red-600">
                  ▼S {{ tdLatest.setup_bear }}/9<span v-if="tdLatest.setup_bear === 9"> ✓</span>
                </span>
              </template>
              <template v-if="tdLatest.countdown_bear > 0">
                <span class="font-mono font-bold text-purple-600">
                  ▼CD {{ tdLatest.countdown_bear }}/13<span v-if="tdLatest.countdown_bear === 13"> 🔔</span>
                </span>
              </template>
              <!-- 凡例 -->
              <span class="text-gray-300">|</span>
              <span class="text-gray-400">凡例:</span>
              <span class="text-green-600">緑=強S</span>
              <span class="text-sky-600">水=強CD</span>
              <span class="text-red-600">赤=弱S</span>
              <span class="text-purple-600">紫=弱CD</span>
            </div>
          </template>
          <div class="ml-auto">
            <PeriodSelector :periods="timeframes" :model-value="timeframe" @update:model-value="timeframe = $event as Timeframe" />
          </div>
        </div>
        <div class="h-72">
          <PriceChart
            v-if="chartPrices.length"
            :prices="chartPrices"
            :tdData="timeframe === 'daily' && tdData.length ? tdData : undefined"
            :showTd="timeframe === 'daily' && showTd"
          />
          <div v-else class="text-gray-500 text-sm">価格データなし</div>
        </div>
      </div>

      <!-- 因果連鎖 -->
      <div class="grid md:grid-cols-2 gap-3">
        <div class="card">
          <h2 class="font-semibold mb-2 text-blue-600">この銘柄が因果する銘柄</h2>
          <div v-if="detail.causes?.length" class="space-y-1">
            <div v-for="c in detail.causes" :key="c.target" class="flex items-center gap-2 text-sm">
              <RouterLink :to="`/stock/${c.target}`" class="text-blue-600 hover:underline">{{ c.target }}</RouterLink>
              <span class="text-gray-600 truncate flex-1">{{ c.name }}</span>
              <span class="text-gray-500 text-xs">lag {{ c.lag_days }}d</span>
              <span class="text-gray-500 text-xs">p={{ c.p_value?.toFixed(3) }}</span>
            </div>
          </div>
          <div v-else class="text-gray-500 text-sm">なし</div>
        </div>

        <div class="card">
          <h2 class="font-semibold mb-2 text-purple-600">この銘柄を因果する銘柄</h2>
          <div v-if="detail.caused_by?.length" class="space-y-1">
            <div v-for="c in detail.caused_by" :key="c.source" class="flex items-center gap-2 text-sm">
              <RouterLink :to="`/stock/${c.source}`" class="text-blue-600 hover:underline">{{ c.source }}</RouterLink>
              <span class="text-gray-600 truncate flex-1">{{ c.name }}</span>
              <span class="text-gray-500 text-xs">lag {{ c.lag_days }}d</span>
            </div>
          </div>
          <div v-else class="text-gray-500 text-sm">なし</div>
        </div>
      </div>

      <!-- 相関銘柄 -->
      <div class="card">
        <h2 class="font-semibold mb-2">高相関銘柄</h2>
        <div v-if="detail.correlated?.length" class="flex flex-wrap gap-2">
          <RouterLink
            v-for="c in detail.correlated"
            :key="c.peer_code"
            :to="`/stock/${c.peer_code}`"
            class="px-2 py-1 bg-gray-100 rounded text-sm hover:bg-gray-200 transition-colors"
          >
            {{ c.peer_code }} <span class="text-gray-500 text-xs">{{ (c.coefficient * 100).toFixed(0) }}%</span>
          </RouterLink>
        </div>
        <div v-else class="text-gray-500 text-sm">なし</div>
      </div>

      <!-- クラスター内銘柄 -->
      <div class="card" v-if="detail.cluster?.members?.length">
        <h2 class="font-semibold mb-2">同クラスター銘柄</h2>
        <div class="flex flex-wrap gap-2">
          <RouterLink
            v-for="m in detail.cluster!.members"
            :key="m.code"
            :to="`/stock/${m.code}`"
            class="px-2 py-1 bg-gray-100 rounded text-sm hover:bg-gray-200 transition-colors"
          >{{ m.code }}</RouterLink>
        </div>
      </div>

      <!-- 関連シグナル -->
      <div class="card" v-if="detail.signals?.length">
        <h2 class="font-semibold mb-2">関連シグナル</h2>
        <div class="space-y-2">
          <div v-for="s in detail.signals" :key="s.id" class="flex items-center gap-3 text-sm border-t border-gray-200 pt-2">
            <span class="text-gray-500">{{ s.date }}</span>
            <span class="badge" :class="s.direction === 'bullish' ? 'badge-green' : 'badge-red'">{{ s.direction }}</span>
            <span class="text-gray-600">{{ s.signal_type }}</span>
            <span class="ml-auto text-gray-600">{{ (s.confidence * 100).toFixed(0) }}%</span>
          </div>
        </div>
      </div>
    </template>
    </LoadingState>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import PriceChart from "../components/charts/PriceChart.vue";
import LoadingState from "../components/shared/LoadingState.vue";
import PeriodSelector from "../components/shared/PeriodSelector.vue";
import { useApi } from "../composables/useApi";
import type { DailyPrice, StockDetail, TdSequentialBar } from "../types";
import { aggregateOHLCV, type Timeframe } from "../utils/aggregateOHLCV";
import { toDate } from "../utils/dateRange";
import { formatReturn } from "../utils/formatters";

const props = defineProps<{ code: string }>();
const api = useApi();
const loading = ref(true);
const error = ref("");
const detail = ref<StockDetail | null>(null);
const prices = ref<DailyPrice[]>([]);
const timeframe = ref<Timeframe>("daily");
const tdData = ref<TdSequentialBar[]>([]);
const tdLatest = ref<TdSequentialBar | null>(null);
const showTd = ref(true); // TD Sequential 表示切替

const latest = computed(() => detail.value?.recent_prices?.[0] ?? null);
const chartPrices = computed(() =>
	aggregateOHLCV(prices.value, timeframe.value),
);

const LOAD_DAYS = 1250; // 5年分をロード (月足で ~60本)

const timeframes: { value: Timeframe; label: string }[] = [
	{ value: "daily", label: "日足" },
	{ value: "weekly", label: "週足" },
	{ value: "monthly", label: "月足" },
];

async function loadTdData(days = LOAD_DAYS) {
	try {
		const [latest, series] = await Promise.all([
			api.getTdSequentialLatest(props.code),
			api.getTdSequential(props.code, days),
		]);
		tdLatest.value = latest;
		tdData.value = series ?? [];
	} catch {
		// TD Sequential データなし — 表示なし
	}
}

// 5年分のデータを一括ロード (足種変更時はデータ再取得不要)
async function loadPrices() {
	try {
		prices.value = await api.getPrices(props.code, toDate(LOAD_DAYS));
		await loadTdData(LOAD_DAYS);
	} catch {
		/* ignore */
	}
}

async function loadDetail() {
	loading.value = true;
	error.value = "";
	try {
		detail.value = await api.getStock(props.code);
		await loadPrices();
	} catch (e: unknown) {
		error.value = e instanceof Error ? e.message : "データ取得失敗";
	} finally {
		loading.value = false;
	}
}

onMounted(loadDetail);
watch(() => props.code, loadDetail);
</script>

<style scoped>
.card { @apply bg-white rounded-lg p-3 border border-gray-200 shadow-sm; }
.label { @apply text-gray-500 text-xs mb-1; }
.value { @apply text-xl font-bold; }
.badge { @apply px-2 py-0.5 rounded text-xs font-medium; }
.badge-green { @apply bg-green-100 text-green-700; }
.badge-red { @apply bg-red-100 text-red-700; }
.badge-sector { @apply px-2 py-0.5 rounded text-xs bg-indigo-100 text-indigo-700; }
.btn-sm { @apply px-2 py-0.5 rounded text-xs border border-gray-300 text-gray-600 hover:text-gray-900 transition-colors; }
.btn-sm-active { @apply border-blue-500 text-blue-600 bg-blue-50; }
</style>
