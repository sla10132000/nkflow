<script setup lang="ts">
import type { SupercycleSector, SupercyclePhase } from "../../types";

const props = defineProps<{
	phases: Record<string, SupercyclePhase>;
	sectors: SupercycleSector[];
}>();

// セクターカラー
const SECTOR_COLORS: Record<string, string> = {
	energy: "#f97316",
	base_metals: "#6366f1",
	precious_metals: "#eab308",
	battery_metals: "#22c55e",
	agriculture: "#84cc16",
};

// position (1.0〜4.99) → 横座標 % に変換
function positionToPercent(position: number): number {
	// 4フェーズ = 0%〜100%。各フェーズは25%幅
	const pct = ((position - 1) / 4) * 100;
	return Math.min(Math.max(pct, 1), 99);
}

// セクター内の全コモディティを position でソート
interface DotItem {
	ticker: string;
	label: string;
	sectorId: string;
	position: number;
	phase: number;
	isEtf: boolean;
}

const dots = computed<DotItem[]>(() => {
	const items: DotItem[] = [];
	for (const sector of props.sectors) {
		for (const c of sector.commodities) {
			items.push({
				ticker: c.ticker,
				label: c.label,
				sectorId: sector.id,
				position: c.position,
				phase: c.phase,
				isEtf: c.is_etf,
			});
		}
	}
	return items;
});

const phaseEntries = computed(() =>
	Object.entries(props.phases).map(([id, p]) => ({ id, ...p })),
);
</script>

<script lang="ts">
import { computed } from "vue";
export default { name: "SupercyclePhaseChart" };
</script>

<template>
	<div class="supercycle-phase-chart">
		<!-- フェーズゾーン背景 -->
		<div class="phase-track">
			<div
				v-for="ph in phaseEntries"
				:key="ph.id"
				class="phase-zone"
				:style="{ backgroundColor: ph.color + '22', borderRight: '1px solid ' + ph.color + '66' }"
			>
				<span class="phase-label" :style="{ color: ph.color }">
					Phase {{ ph.id }}<br />
					<span class="phase-name">{{ ph.name }}（{{ ph.subtitle }}）</span>
				</span>
			</div>
		</div>

		<!-- ドットレイヤー -->
		<div class="dots-layer">
			<div
				v-for="dot in dots"
				:key="dot.ticker"
				class="dot-wrapper"
				:style="{ left: positionToPercent(dot.position) + '%' }"
				:title="`${dot.label} (${dot.ticker}) — Phase ${dot.phase} pos:${dot.position}`"
			>
				<div
					class="dot"
					:class="{ 'dot-etf': dot.isEtf }"
					:style="{ backgroundColor: SECTOR_COLORS[dot.sectorId] ?? '#94a3b8' }"
				/>
				<span class="dot-label">{{ dot.label }}</span>
			</div>
		</div>

		<!-- 凡例 -->
		<div class="legend">
			<div
				v-for="sector in sectors"
				:key="sector.id"
				class="legend-item"
			>
				<span
					class="legend-dot"
					:style="{ backgroundColor: SECTOR_COLORS[sector.id] ?? '#94a3b8' }"
				/>
				<span class="legend-text">{{ sector.label }}</span>
			</div>
			<div class="legend-item ml-4">
				<span class="legend-dot-etf" />
				<span class="legend-text">ETF代替</span>
			</div>
		</div>
	</div>
</template>

<style scoped>
.supercycle-phase-chart {
	position: relative;
	width: 100%;
	user-select: none;
}

/* 4等分フェーズゾーン */
.phase-track {
	display: flex;
	width: 100%;
	height: 60px;
	border: 1px solid #e5e7eb;
	border-radius: 8px;
	overflow: hidden;
}

.phase-zone {
	flex: 1;
	display: flex;
	align-items: flex-start;
	padding: 4px 6px;
}

.phase-zone:last-child {
	border-right: none !important;
}

.phase-label {
	font-size: 10px;
	font-weight: 600;
	line-height: 1.3;
}

.phase-name {
	font-size: 9px;
	font-weight: 400;
}

/* ドット配置レイヤー */
.dots-layer {
	position: relative;
	height: 56px;
	margin-top: 8px;
}

.dot-wrapper {
	position: absolute;
	transform: translateX(-50%);
	display: flex;
	flex-direction: column;
	align-items: center;
	cursor: default;
}

.dot {
	width: 12px;
	height: 12px;
	border-radius: 50%;
	border: 2px solid white;
	box-shadow: 0 1px 3px rgba(0, 0, 0, 0.3);
	transition: transform 0.15s;
}

.dot:hover {
	transform: scale(1.4);
}

/* ETF は四角形 */
.dot-etf {
	border-radius: 2px;
}

.dot-label {
	font-size: 9px;
	color: #374151;
	white-space: nowrap;
	margin-top: 2px;
	font-weight: 500;
}

/* 凡例 */
.legend {
	display: flex;
	flex-wrap: wrap;
	gap: 8px 16px;
	margin-top: 12px;
	padding-top: 8px;
	border-top: 1px solid #e5e7eb;
}

.legend-item {
	display: flex;
	align-items: center;
	gap: 4px;
}

.legend-dot {
	display: inline-block;
	width: 10px;
	height: 10px;
	border-radius: 50%;
	border: 1.5px solid white;
	box-shadow: 0 1px 2px rgba(0, 0, 0, 0.2);
}

.legend-dot-etf {
	display: inline-block;
	width: 10px;
	height: 10px;
	border-radius: 2px;
	background: #94a3b8;
	border: 1.5px solid white;
	box-shadow: 0 1px 2px rgba(0, 0, 0, 0.2);
}

.legend-text {
	font-size: 11px;
	color: #374151;
}

.ml-4 {
	margin-left: 16px;
}
</style>
