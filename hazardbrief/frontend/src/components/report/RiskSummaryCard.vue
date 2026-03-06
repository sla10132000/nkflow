<script setup lang="ts">
import type { RiskCard } from "../../types/report";
import { getRiskColorClass, getRiskBadgeClass } from "../../utils/formatters";

defineProps<{
	card: RiskCard;
}>();

const riskTypeIcons: Record<string, string> = {
	flood: "🌊",
	landslide: "⛰",
	tsunami: "🌊",
	ground: "🏔",
};
</script>

<template>
  <div
    :class="[
      'border rounded-lg p-4 transition-all',
      getRiskColorClass(card.level),
    ]"
  >
    <!-- ヘッダー -->
    <div class="flex items-center justify-between mb-3">
      <div class="flex items-center gap-2">
        <span class="text-xl">{{ riskTypeIcons[card.risk_type] }}</span>
        <h3 class="font-semibold text-sm">{{ card.title }}</h3>
      </div>
      <span
        v-if="card.available"
        :class="[
          'text-xs font-bold px-2 py-1 rounded-full',
          getRiskBadgeClass(card.level),
        ]"
      >
        {{ card.level_label }}
      </span>
      <span
        v-else
        class="text-xs font-bold px-2 py-1 rounded-full bg-gray-100 text-gray-500"
      >
        要確認
      </span>
    </div>

    <!-- 説明 -->
    <p class="text-xs mb-2">{{ card.description }}</p>

    <!-- データ取得不可の場合 -->
    <div
      v-if="!card.available"
      class="text-xs text-gray-500 bg-gray-50 rounded p-2 mb-2 border border-gray-200"
    >
      データを取得できませんでした。市区町村のハザードマップをご確認ください。
    </div>

    <!-- 対策ヒント -->
    <div
      v-if="card.mitigation"
      class="mt-3 pt-3 border-t border-current border-opacity-20"
    >
      <p class="text-xs font-medium mb-1">対策のポイント</p>
      <p class="text-xs opacity-80">{{ card.mitigation }}</p>
    </div>
  </div>
</template>
