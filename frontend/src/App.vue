<template>
  <div class="min-h-screen flex flex-col">
    <nav class="bg-gray-900 border-b border-gray-800 px-4 py-3">
      <div class="max-w-7xl mx-auto flex items-center gap-6">
        <RouterLink to="/" class="text-lg font-bold text-white">nkflow</RouterLink>
        <template v-if="isAuthenticated">
          <RouterLink to="/" class="nav-link">概要</RouterLink>
          <RouterLink to="/timeseries" class="nav-link">時系列</RouterLink>
          <RouterLink to="/network" class="nav-link">資金フロー</RouterLink>
          <RouterLink to="/signals" class="nav-link">シグナル</RouterLink>
          <RouterLink to="/sector-rotation" class="nav-link">ローテーション</RouterLink>
        </template>
        <div class="ml-auto flex items-center gap-3">
          <template v-if="isAuthenticated">
            <img
              v-if="user?.picture"
              :src="user.picture"
              :alt="user.name ?? 'user'"
              class="w-8 h-8 rounded-full"
            />
            <span class="text-gray-300 text-sm hidden sm:inline">{{ user?.name }}</span>
            <button
              class="text-sm text-gray-400 hover:text-white border border-gray-700 hover:border-gray-500 px-3 py-1 rounded transition-colors"
              @click="logout({ logoutParams: { returnTo: window.location.origin } })"
            >
              ログアウト
            </button>
          </template>
          <template v-else-if="!isLoading">
            <button
              class="text-sm text-white bg-blue-600 hover:bg-blue-500 px-4 py-1.5 rounded transition-colors"
              @click="loginWithRedirect()"
            >
              Googleでログイン
            </button>
          </template>
        </div>
      </div>
    </nav>
    <main class="flex-1 max-w-7xl mx-auto w-full px-4 py-6">
      <RouterView />
    </main>
  </div>
</template>

<script setup lang="ts">
import { useAuth0 } from '@auth0/auth0-vue'

const { isAuthenticated, isLoading, user, loginWithRedirect, logout } = useAuth0()
</script>

<style scoped>
.nav-link {
  @apply text-gray-400 hover:text-white transition-colors text-sm;
}
.nav-link.router-link-active {
  @apply text-blue-400;
}
</style>
