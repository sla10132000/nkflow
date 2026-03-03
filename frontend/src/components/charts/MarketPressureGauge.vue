<template>
  <div class="flex flex-col items-center gap-2">
    <!-- 半円ゲージ -->
    <svg :width="svgW" :height="svgH" :viewBox="`0 0 ${svgW} ${svgH}`" class="overflow-visible">
      <!-- 背景 arc セグメント (大底→天井) -->
      <path v-for="seg in segments" :key="seg.zone"
        :d="seg.path" :fill="seg.color" opacity="0.7" />

      <!-- 針 -->
      <line
        :x1="cx" :y1="cy"
        :x2="needleTip.x" :y2="needleTip.y"
        stroke="#374151" stroke-width="2" stroke-linecap="round"
      />
      <circle :cx="cx" :cy="cy" r="4" fill="#374151" />

      <!-- 中央ラベル -->
      <text :x="cx" :y="cy + 20" text-anchor="middle" fill="#6b7280" font-size="11">
        {{ zoneLabel }}
      </text>
      <text :x="cx" :y="cy + 34" text-anchor="middle" fill="#111827" font-size="13" font-weight="bold">
        {{ plRatioLabel }}
      </text>

      <!-- 端ラベル -->
      <text x="8" :y="cy + 4" fill="#6b7280" font-size="9">大底</text>
      <text :x="svgW - 8" :y="cy + 4" text-anchor="end" fill="#6b7280" font-size="9">天井</text>
    </svg>

    <!-- buy_growth_4w バー -->
    <div class="w-full">
      <div class="flex justify-between text-xs text-gray-500 mb-1">
        <span>信用買残4週増加率</span>
        <span :class="buyGrowthClass">{{ buyGrowthLabel }}</span>
      </div>
      <div class="h-2 bg-gray-200 rounded-full overflow-hidden">
        <div
          class="h-full rounded-full transition-all duration-500"
          :class="buyGrowthBarClass"
          :style="{ width: buyGrowthBarWidth }"
        />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  plRatio: number | null
  plZone: string
  buyGrowth4w: number | null
}>()

const svgW = 200
const svgH = 110
const cx = svgW / 2
const cy = svgH - 10
const R = 80

// ゾーン定義: [開始率, 終了率, カラー]
const ZONE_DEFS: [number, number, string][] = [
  [-0.25, -0.15, '#1e3a5f'], // bottom  (濃紺)
  [-0.15, -0.10, '#1d4ed8'], // sellin  (青)
  [-0.10,  0.00, '#065f46'], // weak    (深緑)
  [ 0.00,  0.05, '#16a34a'], // neutral (緑)
  [ 0.05,  0.15, '#ca8a04'], // overheat(黄)
  [ 0.15,  0.20, '#dc2626'], // ceiling (赤)
]

const MIN_RATIO = -0.25
const MAX_RATIO =  0.20
const TOTAL_RANGE = MAX_RATIO - MIN_RATIO

function ratioToAngle(r: number): number {
  // 左端(180°) ～ 右端(0°) の半円
  const clamped = Math.max(MIN_RATIO, Math.min(MAX_RATIO, r))
  const pct = (clamped - MIN_RATIO) / TOTAL_RANGE
  return Math.PI - pct * Math.PI // 180° → 0°
}

function polarToCart(angle: number, r: number): { x: number; y: number } {
  return { x: cx + r * Math.cos(angle), y: cy - r * Math.sin(angle) }
}

function arcPath(ratioStart: number, ratioEnd: number): string {
  const a1 = ratioToAngle(ratioStart)
  const a2 = ratioToAngle(ratioEnd)
  const p1 = polarToCart(a1, R)
  const p2 = polarToCart(a2, R)
  const p1i = polarToCart(a1, R - 16)
  const p2i = polarToCart(a2, R - 16)
  return [
    `M ${p1.x} ${p1.y}`,
    `A ${R} ${R} 0 0 0 ${p2.x} ${p2.y}`,
    `L ${p2i.x} ${p2i.y}`,
    `A ${R - 16} ${R - 16} 0 0 1 ${p1i.x} ${p1i.y}`,
    'Z',
  ].join(' ')
}

const segments = computed(() =>
  ZONE_DEFS.map(([s, e, color]) => ({
    zone: `${s}_${e}`,
    path: arcPath(s, e),
    color,
  }))
)

const needleTip = computed(() => {
  const ratio = props.plRatio ?? 0
  const angle = ratioToAngle(ratio)
  return polarToCart(angle, R - 8)
})

const plRatioLabel = computed(() => {
  if (props.plRatio == null) return '—'
  return `${(props.plRatio * 100).toFixed(1)}%`
})

const zoneLabel = computed(() => {
  const labels: Record<string, string> = {
    ceiling: '天井警戒',
    overheat: '過熱',
    neutral: '中立',
    weak: '弱含み',
    sellin: '投げ売り',
    bottom: '大底',
  }
  return labels[props.plZone] ?? props.plZone
})

const buyGrowthLabel = computed(() => {
  if (props.buyGrowth4w == null) return '—'
  return `${(props.buyGrowth4w * 100).toFixed(1)}%`
})

const buyGrowthClass = computed(() => {
  const v = props.buyGrowth4w ?? 0
  if (v > 0.08) return 'text-red-600'
  if (v > 0) return 'text-amber-600'
  return 'text-green-600'
})

const buyGrowthBarClass = computed(() => {
  const v = props.buyGrowth4w ?? 0
  if (v > 0.08) return 'bg-red-500'
  if (v > 0) return 'bg-yellow-500'
  return 'bg-green-500'
})

const buyGrowthBarWidth = computed(() => {
  const v = props.buyGrowth4w ?? 0
  const pct = Math.min(100, Math.max(0, (v / 0.20) * 100))
  return `${pct}%`
})
</script>
