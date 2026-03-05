<template>
  <div class="relative w-full" style="height: 64px">
    <svg :viewBox="`0 0 ${width} ${height}`" preserveAspectRatio="none" class="w-full h-full">
      <!-- Area fill -->
      <polygon :points="areaPoints" :fill="color.fill" />
      <!-- Line -->
      <polyline :points="linePoints" fill="none" :stroke="color.stroke" stroke-width="1.5" stroke-linejoin="round" />
    </svg>
    <!-- Y axis labels -->
    <span class="absolute top-0 right-0 text-[10px] text-gray-400 leading-none">{{ maxLabel }}</span>
    <span class="absolute bottom-0 right-0 text-[10px] text-gray-400 leading-none">{{ minLabel }}</span>
    <!-- X axis labels -->
    <span class="absolute bottom-0 left-0 text-[10px] text-gray-400 leading-none">{{ firstDate }}</span>
    <span v-if="data.length > 1" class="absolute bottom-0 left-1/2 -translate-x-1/2 text-[10px] text-gray-400 leading-none">{{ lastDate }}</span>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";

interface DataPoint {
	date: string;
	close: number;
}

const props = defineProps<{ data: DataPoint[] }>();

const width = 200;
const height = 50;
const padY = 4;

const minVal = computed(() => Math.min(...props.data.map((d) => d.close)));
const maxVal = computed(() => Math.max(...props.data.map((d) => d.close)));

function toY(v: number): number {
	const range = maxVal.value - minVal.value || 1;
	return height - padY - ((v - minVal.value) / range) * (height - padY * 2);
}

function toX(i: number): number {
	const n = props.data.length;
	return n <= 1 ? width / 2 : (i / (n - 1)) * width;
}

const linePoints = computed(() =>
	props.data.map((d, i) => `${toX(i)},${toY(d.close)}`).join(" "),
);

const areaPoints = computed(() => {
	const pts = props.data.map((d, i) => `${toX(i)},${toY(d.close)}`);
	const n = props.data.length;
	return [...pts, `${toX(n - 1)},${height}`, `${toX(0)},${height}`].join(" ");
});

const color = computed(() => {
	if (props.data.length < 2)
		return { stroke: "#6b7280", fill: "rgba(107,114,128,0.1)" };
	const isUp = props.data[props.data.length - 1].close >= props.data[0].close;
	return isUp
		? { stroke: "#16a34a", fill: "rgba(22,163,74,0.1)" }
		: { stroke: "#dc2626", fill: "rgba(220,38,38,0.1)" };
});

const maxLabel = computed(() => maxVal.value.toLocaleString());
const minLabel = computed(() => minVal.value.toLocaleString());
const firstDate = computed(() => props.data[0]?.date.slice(5) ?? "");
const lastDate = computed(
	() => props.data[props.data.length - 1]?.date.slice(5) ?? "",
);
</script>
