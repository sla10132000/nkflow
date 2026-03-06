<template>
  <div ref="container" class="w-full h-full rounded" />
</template>

<script setup lang="ts">
import { DataSet } from "vis-data";
import { Network } from "vis-network";
import { onBeforeUnmount, onMounted, ref, watch } from "vue";
import type { NetworkData } from "../../types";
import { SECTOR_COLORS } from "../../utils/colors";

const props = defineProps<{
	data: NetworkData;
	directed?: boolean;
	anchorMode?: boolean; // true = アンカー設定済み: 流入先ノードを大きく、エッジを太く強調
}>();

const emit = defineEmits<{ nodeClick: [id: string] }>();

const container = ref<HTMLElement>();
let network: Network | null = null;

// SECTOR_COLORS は utils/colors.ts から import

function buildNetwork() {
	if (!container.value || !props.data) return;

	const nodeColor = (group: string) => SECTOR_COLORS[group] ?? "#60a5fa";

	// 市場圧力ノードの判定
	const isPressureNode = (id: string) =>
		id === "__pressure_bullish__" || id === "__pressure_bearish__";
	const pressureNodeColor = (id: string) =>
		id === "__pressure_bullish__" ? "#065f46" : "#7f1d1d";

	// アンカーモード: 流入先ノードの累積流入数を集計
	const inflow: Record<string, number> = {};
	if (props.anchorMode) {
		props.data.edges.forEach((e) => {
			inflow[e.to] = (inflow[e.to] || 0) + (e.edge_count || 1);
		});
	}
	const maxInflow = Math.max(1, ...Object.values(inflow));

	const nodes = new DataSet(
		props.data.nodes.map((n) => {
			if (isPressureNode(n.id)) {
				return {
					id: n.id,
					label: n.label || n.id,
					title: n.label || n.id,
					shape: "diamond",
					color: {
						background: pressureNodeColor(n.id),
						border: "#f3f4f6",
						highlight: {
							background: pressureNodeColor(n.id),
							border: "#fbbf24",
						},
					},
					size: 20,
					borderWidth: 2,
					font: { color: "#f3f4f6", size: 10 },
				};
			}

			const baseSize = 10 + (n.size || 1) * 2;
			const size =
				props.anchorMode && inflow[n.id]
					? baseSize + (inflow[n.id] / maxInflow) * 20
					: baseSize;
			const isHotNode =
				props.anchorMode && inflow[n.id] && inflow[n.id] / maxInflow > 0.5;
			return {
				id: n.id,
				label: n.id,
				title:
					props.anchorMode && inflow[n.id]
						? `${n.id}\n${n.label}\n${n.group}\n流入: ${inflow[n.id]}日`
						: `${n.id}\n${n.label}\n${n.group}`,
				color: {
					background: nodeColor(n.group),
					border: isHotNode ? "#fbbf24" : "#d1d5db",
					highlight: { background: nodeColor(n.group), border: "#f59e0b" },
				},
				size,
				borderWidth: isHotNode ? 3 : 1,
				font: { color: "#1f2937", size: 11 },
			};
		}),
	);

	const maxEdgeCount = Math.max(
		1,
		...props.data.edges.map((e) => e.edge_count || 0),
	);

	const edges = new DataSet(
		props.data.edges.map((e, i) => {
			const hasCount = e.edge_count != null;
			const count = e.edge_count || 0;
			const width =
				props.anchorMode && hasCount
					? 1 + (count / maxEdgeCount) * 12 // アンカー: 最大13px
					: hasCount
						? 1 + count * 2
						: 1 + (e.value || 0) * 3;
			const strength = hasCount ? count / maxEdgeCount : 0;
			const edgeColor =
				props.anchorMode && hasCount
					? strength > 0.6
						? "#f59e0b" // 強: 琥珀
						: strength > 0.3
							? "#6366f1" // 中: 紫
							: "#9ca3af" // 弱: グレー
					: "#9ca3af";
			const title = hasCount
				? `${count}日間のフロー / 平均spread: ${((e.coefficient || 0) * 100).toFixed(2)}%`
				: undefined;
			return {
				id: i,
				from: e.from,
				to: e.to,
				width,
				title,
				color: { color: edgeColor, opacity: props.anchorMode ? 0.9 : 0.8 },
				arrows: props.directed ? e.arrows || "to" : undefined,
				smooth: { enabled: true, type: "curvedCW", roundness: 0.1 },
			};
		}),
	);

	network = new Network(
		container.value,
		{ nodes, edges },
		{
			physics: {
				enabled: true,
				stabilization: { iterations: 100 },
				barnesHut: { gravitationalConstant: -3000, springLength: 100 },
			},
			interaction: { hover: true, tooltipDelay: 200 },
		},
	);

	network.on("click", (params) => {
		if (params.nodes.length > 0) {
			emit("nodeClick", String(params.nodes[0]));
		}
	});
}

onMounted(buildNetwork);

watch([() => props.data, () => props.anchorMode], () => {
	network?.destroy();
	buildNetwork();
});

onBeforeUnmount(() => network?.destroy());
</script>
