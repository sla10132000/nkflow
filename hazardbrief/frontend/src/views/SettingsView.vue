<script setup lang="ts">
import { ref, onMounted } from "vue";
import { useAuth } from "../composables/useAuth";
import { useApi } from "../composables/useApi";
import AppHeader from "../components/layout/AppHeader.vue";
import type { Company } from "../types/property";

const { displayName, userEmail, logout } = useAuth();
const api = useApi();

const companies = ref<Company[]>([]);
const isLoadingCompanies = ref(false);
const newCompanyName = ref("");
const isCreatingCompany = ref(false);
const successMessage = ref<string | null>(null);

const planLabels: Record<string, string> = {
	free: "フリープラン",
	standard: "スタンダードプラン",
	enterprise: "エンタープライズプラン",
};

onMounted(async () => {
	await loadCompanies();
});

async function loadCompanies() {
	isLoadingCompanies.value = true;
	try {
		companies.value = await api.getCompanies();
	} catch (e) {
		console.error("会社一覧取得失敗:", e);
	} finally {
		isLoadingCompanies.value = false;
	}
}

async function createCompany() {
	if (!newCompanyName.value.trim()) return;
	isCreatingCompany.value = true;
	try {
		await api.createCompany(newCompanyName.value.trim());
		newCompanyName.value = "";
		await loadCompanies();
		successMessage.value = "会社を登録しました。";
		setTimeout(() => { successMessage.value = null; }, 3000);
	} catch (e) {
		console.error("会社登録失敗:", e);
	} finally {
		isCreatingCompany.value = false;
	}
}
</script>

<template>
  <div class="min-h-screen bg-gray-50">
    <AppHeader />

    <main class="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <h1 class="text-2xl font-bold text-gray-900 mb-6">設定</h1>

      <!-- 成功メッセージ -->
      <div
        v-if="successMessage"
        class="bg-green-50 border border-green-200 text-green-700 rounded-lg p-3 text-sm mb-6"
      >
        {{ successMessage }}
      </div>

      <!-- ユーザー情報 -->
      <div class="bg-white rounded-xl border border-gray-200 p-6 mb-6">
        <h2 class="text-base font-semibold text-gray-900 mb-4">アカウント情報</h2>
        <div class="space-y-3">
          <div class="flex justify-between text-sm">
            <span class="text-gray-500">名前</span>
            <span class="text-gray-900 font-medium">{{ displayName }}</span>
          </div>
          <div class="flex justify-between text-sm">
            <span class="text-gray-500">メールアドレス</span>
            <span class="text-gray-900">{{ userEmail }}</span>
          </div>
        </div>
        <div class="mt-4 pt-4 border-t border-gray-100">
          <button
            class="text-sm text-gray-500 hover:text-gray-700 transition-colors"
            @click="logout"
          >
            ログアウト
          </button>
        </div>
      </div>

      <!-- 会社管理 -->
      <div class="bg-white rounded-xl border border-gray-200 p-6 mb-6">
        <h2 class="text-base font-semibold text-gray-900 mb-4">会社管理</h2>

        <!-- 会社一覧 -->
        <div v-if="isLoadingCompanies" class="text-sm text-gray-400 mb-4">読み込み中...</div>
        <div v-else-if="companies.length === 0" class="text-sm text-gray-400 mb-4">
          会社が登録されていません
        </div>
        <ul v-else class="space-y-2 mb-4">
          <li
            v-for="company in companies"
            :key="company.id"
            class="flex items-center justify-between p-3 bg-gray-50 rounded-lg"
          >
            <div>
              <p class="text-sm font-medium text-gray-900">{{ company.name }}</p>
              <p class="text-xs text-gray-400">{{ planLabels[company.plan] ?? company.plan }}</p>
            </div>
          </li>
        </ul>

        <!-- 会社登録フォーム -->
        <div class="flex gap-3">
          <input
            v-model="newCompanyName"
            type="text"
            placeholder="会社名を入力"
            class="flex-1 border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            :disabled="isCreatingCompany"
            @keydown.enter="createCompany"
          />
          <button
            class="bg-blue-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-blue-700 transition-colors disabled:opacity-50"
            :disabled="isCreatingCompany || !newCompanyName.trim()"
            @click="createCompany"
          >
            登録
          </button>
        </div>
      </div>

      <!-- データソース情報 -->
      <div class="bg-white rounded-xl border border-gray-200 p-6">
        <h2 class="text-base font-semibold text-gray-900 mb-4">データソース</h2>
        <div class="space-y-3 text-sm">
          <div class="flex justify-between">
            <span class="text-gray-600">洪水・土砂・津波リスク</span>
            <a
              href="https://www.reinfolib.mlit.go.jp/"
              target="_blank"
              rel="noopener noreferrer"
              class="text-blue-600 hover:underline"
            >
              国土交通省 不動産情報ライブラリ
            </a>
          </div>
          <div class="flex justify-between">
            <span class="text-gray-600">地盤・標高情報</span>
            <a
              href="https://maps.gsi.go.jp/"
              target="_blank"
              rel="noopener noreferrer"
              class="text-blue-600 hover:underline"
            >
              国土地理院
            </a>
          </div>
          <div class="flex justify-between">
            <span class="text-gray-600">ジオコーディング</span>
            <a
              href="https://maps.gsi.go.jp/development/geocoding.html"
              target="_blank"
              rel="noopener noreferrer"
              class="text-blue-600 hover:underline"
            >
              国土地理院 住所検索API
            </a>
          </div>
        </div>

        <!-- 免責事項 -->
        <div class="mt-4 pt-4 border-t border-gray-100">
          <p class="text-xs text-gray-400 leading-relaxed">
            本サービスのレポートは公的機関が公表するデータを基に作成しています。
            ハザードマップは想定最大規模の災害を示すものであり、実際の被害程度は
            地形・建物構造・気象条件等により異なります。物件の安全性判断は、
            現地確認・専門家への相談と合わせてご活用ください。
          </p>
        </div>
      </div>
    </main>
  </div>
</template>
