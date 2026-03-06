import { defineStore } from "pinia";
import { computed, ref } from "vue";
import { useApi } from "../composables/useApi";
import type { DailySummary, FearIndices, Stock } from "../types";

const CACHE_TTL = 5 * 60 * 1000; // 5分

/**
 * 全ページで共有するマーケットデータのストア。
 *
 * - summary: 最新の日次サマリ
 * - fearIndices: VIX / Fear & Greed
 * - stocks: 銘柄マスタ (検索・オートコンプリート用)
 */
export const useMarketStore = defineStore("market", () => {
	const api = useApi();

	// ── 状態 ─────────────────────────────────────────
	const summary = ref<DailySummary | null>(null);
	const summaryHistory = ref<DailySummary[]>([]);
	const fearIndices = ref<FearIndices | null>(null);
	const stocks = ref<Stock[]>([]);

	const _summaryFetchedAt = ref(0);
	const _fearIndicesFetchedAt = ref(0);
	const _stocksFetchedAt = ref(0);

	// ── computed ─────────────────────────────────────
	const regime = computed(() => summary.value?.regime ?? "neutral");

	// ── アクション ───────────────────────────────────
	async function fetchSummary(days = 30, force = false) {
		if (
			!force &&
			Date.now() - _summaryFetchedAt.value < CACHE_TTL &&
			summary.value
		) {
			return;
		}
		try {
			const data = await api.getSummary(days);
			const arr = Array.isArray(data) ? data : [data];
			summaryHistory.value = arr;
			summary.value = arr[0] ?? null;
			_summaryFetchedAt.value = Date.now();
		} catch {
			// 取得失敗時は既存データを保持
		}
	}

	async function fetchFearIndices(force = false) {
		if (
			!force &&
			Date.now() - _fearIndicesFetchedAt.value < CACHE_TTL &&
			fearIndices.value
		) {
			return;
		}
		try {
			fearIndices.value = await api.getFearIndices();
			_fearIndicesFetchedAt.value = Date.now();
		} catch {
			// ignore
		}
	}

	async function fetchStocks(force = false) {
		if (
			!force &&
			Date.now() - _stocksFetchedAt.value < CACHE_TTL &&
			stocks.value.length
		) {
			return;
		}
		try {
			stocks.value = await api.getStocks();
			_stocksFetchedAt.value = Date.now();
		} catch {
			// ignore
		}
	}

	return {
		summary,
		summaryHistory,
		fearIndices,
		stocks,
		regime,
		fetchSummary,
		fetchFearIndices,
		fetchStocks,
	};
});
