<script setup lang="ts">
import { useAuth } from "../../composables/useAuth";
import { useRouter } from "vue-router";

const { isAuthenticated, displayName, login, logout } = useAuth();
const router = useRouter();
</script>

<template>
  <header class="bg-white border-b border-gray-200 sticky top-0 z-50">
    <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
      <div class="flex justify-between items-center h-16">
        <!-- ロゴ -->
        <div class="flex items-center gap-2 cursor-pointer" @click="router.push('/dashboard')">
          <div class="w-8 h-8 bg-blue-600 rounded-lg flex items-center justify-center">
            <span class="text-white text-xs font-bold">HB</span>
          </div>
          <span class="font-semibold text-gray-900 text-lg">HazardBrief</span>
        </div>

        <!-- ナビゲーション -->
        <nav v-if="isAuthenticated" class="hidden md:flex items-center gap-6">
          <RouterLink
            to="/dashboard"
            class="text-sm text-gray-600 hover:text-blue-600 transition-colors"
            active-class="text-blue-600 font-medium"
          >
            物件一覧
          </RouterLink>
          <RouterLink
            to="/properties/new"
            class="text-sm text-gray-600 hover:text-blue-600 transition-colors"
            active-class="text-blue-600 font-medium"
          >
            物件登録
          </RouterLink>
          <RouterLink
            to="/settings"
            class="text-sm text-gray-600 hover:text-blue-600 transition-colors"
            active-class="text-blue-600 font-medium"
          >
            設定
          </RouterLink>
        </nav>

        <!-- ユーザーメニュー -->
        <div class="flex items-center gap-4">
          <template v-if="isAuthenticated">
            <span class="text-sm text-gray-600 hidden md:block">{{ displayName }}</span>
            <button
              class="text-sm text-gray-500 hover:text-gray-700 transition-colors"
              @click="logout"
            >
              ログアウト
            </button>
          </template>
          <template v-else>
            <button
              class="bg-blue-600 text-white text-sm px-4 py-2 rounded-md hover:bg-blue-700 transition-colors"
              @click="login"
            >
              ログイン
            </button>
          </template>
        </div>
      </div>
    </div>
  </header>
</template>
