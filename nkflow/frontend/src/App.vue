<template>
  <div class="min-h-screen flex flex-col">
    <nav class="bg-white border-b border-gray-200 shadow-sm px-2 py-1.5">
      <div class="max-w-screen-2xl mx-auto flex items-center gap-4">
        <RouterLink to="/" class="text-lg font-bold text-gray-900">nkflow</RouterLink>
        <RouterLink to="/" class="nav-link">概要</RouterLink>
        <RouterLink to="/news" class="nav-link">ニュース</RouterLink>
        <RouterLink to="/commodities" class="nav-link">コモディティ</RouterLink>
        <RouterLink to="/timeseries" class="nav-link">銘柄チャート</RouterLink>
        <RouterLink to="/sector-rotation" class="nav-link">ローテーション</RouterLink>
        <RouterLink to="/network" class="nav-link">資金フロー</RouterLink>
        <RouterLink to="/us-market" class="nav-link">米国市場</RouterLink>

        <!-- 右端: ユーザー情報 + ログアウト -->
        <div class="ml-auto flex items-center gap-2">
          <template v-if="isAuthenticated">
            <img
              v-if="user?.picture"
              :src="user.picture"
              :alt="user.name ?? 'user'"
              class="w-7 h-7 rounded-full border border-gray-200"
            />
            <span class="text-xs text-gray-600 hidden sm:inline">{{ user?.name }}</span>
            <button
              class="text-xs text-gray-500 hover:text-gray-800 border border-gray-200 rounded px-2 py-1 transition-colors"
              @click="logout({ logoutParams: { returnTo: window.location.origin } })"
            >
              ログアウト
            </button>
          </template>
          <template v-else-if="!isLoading">
            <button
              class="text-xs bg-blue-600 text-white rounded px-3 py-1.5 hover:bg-blue-700 transition-colors"
              @click="loginWithRedirect()"
            >
              ログイン
            </button>
          </template>
        </div>
      </div>
    </nav>
    <main class="flex-1 max-w-screen-2xl mx-auto w-full px-2 py-2">
      <RouterView />
    </main>
  </div>
</template>

<script setup lang="ts">
import { useAuth0 } from "@auth0/auth0-vue";

const { isAuthenticated, isLoading, user, loginWithRedirect, logout } =
	useAuth0();
const window = globalThis.window;
</script>

<style scoped>
.nav-link {
  @apply text-gray-600 hover:text-gray-900 transition-colors text-sm;
}
.nav-link.router-link-active {
  @apply text-blue-600 font-medium;
}
</style>
