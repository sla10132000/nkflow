<script setup lang="ts">
import { ref, onMounted } from "vue";
import { useRouter } from "vue-router";
import { useApi } from "../composables/useApi";
import { useAuth } from "../composables/useAuth";
import AppHeader from "../components/layout/AppHeader.vue";
import LoadingSpinner from "../components/shared/LoadingSpinner.vue";
import type { Property } from "../types/property";
import { formatDate } from "../utils/formatters";

const router = useRouter();
const api = useApi();
const { isAuthenticated, login } = useAuth();

const properties = ref<Property[]>([]);
const isLoading = ref(true);
const error = ref<string | null>(null);
const deleteConfirmId = ref<string | null>(null);

onMounted(async () => {
	if (!isAuthenticated.value) {
		login();
		return;
	}
	await loadProperties();
});

async function loadProperties() {
	isLoading.value = true;
	error.value = null;
	try {
		properties.value = await api.getProperties();
	} catch (e) {
		error.value = "物件一覧の取得に失敗しました。";
		console.error(e);
	} finally {
		isLoading.value = false;
	}
}

async function deleteProperty(id: string) {
	try {
		await api.deleteProperty(id);
		properties.value = properties.value.filter((p) => p.id !== id);
		deleteConfirmId.value = null;
	} catch (e) {
		console.error("削除失敗:", e);
		error.value = "削除に失敗しました。";
	}
}

function goToDetail(id: string) {
	router.push(`/properties/${id}`);
}
</script>

<template>
  <div class="min-h-screen bg-gray-50">
    <AppHeader />

    <main class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <!-- ページヘッダー -->
      <div class="flex items-center justify-between mb-6">
        <div>
          <h1 class="text-2xl font-bold text-gray-900">物件一覧</h1>
          <p class="text-sm text-gray-500 mt-1">登録済み物件の防災レポートを確認できます</p>
        </div>
        <RouterLink
          to="/properties/new"
          class="bg-blue-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-blue-700 transition-colors flex items-center gap-2"
        >
          <span>+</span>
          物件を登録
        </RouterLink>
      </div>

      <!-- エラー -->
      <div v-if="error" class="bg-red-50 border border-red-200 text-red-700 rounded-lg p-4 mb-6 text-sm">
        {{ error }}
      </div>

      <!-- ローディング -->
      <LoadingSpinner v-if="isLoading" message="物件一覧を読み込み中..." />

      <!-- 空の状態 -->
      <div
        v-else-if="properties.length === 0"
        class="text-center py-16 bg-white rounded-xl border border-dashed border-gray-300"
      >
        <div class="text-5xl mb-4">🏠</div>
        <h3 class="text-lg font-medium text-gray-900 mb-2">物件が登録されていません</h3>
        <p class="text-sm text-gray-500 mb-6">住所を入力して防災レポートを自動生成しましょう</p>
        <RouterLink
          to="/properties/new"
          class="inline-block bg-blue-600 text-white px-6 py-2 rounded-lg text-sm font-medium hover:bg-blue-700 transition-colors"
        >
          最初の物件を登録する
        </RouterLink>
      </div>

      <!-- 物件カード一覧 -->
      <div v-else class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        <div
          v-for="property in properties"
          :key="property.id"
          class="bg-white rounded-xl border border-gray-200 p-5 hover:shadow-md transition-shadow cursor-pointer"
          @click="goToDetail(property.id)"
        >
          <div class="flex items-start justify-between mb-3">
            <div class="flex-1 min-w-0">
              <h3 class="font-semibold text-gray-900 truncate">
                {{ property.property_name || "物件名未設定" }}
              </h3>
              <p class="text-xs text-gray-500 mt-1 truncate">{{ property.address }}</p>
            </div>
            <button
              class="ml-2 text-gray-400 hover:text-red-500 transition-colors p-1 shrink-0"
              @click.stop="deleteConfirmId = property.id"
            >
              ✕
            </button>
          </div>

          <!-- 座標バッジ -->
          <div class="flex items-center gap-2 text-xs text-gray-400 mb-3">
            <span v-if="property.latitude && property.longitude">
              📍 {{ property.latitude.toFixed(4) }}, {{ property.longitude.toFixed(4) }}
            </span>
            <span v-else class="text-amber-500">📍 座標未設定</span>
          </div>

          <div class="flex items-center justify-between">
            <span class="text-xs text-gray-400">{{ formatDate(property.created_at) }}</span>
            <button
              class="text-xs text-blue-600 hover:text-blue-800 font-medium"
              @click.stop="goToDetail(property.id)"
            >
              レポートを見る →
            </button>
          </div>
        </div>
      </div>
    </main>

    <!-- 削除確認ダイアログ -->
    <div
      v-if="deleteConfirmId"
      class="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4"
      @click.self="deleteConfirmId = null"
    >
      <div class="bg-white rounded-xl p-6 max-w-sm w-full shadow-xl">
        <h3 class="font-semibold text-gray-900 mb-2">物件を削除しますか？</h3>
        <p class="text-sm text-gray-500 mb-4">
          この操作は取り消せません。関連するハザードレポートも削除されます。
        </p>
        <div class="flex gap-3">
          <button
            class="flex-1 bg-gray-100 text-gray-700 py-2 rounded-lg text-sm font-medium hover:bg-gray-200 transition-colors"
            @click="deleteConfirmId = null"
          >
            キャンセル
          </button>
          <button
            class="flex-1 bg-orange-600 text-white py-2 rounded-lg text-sm font-medium hover:bg-orange-700 transition-colors"
            @click="deleteProperty(deleteConfirmId)"
          >
            削除する
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
