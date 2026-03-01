<template>
  <div ref="container" class="w-full h-full rounded" />
</template>

<script setup lang="ts">
import { ref, watch, onMounted, onBeforeUnmount } from 'vue'
import { Network } from 'vis-network'
import { DataSet } from 'vis-data'
import type { NetworkData } from '../../types'

const props = defineProps<{
  data: NetworkData
  directed?: boolean
}>()

const emit = defineEmits<{ nodeClick: [id: string] }>()

const container = ref<HTMLElement>()
let network: Network | null = null

const SECTOR_COLORS: Record<string, string> = {
  '食料品': '#f59e0b', '水産・農林業': '#84cc16', '鉱業': '#6b7280',
  '建設業': '#f97316', '繊維製品': '#ec4899', 'パルプ・紙': '#a3e635',
  '化学': '#38bdf8', '医薬品': '#34d399', 'ゴム製品': '#fb923c',
  'ガラス・土石製品': '#a78bfa', '鉄鋼': '#94a3b8', '非鉄金属': '#fbbf24',
  '金属製品': '#e2e8f0', '機械': '#60a5fa', '電気機器': '#818cf8',
  '輸送用機器': '#c084fc', '精密機器': '#f0abfc', 'その他製品': '#fdba74',
  '電気・ガス業': '#fde68a', '陸運業': '#bbf7d0', '海運業': '#7dd3fc',
  '空運業': '#93c5fd', '倉庫・運輸関連業': '#6ee7b7', '情報・通信業': '#67e8f9',
  '卸売業': '#fca5a5', '小売業': '#fde047', '銀行業': '#86efac',
  '証券・商品先物取引業': '#fdba74', '保険業': '#f9a8d4', 'その他金融業': '#d9f99d',
  '不動産業': '#fcd34d', 'サービス業': '#a5b4fc',
}

function buildNetwork() {
  if (!container.value || !props.data) return

  const nodeColor = (group: string) => SECTOR_COLORS[group] ?? '#60a5fa'

  const nodes = new DataSet(
    props.data.nodes.map(n => ({
      id: n.id,
      label: n.id,
      title: `${n.id}\n${n.label}\n${n.group}`,
      color: { background: nodeColor(n.group), border: '#1f2937' },
      size: 10 + (n.size || 1) * 2,
      font: { color: '#f3f4f6', size: 11 },
    }))
  )

  const edges = new DataSet(
    props.data.edges.map((e, i) => ({
      id: i,
      from: e.from,
      to: e.to,
      width: 1 + (e.value || 0) * 3,
      color: { color: '#374151', opacity: 0.8 },
      arrows: props.directed ? e.arrows || 'to' : undefined,
      smooth: { enabled: true, type: 'curvedCW', roundness: 0.1 },
    }))
  )

  network = new Network(container.value, { nodes, edges }, {
    physics: {
      enabled: true,
      stabilization: { iterations: 100 },
      barnesHut: { gravitationalConstant: -3000, springLength: 100 },
    },
    interaction: { hover: true, tooltipDelay: 200 },
  })

  network.on('click', params => {
    if (params.nodes.length > 0) {
      emit('nodeClick', String(params.nodes[0]))
    }
  })
}

onMounted(buildNetwork)

watch(() => props.data, () => {
  network?.destroy()
  buildNetwork()
})

onBeforeUnmount(() => network?.destroy())
</script>
