<script setup lang="ts">
import { useAuth0 } from "@auth0/auth0-vue";
import { RouterView } from "vue-router";

const { isLoading } = useAuth0();
</script>

<template>
  <div class="min-h-screen bg-gray-50">
    <div v-if="isLoading" class="flex items-center justify-center min-h-screen">
      <div class="text-center">
        <div class="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto mb-4"></div>
        <p class="text-gray-500">読み込み中...</p>
      </div>
    </div>
    <RouterView v-else />
  </div>
</template>
