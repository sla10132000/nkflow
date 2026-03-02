<template>
  <div class="min-h-screen flex flex-col">
    <nav class="bg-gray-900 border-b border-gray-800 px-4 py-3">
      <div class="max-w-7xl mx-auto flex items-center gap-6">
        <RouterLink to="/" class="text-lg font-bold text-white">nkflow</RouterLink>
        <RouterLink to="/" class="nav-link">概要</RouterLink>
        <RouterLink to="/timeseries" class="nav-link">時系列</RouterLink>
        <RouterLink to="/network" class="nav-link">資金フロー</RouterLink>
        <RouterLink to="/signals" class="nav-link">シグナル</RouterLink>
        <RouterLink to="/sector-rotation" class="nav-link">ローテーション</RouterLink>
      </div>
    </nav>
    <main class="flex-1 max-w-7xl mx-auto w-full px-4 py-6">
      <RouterView />
    </main>
  </div>
</template>

<style scoped>
.nav-link {
  @apply text-gray-400 hover:text-white transition-colors text-sm;
}
.nav-link.router-link-active {
  @apply text-blue-400;
}
</style>
