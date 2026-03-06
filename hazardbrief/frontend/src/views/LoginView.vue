<script setup lang="ts">
import { useAuth } from "../composables/useAuth";
import { useRouter } from "vue-router";
import { watchEffect } from "vue";

const { isAuthenticated, isLoading, login } = useAuth();
const router = useRouter();

// 認証済みの場合はダッシュボードへ
watchEffect(() => {
	if (!isLoading.value && isAuthenticated.value) {
		router.push("/dashboard");
	}
});
</script>

<template>
  <div class="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-100 flex items-center justify-center p-4">
    <div class="bg-white rounded-2xl shadow-lg p-8 max-w-md w-full">
      <!-- ロゴ -->
      <div class="text-center mb-8">
        <div class="w-16 h-16 bg-blue-600 rounded-2xl flex items-center justify-center mx-auto mb-4">
          <span class="text-white text-2xl font-bold">HB</span>
        </div>
        <h1 class="text-2xl font-bold text-gray-900">HazardBrief</h1>
        <p class="text-gray-500 mt-1 text-sm">防災レポート自動生成サービス</p>
      </div>

      <!-- 機能説明 -->
      <div class="space-y-3 mb-8">
        <div class="flex items-start gap-3">
          <span class="text-blue-600 mt-0.5">✓</span>
          <div>
            <p class="text-sm font-medium text-gray-900">住所入力で自動レポート生成</p>
            <p class="text-xs text-gray-500">洪水・土砂・津波・地盤リスクを一括取得</p>
          </div>
        </div>
        <div class="flex items-start gap-3">
          <span class="text-blue-600 mt-0.5">✓</span>
          <div>
            <p class="text-sm font-medium text-gray-900">公的データを根拠に表示</p>
            <p class="text-xs text-gray-500">国土交通省・国土地理院の公式データを使用</p>
          </div>
        </div>
        <div class="flex items-start gap-3">
          <span class="text-blue-600 mt-0.5">✓</span>
          <div>
            <p class="text-sm font-medium text-gray-900">リスクと対策をセットで提示</p>
            <p class="text-xs text-gray-500">お客様への説明をサポートします</p>
          </div>
        </div>
      </div>

      <!-- ログインボタン -->
      <button
        class="w-full bg-blue-600 text-white py-3 px-4 rounded-lg font-medium hover:bg-blue-700 transition-colors disabled:opacity-50"
        :disabled="isLoading"
        @click="login"
      >
        <span v-if="isLoading">読み込み中...</span>
        <span v-else>ログイン / 新規登録</span>
      </button>

      <!-- 免責事項 -->
      <p class="text-xs text-gray-400 text-center mt-4 leading-relaxed">
        本サービスは公的機関のデータを参考情報として提供します。
        物件の安全性については専門家にご相談ください。
      </p>
    </div>
  </div>
</template>
