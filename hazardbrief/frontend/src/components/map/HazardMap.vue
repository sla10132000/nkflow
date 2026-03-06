<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch } from "vue";

const props = defineProps<{
	latitude: number;
	longitude: number;
	address?: string;
	zoom?: number;
}>();

const mapContainer = ref<HTMLDivElement | null>(null);
let mapInstance: unknown = null;
let markerInstance: unknown = null;

const initMap = async () => {
	if (!mapContainer.value) return;

	// Leaflet を動的インポート (SSR 非対応のため)
	const L = await import("leaflet");

	// デフォルトアイコン修正 (Vite ビルド時のパス問題対策)
	// biome-ignore lint/suspicious/noExplicitAny: Leaflet の内部型
	delete (L.Icon.Default.prototype as any)._getIconUrl;
	L.Icon.Default.mergeOptions({
		iconRetinaUrl: new URL("leaflet/dist/images/marker-icon-2x.png", import.meta.url).href,
		iconUrl: new URL("leaflet/dist/images/marker-icon.png", import.meta.url).href,
		shadowUrl: new URL("leaflet/dist/images/marker-shadow.png", import.meta.url).href,
	});

	const zoom = props.zoom ?? 15;
	const map = L.map(mapContainer.value).setView([props.latitude, props.longitude], zoom);

	L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
		attribution:
			'&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
		maxZoom: 19,
	}).addTo(map);

	const marker = L.marker([props.latitude, props.longitude]).addTo(map);

	if (props.address) {
		marker.bindPopup(`<b>${props.address}</b>`).openPopup();
	}

	mapInstance = map;
	markerInstance = marker;
};

onMounted(() => {
	initMap();
});

onUnmounted(() => {
	if (mapInstance) {
		// biome-ignore lint/suspicious/noExplicitAny: Leaflet インスタンス
		(mapInstance as any).remove();
		mapInstance = null;
	}
});

watch(
	() => [props.latitude, props.longitude],
	([newLat, newLon]) => {
		if (!mapInstance) return;
		// biome-ignore lint/suspicious/noExplicitAny: Leaflet インスタンス
		const map = mapInstance as any;
		map.setView([newLat, newLon]);
		if (markerInstance) {
			// biome-ignore lint/suspicious/noExplicitAny: Leaflet インスタンス
			(markerInstance as any).setLatLng([newLat, newLon]);
		}
	},
);
</script>

<template>
  <div class="relative w-full rounded-lg overflow-hidden border border-gray-200">
    <div ref="mapContainer" class="w-full h-64 md:h-80 z-0"></div>

    <!-- 地図の注記 -->
    <div class="absolute bottom-2 left-2 bg-white bg-opacity-90 rounded px-2 py-1 text-xs text-gray-500 z-10">
      地図: © OpenStreetMap contributors
    </div>
  </div>
</template>
