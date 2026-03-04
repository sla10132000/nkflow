<template>
  <div class="space-y-3">
    <h1 class="text-xl font-bold">時系列チャート</h1>

    <!-- コントロール -->
    <div class="flex flex-wrap gap-3 items-center">
      <div class="relative">
        <input
          v-model="searchInput"
          @keyup.enter="onEnter"
          @input="onInput"
          @blur="hideDropdownDelayed"
          @focus="onFocus"
          placeholder="銘柄コード or 銘柄名"
          class="bg-white border border-gray-300 rounded px-3 py-1.5 text-sm w-56 focus:outline-none focus:border-blue-500"
          autocomplete="off"
        />
        <!-- オートコンプリートドロップダウン -->
        <ul
          v-if="showDropdown && suggestions.length"
          class="absolute z-50 top-full left-0 mt-1 w-80 bg-white border border-gray-200 rounded shadow-lg max-h-60 overflow-y-auto text-sm"
        >
          <li
            v-for="stock in suggestions"
            :key="stock.code"
            @mousedown.prevent="selectStock(stock)"
            class="px-3 py-2 cursor-pointer hover:bg-blue-50 flex gap-2 items-center"
          >
            <span class="font-mono text-blue-700 w-12 shrink-0">{{ stock.code }}</span>
            <span class="text-gray-800 truncate flex-1">{{ stock.name }}</span>
            <span class="text-gray-400 text-xs shrink-0">{{ stock.sector }}</span>
          </li>
        </ul>
      </div>
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
        <h2 class="font-semibold mb-2">{{ chartTitle }}</h2>
        <div class="h-64">
          <PriceChart :prices="prices" />
        </div>
      </div>

      <!-- データテーブル -->
      <div class="card overflow-x-auto">
        <h2 class="font-semibold mb-2">価格データ</h2>
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
import { computed, onMounted, ref } from "vue";
import PriceChart from "../components/charts/PriceChart.vue";
import { useApi } from "../composables/useApi";
import type { DailyPrice, Stock } from "../types";

const api = useApi();
const searchInput = ref("");
const selectedCode = ref("");
const selectedStock = ref<Stock | null>(null);
const stocks = ref<Stock[]>([]);
const prices = ref<DailyPrice[]>([]);
const loading = ref(false);
const error = ref("");
const activePeriod = ref(60);
const showDropdown = ref(false);

const periods = [
	{ label: "1M", days: 20 },
	{ label: "3M", days: 60 },
	{ label: "6M", days: 120 },
	{ label: "1Y", days: 250 },
];

const suggestions = computed(() => {
	const q = searchInput.value.trim().toLowerCase();
	if (!q) return [];
	return stocks.value
		.filter(
			(s) =>
				s.code.toLowerCase().includes(q) ||
				s.name.toLowerCase().includes(q),
		)
		.slice(0, 10);
});

const chartTitle = computed(() => {
	if (selectedStock.value) {
		return `${selectedStock.value.code} ${selectedStock.value.name} 終値`;
	}
	return `${selectedCode.value} 終値`;
});

onMounted(async () => {
	try {
		stocks.value = await api.getStocks();
	} catch {
		// 銘柄リスト取得失敗は無視 (オートコンプリートなしで動作継続)
	}
});

function onInput() {
	showDropdown.value = true;
	selectedStock.value = null;
	selectedCode.value = "";
}

function onFocus() {
	if (searchInput.value.trim()) showDropdown.value = true;
}

function hideDropdownDelayed() {
	setTimeout(() => {
		showDropdown.value = false;
	}, 150);
}

function selectStock(stock: Stock) {
	searchInput.value = `${stock.code} ${stock.name}`;
	selectedCode.value = stock.code;
	selectedStock.value = stock;
	showDropdown.value = false;
	loadPrices();
}

function onEnter() {
	const q = searchInput.value.trim();
	if (!q) return;
	// コード完全一致
	const exactCode = stocks.value.find((s) => s.code === q);
	if (exactCode) {
		selectStock(exactCode);
		return;
	}
	// サジェスト候補の先頭
	if (suggestions.value.length > 0) {
		selectStock(suggestions.value[0]);
		return;
	}
	// 候補なし → 入力をそのままコードとして使用
	selectedCode.value = q;
	selectedStock.value = null;
	showDropdown.value = false;
	loadPrices();
}

function toDate(daysAgo: number) {
	const d = new Date();
	d.setDate(d.getDate() - daysAgo);
	return d.toISOString().split("T")[0];
}

async function loadPrices() {
	const code = selectedCode.value || searchInput.value.trim();
	if (!code) return;
	selectedCode.value = code;
	loading.value = true;
	error.value = "";
	try {
		prices.value = await api.getPrices(code, toDate(activePeriod.value));
	} catch (e: unknown) {
		error.value = e instanceof Error ? e.message : "データ取得失敗";
		prices.value = [];
	} finally {
		loading.value = false;
	}
}

async function setPeriod(days: number) {
	activePeriod.value = days;
	if (selectedCode.value || searchInput.value.trim()) await loadPrices();
}
</script>

<style scoped>
.card { @apply bg-white rounded-lg p-3 border border-gray-200 shadow-sm; }
.btn-primary { @apply bg-blue-600 hover:bg-blue-500 text-white px-4 py-1.5 rounded text-sm transition-colors; }
.btn-period { @apply px-3 py-1 rounded text-sm border border-gray-300 text-gray-600 hover:border-blue-500 hover:text-blue-600 transition-colors; }
.btn-period-active { @apply border-blue-500 text-blue-600 bg-blue-50; }
</style>
