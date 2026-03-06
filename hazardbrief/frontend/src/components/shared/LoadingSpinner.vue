<script setup lang="ts">
defineProps<{
	message?: string;
	size?: "sm" | "md" | "lg";
}>();
</script>

<template>
  <div class="flex flex-col items-center justify-center p-8">
    <div
      :class="[
        'animate-spin rounded-full border-b-2 border-blue-600',
        size === 'sm' ? 'h-6 w-6' : size === 'lg' ? 'h-16 w-16' : 'h-12 w-12',
      ]"
    ></div>
    <p v-if="message" class="mt-3 text-sm text-gray-500">{{ message }}</p>
  </div>
</template>
