<script setup lang="ts">
import { ref, onMounted, computed } from "vue";
import { useRouter } from "vue-router";
import { useApi } from "../composables/useApi";
import AppHeader from "../components/layout/AppHeader.vue";
import HazardMap from "../components/map/HazardMap.vue";
import RiskSummaryCard from "../components/report/RiskSummaryCard.vue";
import HazardDetail from "../components/report/HazardDetail.vue";
import LoadingSpinner from "../components/shared/LoadingSpinner.vue";
import type { HazardReport } from "../types/report";
import type { HazardData } from "../types/hazard";
import { formatDateTime } from "../utils/formatters";

const props = defineProps<{ id: string }>();
const router = useRouter();
const api = useApi();

const report = ref<HazardReport | null>(null);
const hazardData = ref<HazardData | null>(null);
const isLoadingReport = ref(true);
const isFetchingHazard = ref(false);
const error = ref<string | null>(null);
const activeTab = ref<"summary" | "detail">("summary");

const overallLevel = computed(() => {
	return report.value?.report.risk_summary.overall_level ?? "unknown";
});

const overallLevelLabel: Record<string, string> = {
	low: "リスク低",
	medium: "リスク中程度",
	high: "リスク高",
	unknown: "要確認",
};

const overallLevelColor: Record<string, string> = {
	low: "text-green-700 bg-green-50 border-green-200",
	medium: "text-amber-700 bg-amber-50 border-amber-200",
	high: "text-orange-700 bg-orange-50 border-orange-200",
	unknown: "text-gray-600 bg-gray-50 border-gray-200",
};

onMounted(async () => {
	await loadReport();
});

async function loadReport() {
	isLoadingReport.value = true;
	error.value = null;

	try {
		// まずレポートを取得。なければハザードデータを先に取得
		try {
			report.value = await api.getReport(props.id);
		} catch (e: unknown) {
			const err = e as { response?: { status?: number } };
			if (err?.response?.status === 404) {
				// レポートなし → ハザードデータを取得してから再試行
				await fetchHazard();
				report.value = await api.getReport(props.id);
			} else {
				throw e;
			}
		}
	} catch (e) {
		console.error("レポート取得失敗:", e);
		error.value = "レポートの取得に失敗しました。";
	} finally {
		isLoadingReport.value = false;
	}
}

async function fetchHazard() {
	isFetchingHazard.value = true;
	try {
		hazardData.value = await api.getHazard(props.id);
	} catch (e: unknown) {
		const err = e as { response?: { status?: number } };
		if (err?.response?.status === 422) {
			throw new Error("この物件には緯度経度が設定されていません");
		}
		throw e;
	} finally {
		isFetchingHazard.value = false;
	}
}

async function refreshHazard() {
	isFetchingHazard.value = true;
	error.value = null;
	try {
		hazardData.value = await api.getHazard(props.id, true);
		report.value = await api.getReport(props.id);
	} catch (e) {
		console.error("ハザードデータ更新失敗:", e);
		error.value = "データの更新に失敗しました。";
	} finally {
		isFetchingHazard.value = false;
	}
}
</script>

<template>
  <div class="min-h-screen bg-gray-50">
    <AppHeader />

    <main class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <!-- ページヘッダー -->
      <div class="flex items-center gap-4 mb-6">
        <button
          class="text-gray-400 hover:text-gray-600 transition-colors"
          @click="router.push('/dashboard')"
        >
          ← 物件一覧
        </button>
      </div>

      <!-- ローディング -->
      <div v-if="isLoadingReport || isFetchingHazard" class="text-center py-16">
        <LoadingSpinner
          :message="isFetchingHazard ? 'ハザードデータを取得中...' : 'レポートを読み込み中...'"
        />
        <p v-if="isFetchingHazard" class="text-xs text-gray-400 mt-2">
          複数の公的データベースにアクセスしています（数秒かかる場合があります）
        </p>
      </div>

      <!-- エラー -->
      <div
        v-else-if="error"
        class="bg-red-50 border border-red-200 text-red-700 rounded-xl p-6 text-sm"
      >
        {{ error }}
        <button
          class="ml-4 underline text-red-600 hover:text-red-800"
          @click="loadReport"
        >
          再試行
        </button>
      </div>

      <!-- レポート -->
      <template v-else-if="report">
        <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <!-- 左カラム: 物件情報 + 地図 -->
          <div class="lg:col-span-1 space-y-4">
            <!-- 物件情報 -->
            <div class="bg-white rounded-xl border border-gray-200 p-5">
              <h2 class="font-semibold text-gray-900 text-lg mb-1">
                {{ report.property.property_name || "物件名未設定" }}
              </h2>
              <p class="text-sm text-gray-500 mb-3">{{ report.property.address }}</p>

              <!-- 総合リスクレベル -->
              <div
                :class="[
                  'border rounded-lg px-3 py-2 text-sm font-medium text-center mb-3',
                  overallLevelColor[overallLevel],
                ]"
              >
                総合リスク: {{ overallLevelLabel[overallLevel] }}
              </div>

              <!-- データ部分取得の警告 -->
              <div
                v-if="report.report.risk_summary.has_partial_data"
                class="bg-amber-50 border border-amber-200 rounded-lg p-2 text-xs text-amber-700 mb-3"
              >
                一部のデータが取得できませんでした（{{ report.report.risk_summary.unavailable_count }}件）
              </div>

              <!-- 更新ボタン -->
              <button
                class="w-full text-xs text-blue-600 hover:text-blue-800 border border-blue-200 rounded-lg py-2 hover:bg-blue-50 transition-colors"
                :disabled="isFetchingHazard"
                @click="refreshHazard"
              >
                ハザードデータを更新
              </button>

              <!-- フェッチ日時 -->
              <p class="text-xs text-gray-400 text-center mt-2">
                取得日時: {{ formatDateTime(report.report.fetched_at) }}
              </p>
            </div>

            <!-- 地図 -->
            <div
              v-if="report.property.latitude && report.property.longitude"
              class="bg-white rounded-xl border border-gray-200 p-4"
            >
              <h3 class="text-sm font-medium text-gray-700 mb-2">物件位置</h3>
              <HazardMap
                :latitude="report.property.latitude"
                :longitude="report.property.longitude"
                :address="report.property.address"
              />
            </div>
          </div>

          <!-- 右カラム: リスクレポート -->
          <div class="lg:col-span-2">
            <!-- タブ -->
            <div class="flex gap-1 mb-4 bg-gray-100 rounded-lg p-1">
              <button
                :class="[
                  'flex-1 py-2 text-sm font-medium rounded-md transition-colors',
                  activeTab === 'summary'
                    ? 'bg-white text-gray-900 shadow-sm'
                    : 'text-gray-500 hover:text-gray-700',
                ]"
                @click="activeTab = 'summary'"
              >
                リスクサマリー
              </button>
              <button
                :class="[
                  'flex-1 py-2 text-sm font-medium rounded-md transition-colors',
                  activeTab === 'detail'
                    ? 'bg-white text-gray-900 shadow-sm'
                    : 'text-gray-500 hover:text-gray-700',
                ]"
                @click="activeTab = 'detail'"
              >
                詳細データ
              </button>
            </div>

            <!-- サマリータブ -->
            <div v-if="activeTab === 'summary'" class="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <RiskSummaryCard
                v-for="card in report.report.cards"
                :key="card.risk_type"
                :card="card"
              />
            </div>

            <!-- 詳細タブ -->
            <div v-if="activeTab === 'detail' && hazardData">
              <HazardDetail :hazard="hazardData" />
            </div>
            <div v-else-if="activeTab === 'detail' && !hazardData" class="text-center py-8">
              <p class="text-sm text-gray-500">詳細データを読み込み中...</p>
            </div>

            <!-- 免責事項 -->
            <div class="mt-6 bg-gray-50 border border-gray-200 rounded-xl p-4">
              <h4 class="text-xs font-semibold text-gray-600 mb-1">免責事項</h4>
              <p class="text-xs text-gray-500 leading-relaxed">
                {{ report.disclaimer }}
              </p>
            </div>
          </div>
        </div>
      </template>
    </main>
  </div>
</template>
