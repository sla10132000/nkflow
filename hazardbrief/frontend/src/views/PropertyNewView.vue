<script setup lang="ts">
import { ref, watch } from "vue";
import { useRouter } from "vue-router";
import { useApi } from "../composables/useApi";
import AppHeader from "../components/layout/AppHeader.vue";
import HazardMap from "../components/map/HazardMap.vue";
import LoadingSpinner from "../components/shared/LoadingSpinner.vue";

const router = useRouter();
const api = useApi();

const address = ref("");
const propertyName = ref("");
const notes = ref("");
const isSubmitting = ref(false);
const isGeocoding = ref(false);
const error = ref<string | null>(null);

// 地図プレビュー用
const previewLat = ref<number | null>(null);
const previewLon = ref<number | null>(null);
const geocodeError = ref<string | null>(null);

// アドレス入力から地図プレビュー更新
let geocodeTimer: ReturnType<typeof setTimeout> | null = null;

watch(address, (newAddress) => {
	if (geocodeTimer) clearTimeout(geocodeTimer);
	if (!newAddress || newAddress.length < 5) {
		previewLat.value = null;
		previewLon.value = null;
		return;
	}
	geocodeTimer = setTimeout(() => {
		previewGeocode(newAddress);
	}, 800);
});

async function previewGeocode(addr: string) {
	isGeocoding.value = true;
	geocodeError.value = null;
	try {
		const resp = await fetch(
			`https://msearch.gsi.go.jp/address-search/AddressSearch?q=${encodeURIComponent(addr)}`,
		);
		const data = await resp.json();
		if (data && data.length > 0) {
			const [lon, lat] = data[0].geometry.coordinates;
			previewLat.value = lat;
			previewLon.value = lon;
		} else {
			geocodeError.value = "住所が見つかりませんでした。住所を確認してください。";
			previewLat.value = null;
			previewLon.value = null;
		}
	} catch {
		geocodeError.value = "住所の検索に失敗しました。";
	} finally {
		isGeocoding.value = false;
	}
}

async function submitForm() {
	if (!address.value.trim()) {
		error.value = "住所は必須です。";
		return;
	}

	isSubmitting.value = true;
	error.value = null;

	try {
		const prop = await api.createProperty({
			address: address.value.trim(),
			property_name: propertyName.value.trim() || undefined,
			notes: notes.value.trim() || undefined,
			latitude: previewLat.value ?? undefined,
			longitude: previewLon.value ?? undefined,
		});

		// 登録成功 → 詳細ページへ
		router.push(`/properties/${prop.id}`);
	} catch (e) {
		console.error("物件登録失敗:", e);
		error.value = "物件の登録に失敗しました。しばらくしてからお試しください。";
	} finally {
		isSubmitting.value = false;
	}
}
</script>

<template>
  <div class="min-h-screen bg-gray-50">
    <AppHeader />

    <main class="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <!-- ページヘッダー -->
      <div class="flex items-center gap-4 mb-6">
        <button
          class="text-gray-400 hover:text-gray-600 transition-colors"
          @click="router.back()"
        >
          ← 戻る
        </button>
        <h1 class="text-2xl font-bold text-gray-900">物件を登録</h1>
      </div>

      <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <!-- フォーム -->
        <div class="bg-white rounded-xl border border-gray-200 p-6">
          <form @submit.prevent="submitForm" class="space-y-5">
            <!-- エラーメッセージ -->
            <div
              v-if="error"
              class="bg-red-50 border border-red-200 text-red-700 rounded-lg p-3 text-sm"
            >
              {{ error }}
            </div>

            <!-- 住所 (必須) -->
            <div>
              <label class="block text-sm font-medium text-gray-700 mb-1">
                住所 <span class="text-red-500">*</span>
              </label>
              <input
                v-model="address"
                type="text"
                placeholder="例: 東京都千代田区丸の内1-1-1"
                class="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                :disabled="isSubmitting"
              />
              <p class="text-xs text-gray-400 mt-1">
                入力すると自動的に地図にプレビューします
              </p>
              <p v-if="geocodeError" class="text-xs text-amber-600 mt-1">
                {{ geocodeError }}
              </p>
            </div>

            <!-- 物件名 -->
            <div>
              <label class="block text-sm font-medium text-gray-700 mb-1">
                物件名（任意）
              </label>
              <input
                v-model="propertyName"
                type="text"
                placeholder="例: 〇〇マンション 201号室"
                class="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                :disabled="isSubmitting"
              />
            </div>

            <!-- メモ -->
            <div>
              <label class="block text-sm font-medium text-gray-700 mb-1">
                メモ（任意）
              </label>
              <textarea
                v-model="notes"
                placeholder="商談メモや物件の特記事項など"
                rows="3"
                class="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent resize-none"
                :disabled="isSubmitting"
              ></textarea>
            </div>

            <!-- 送信ボタン -->
            <button
              type="submit"
              class="w-full bg-blue-600 text-white py-3 rounded-lg font-medium hover:bg-blue-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              :disabled="isSubmitting || !address.trim()"
            >
              <span v-if="isSubmitting">
                <span class="animate-spin inline-block w-4 h-4 border-2 border-white border-t-transparent rounded-full mr-2 align-middle"></span>
                登録中...
              </span>
              <span v-else>物件を登録してレポートを生成</span>
            </button>

            <!-- 注記 -->
            <p class="text-xs text-gray-400 leading-relaxed">
              登録後、自動的にハザードデータを取得します（数秒かかる場合があります）。
            </p>
          </form>
        </div>

        <!-- 地図プレビュー -->
        <div class="bg-white rounded-xl border border-gray-200 p-6">
          <h2 class="text-sm font-medium text-gray-700 mb-3">地図プレビュー</h2>

          <div v-if="isGeocoding" class="flex items-center justify-center h-64 bg-gray-50 rounded-lg">
            <LoadingSpinner size="sm" message="住所を検索中..." />
          </div>

          <div
            v-else-if="previewLat && previewLon"
          >
            <HazardMap
              :latitude="previewLat"
              :longitude="previewLon"
              :address="address"
            />
            <p class="text-xs text-gray-400 mt-2">
              緯度: {{ previewLat.toFixed(6) }}, 経度: {{ previewLon.toFixed(6) }}
            </p>
          </div>

          <div
            v-else
            class="flex items-center justify-center h-64 bg-gray-50 rounded-lg border border-dashed border-gray-300"
          >
            <div class="text-center text-gray-400">
              <p class="text-2xl mb-2">🗺</p>
              <p class="text-xs">住所を入力すると地図が表示されます</p>
            </div>
          </div>
        </div>
      </div>
    </main>
  </div>
</template>
