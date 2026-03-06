<script setup lang="ts">
import type { HazardData } from "../../types/hazard";
import { formatElevation } from "../../utils/formatters";

defineProps<{
	hazard: HazardData;
}>();
</script>

<template>
  <div class="space-y-4">
    <!-- 洪水リスク詳細 -->
    <div class="bg-white border border-gray-200 rounded-lg p-4">
      <h3 class="font-medium text-gray-900 mb-2 flex items-center gap-2">
        <span>🌊</span> 洪水リスク詳細
      </h3>
      <div v-if="hazard.flood_risk.available" class="space-y-1 text-sm text-gray-600">
        <div class="flex justify-between">
          <span class="text-gray-500">想定浸水深</span>
          <span class="font-medium">{{ hazard.flood_risk.depth_label }}</span>
        </div>
        <div v-if="hazard.flood_risk.river_name" class="flex justify-between">
          <span class="text-gray-500">対象河川</span>
          <span class="font-medium">{{ hazard.flood_risk.river_name }}</span>
        </div>
        <div class="flex justify-between text-xs text-gray-400 mt-1">
          <span>データ出典</span>
          <span>{{ hazard.flood_risk.source }}</span>
        </div>
      </div>
      <p v-else class="text-sm text-gray-500">データを取得できませんでした</p>
    </div>

    <!-- 土砂災害リスク詳細 -->
    <div class="bg-white border border-gray-200 rounded-lg p-4">
      <h3 class="font-medium text-gray-900 mb-2 flex items-center gap-2">
        <span>⛰</span> 土砂災害リスク詳細
      </h3>
      <div v-if="hazard.landslide_risk.available" class="space-y-1 text-sm text-gray-600">
        <div class="flex justify-between">
          <span class="text-gray-500">区域区分</span>
          <span class="font-medium">{{ hazard.landslide_risk.zone_label }}</span>
        </div>
        <div v-if="hazard.landslide_risk.disaster_type_label" class="flex justify-between">
          <span class="text-gray-500">災害種別</span>
          <span class="font-medium">{{ hazard.landslide_risk.disaster_type_label }}</span>
        </div>
        <div class="flex justify-between text-xs text-gray-400 mt-1">
          <span>データ出典</span>
          <span>{{ hazard.landslide_risk.source }}</span>
        </div>
      </div>
      <p v-else class="text-sm text-gray-500">データを取得できませんでした</p>
    </div>

    <!-- 津波リスク詳細 -->
    <div class="bg-white border border-gray-200 rounded-lg p-4">
      <h3 class="font-medium text-gray-900 mb-2 flex items-center gap-2">
        <span>🌊</span> 津波リスク詳細
      </h3>
      <div v-if="hazard.tsunami_risk.available" class="space-y-1 text-sm text-gray-600">
        <div class="flex justify-between">
          <span class="text-gray-500">想定浸水深</span>
          <span class="font-medium">{{ hazard.tsunami_risk.depth_label }}</span>
        </div>
        <div class="flex justify-between text-xs text-gray-400 mt-1">
          <span>データ出典</span>
          <span>{{ hazard.tsunami_risk.source }}</span>
        </div>
      </div>
      <p v-else class="text-sm text-gray-500">データを取得できませんでした</p>
    </div>

    <!-- 地盤リスク詳細 -->
    <div class="bg-white border border-gray-200 rounded-lg p-4">
      <h3 class="font-medium text-gray-900 mb-2 flex items-center gap-2">
        <span>🏔</span> 地盤リスク詳細
      </h3>
      <div v-if="hazard.ground_risk.available" class="space-y-1 text-sm text-gray-600">
        <div class="flex justify-between">
          <span class="text-gray-500">海抜標高</span>
          <span class="font-medium">{{ formatElevation(hazard.ground_risk.elevation) }}</span>
        </div>
        <div class="flex justify-between">
          <span class="text-gray-500">地盤評価</span>
          <span class="font-medium text-right max-w-48">{{ hazard.ground_risk.description }}</span>
        </div>
        <p class="text-xs text-gray-500 mt-2 pt-2 border-t border-gray-100">
          {{ hazard.ground_risk.liquefaction_note }}
        </p>
        <div class="flex justify-between text-xs text-gray-400 mt-1">
          <span>データ出典</span>
          <span>{{ hazard.ground_risk.source }}</span>
        </div>
      </div>
      <p v-else class="text-sm text-gray-500">データを取得できませんでした</p>
    </div>
  </div>
</template>
