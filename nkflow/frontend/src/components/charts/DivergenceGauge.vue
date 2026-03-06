<template>
  <div class="w-full">
    <!-- ゲージバー -->
    <svg :width="svgW" :height="svgH" :viewBox="`0 0 ${svgW} ${svgH}`" class="w-full overflow-visible">
      <!-- カラーゾーン -->
      <rect
        v-for="zone in zones"
        :key="zone.id"
        :x="zone.x"
        :y="barY"
        :width="zone.w"
        :height="barH"
        :fill="zone.color"
        :rx="zone.rx"
        :ry="zone.ry"
      />

      <!-- 中央ゼロライン -->
      <line
        :x1="centerX"
        :y1="barY - 4"
        :x2="centerX"
        :y2="barY + barH + 4"
        stroke="#9ca3af"
        stroke-width="1"
        stroke-dasharray="2,2"
      />

      <!-- インジケーター (現在値) -->
      <line
        v-if="indicatorX !== null"
        :x1="indicatorX"
        :y1="barY - 6"
        :x2="indicatorX"
        :y2="barY + barH + 6"
        stroke="#111827"
        stroke-width="2"
        stroke-linecap="round"
      />
      <polygon
        v-if="indicatorX !== null"
        :points="arrowPoints"
        fill="#111827"
      />

      <!-- 端ラベル -->
      <text :x="barX + 2" :y="barY + barH + 14" fill="#6b7280" font-size="9" text-anchor="start">底入れ</text>
      <text :x="barX + barW - 2" :y="barY + barH + 14" fill="#6b7280" font-size="9" text-anchor="end">天井警戒</text>
      <text :x="centerX" :y="barY + barH + 14" fill="#9ca3af" font-size="9" text-anchor="middle">0</text>

      <!-- 現在値ラベル -->
      <text
        v-if="props.value !== null"
        :x="Math.max(20, Math.min(svgW - 20, indicatorX ?? centerX))"
        :y="barY - 10"
        fill="#111827"
        font-size="11"
        font-weight="bold"
        text-anchor="middle"
      >{{ valueLabel }}</text>
    </svg>

    <!-- レジームラベル -->
    <div v-if="props.regime" class="mt-1 text-center">
      <span :class="regimeClass" class="text-xs px-2 py-0.5 rounded-full font-medium">
        {{ regimeLabel }}
      </span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";

const props = defineProps<{
	value: number | null;
	regime: string | null;
}>();

const svgW = 300;
const svgH = 54;
const barX = 10;
const barY = 18;
const barW = svgW - 20;
const barH = 16;
const centerX = barX + barW / 2;

// ゾーン定義: [from, to, color]  (-1.0 〜 +1.0)
const ZONE_DEFS: [number, number, string, string?][] = [
	[-1.0, -0.5, "#16a34a"], // 強い底入れ: 緑
	[-0.5, -0.2, "#86efac"], // 弱い底入れ: 薄緑
	[-0.2, 0.2, "#d1d5db"], // 中立: 灰
	[0.2, 0.5, "#fca5a5"], // 弱い天井警戒: 薄赤
	[0.5, 1.0, "#ef4444"], // 強い天井警戒: 赤
];

function valueToX(v: number): number {
	const clamped = Math.max(-1, Math.min(1, v));
	return barX + ((clamped + 1) / 2) * barW;
}

const zones = computed(() =>
	ZONE_DEFS.map(([from, to, color], i) => {
		const x1 = valueToX(from);
		const x2 = valueToX(to);
		return {
			id: `zone-${i}`,
			x: x1,
			w: x2 - x1,
			color,
			// 角丸は左端と右端のみ
			rx: i === 0 || i === ZONE_DEFS.length - 1 ? 3 : 0,
			ry: i === 0 || i === ZONE_DEFS.length - 1 ? 3 : 0,
		};
	}),
);

const indicatorX = computed(() =>
	props.value !== null ? valueToX(props.value) : null,
);

// 上向き三角 (インジケーターの上端)
const arrowPoints = computed(() => {
	const x = indicatorX.value ?? centerX;
	const y = barY - 6;
	return `${x},${y} ${x - 4},${y - 5} ${x + 4},${y - 5}`;
});

const valueLabel = computed(() => {
	if (props.value === null) return "";
	return props.value.toFixed(2);
});

const regimeLabel = computed(() => {
	const labels: Record<string, string> = {
		bullish: "強気 (外国人買い優勢)",
		bull: "強気 (外国人買い優勢)",
		bearish: "弱気 (個人買い優勢)",
		bear: "弱気 (個人買い優勢)",
		neutral: "中立",
		diverging: "乖離拡大",
	};
	return labels[props.regime ?? ""] ?? props.regime ?? "";
});

const regimeClass = computed(() => {
	switch (props.regime) {
		case "bullish":
		case "bull":
			return "bg-blue-100 text-blue-700";
		case "bearish":
		case "bear":
			return "bg-red-100 text-red-700";
		case "diverging":
			return "bg-amber-100 text-amber-700";
		default:
			return "bg-gray-100 text-gray-600";
	}
});
</script>
