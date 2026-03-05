<template>
  <div class="flex gap-1">
    <button
      v-for="p in periods"
      :key="p.value"
      class="px-2 py-0.5 text-xs rounded transition-colors"
      :class="modelValue === p.value
        ? 'bg-blue-600 text-white'
        : 'bg-gray-100 text-gray-600 hover:bg-gray-200'"
      @click="$emit('update:modelValue', p.value)"
    >
      {{ p.label }}
    </button>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  periods: { value: string | number; label: string }[];
  modelValue: string | number;
}>();

defineEmits<{
  "update:modelValue": [value: string | number];
}>();
</script>
