<template>
  <div class="min-h-screen flex flex-col">
    <nav class="bg-white border-b border-gray-200 shadow-sm px-4 py-3">
      <div class="max-w-screen-2xl mx-auto flex items-center gap-6">
        <RouterLink to="/" class="text-lg font-bold text-gray-900">nkflow</RouterLink>
        <RouterLink to="/" class="nav-link">概要</RouterLink>
        <RouterLink to="/news" class="nav-link">ニュース</RouterLink>
        <RouterLink to="/timeseries" class="nav-link">時系列</RouterLink>
        <RouterLink to="/sector-rotation" class="nav-link">ローテーション</RouterLink>
        <RouterLink to="/network" class="nav-link">資金フロー</RouterLink>
      </div>
    </nav>
    <main class="flex-1 max-w-screen-2xl mx-auto w-full px-4 py-4">
      <RouterView />
    </main>
  </div>
</template>

<script setup lang="ts">
</script>

<style scoped>
.nav-link {
  @apply text-gray-600 hover:text-gray-900 transition-colors text-sm;
}
.nav-link.router-link-active {
  @apply text-blue-600 font-medium;
}
</style>
