<template>
  <div v-if="loading" class="text-gray-500 text-sm">読み込み中...</div>
  <div v-else-if="error" class="text-red-600 text-sm">{{ error }}</div>
  <div v-else-if="empty" class="text-gray-500 text-sm">
    <slot name="empty">データなし</slot>
  </div>
  <slot v-else />
</template>

<script setup lang="ts">
defineProps<{
	loading: boolean;
	error?: string;
	empty?: boolean;
}>();
</script>
