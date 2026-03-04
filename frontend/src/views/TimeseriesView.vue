<template>
  <div class="space-y-6">
    <h1 class="text-2xl font-bold">時系列チャート</h1>

    <!-- コントロール -->
    <div class="flex flex-wrap gap-3 items-center">
      <input
        v-model="codeInput"
        @keyup.enter="loadPrices"
        placeholder="銘柄コード (例: 7203)"
        class="bg-white border border-gray-300 rounded px-3 py-1.5 text-sm w-36 focus:outline-none focus:border-blue-500"
      />
      <button @click="loadPrices" class="btn-primary">表示</button>

      <div class="flex gap-2 ml-auto">
        <button
          v-for="p in periods"
          :key="p.label"
          @click="setPeriod(p.days)"
          class="btn-period"
          :class="{ 'btn-period-active': activePeriod === p.days }"
        >{{ p.label }}</button>
      </div>
    </div>

    <div v-if="loading" class="text-gray-500">読み込み中...</div>
    <div v-else-if="error" class="text-red-600">{{ error }}</div>

    <template v-else-if="prices.length">
      <!-- 株価チャート -->
      <div class="card">
        <h2 class="font-semibold mb-2">{{ codeInput }} 終値</h2>
        <div class="h-64">
          <PriceChart :prices="prices" />
        </div>
      </div>

      <!-- データテーブル -->
      <div class="card overflow-x-auto">
        <h2 class="font-semibold mb-3">価格データ</h2>
        <table class="w-full text-sm">
          <thead>
            <tr class="text-gray-500 text-left border-b border-gray-200">
              <th class="pb-2">日付</th>
              <th class="pb-2 text-right">始値</th>
              <th class="pb-2 text-right">高値</th>
              <th class="pb-2 text-right">安値</th>
              <th class="pb-2 text-right">終値</th>
              <th class="pb-2 text-right">騰落率</th>
              <th class="pb-2 text-right">出来高</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="p in prices.slice().reverse().slice(0, 30)"
              :key="p.date"
              class="border-t border-gray-100"
            >
              <td class="py-1 text-gray-700">{{ p.date }}</td>
              <td class="py-1 text-right">{{ p.open?.toLocaleString() }}</td>
              <td class="py-1 text-right">{{ p.high?.toLocaleString() }}</td>
              <td class="py-1 text-right">{{ p.low?.toLocaleString() }}</td>
              <td class="py-1 text-right">{{ p.close?.toLocaleString() }}</td>
              <td class="py-1 text-right" :class="p.return_rate >= 0 ? 'text-green-600' : 'text-red-600'">
                {{ p.return_rate != null ? ((p.return_rate >= 0 ? '+' : '') + (p.return_rate * 100).toFixed(2) + '%') : '—' }}
              </td>
              <td class="py-1 text-right text-gray-500">{{ p.volume?.toLocaleString() }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>

    <div v-else-if="!loading" class="text-gray-500">銘柄コードを入力して「表示」を押してください</div>
  </div>
</template>

<script setup lang="ts">
import { ref } from "vue";
import { useApi } from "../composables/useApi";
import type { DailyPrice } from "../types";

const api = useApi();
const codeInput = ref("");
const prices = ref<DailyPrice[]>([]);
const loading = ref(false);
const error = ref("");
const activePeriod = ref(60);

const periods = [
	{ label: "1M", days: 20 },
	{ label: "3M", days: 60 },
	{ label: "6M", days: 120 },
	{ label: "1Y", days: 250 },
];

function toDate(daysAgo: number) {
	const d = new Date();
	d.setDate(d.getDate() - daysAgo);
	return d.toISOString().split("T")[0];
}

async function loadPrices() {
	if (!codeInput.value.trim()) return;
	loading.value = true;
	error.value = "";
	try {
		prices.value = await api.getPrices(
			codeInput.value.trim(),
			toDate(activePeriod.value),
		);
	} catch (e: unknown) {
		error.value = e instanceof Error ? e.message : "データ取得失敗";
		prices.value = [];
	} finally {
		loading.value = false;
	}
}

async function setPeriod(days: number) {
	activePeriod.value = days;
	if (codeInput.value.trim()) await loadPrices();
}
</script>

<style scoped>
.card { @apply bg-white rounded-lg p-4 border border-gray-200 shadow-sm; }
.btn-primary { @apply bg-blue-600 hover:bg-blue-500 text-white px-4 py-1.5 rounded text-sm transition-colors; }
.btn-period { @apply px-3 py-1 rounded text-sm border border-gray-300 text-gray-600 hover:border-blue-500 hover:text-blue-600 transition-colors; }
.btn-period-active { @apply border-blue-500 text-blue-600 bg-blue-50; }
</style>
