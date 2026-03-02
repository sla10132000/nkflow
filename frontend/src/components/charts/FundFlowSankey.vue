<template>
  <div>
    <div v-if="!layout.paths.length"
         class="flex items-center justify-center h-32 text-gray-500 text-sm">
      データなし（期間を広げると表示されます）
    </div>
    <svg v-else :viewBox="`0 0 ${W} ${H}`" class="w-full" :style="`max-height: ${H}px`">
      <!-- Bezier paths (drawn first, behind nodes) -->
      <path
        v-for="(p, i) in layout.paths"
        :key="i"
        :d="p.d"
        :fill="p.color"
        opacity="0.38"
        class="transition-opacity duration-150 hover:opacity-65"
        style="cursor:default"
      >
        <title>{{ p.from }} → {{ p.to }}: {{ p.val }}{{ valUnit }}</title>
      </path>

      <!-- Source node bars (left) -->
      <g v-for="n in layout.srcNodes" :key="'s'+n.name">
        <rect
          :x="LEFT_X" :y="n.top" :width="NODE_W" :height="Math.max(3, n.h)"
          :fill="color(n.name)" rx="2"
        />
        <text
          :x="LEFT_X - 5" :y="n.top + n.h / 2 + 4"
          fill="#9ca3af" font-size="10" text-anchor="end"
        >{{ short(n.name) }}</text>
      </g>

      <!-- Destination node bars (right) -->
      <g v-for="n in layout.dstNodes" :key="'d'+n.name">
        <rect
          :x="RIGHT_X" :y="n.top" :width="NODE_W" :height="Math.max(3, n.h)"
          :fill="color(n.name)" rx="2"
        />
        <!-- Sector label -->
        <text
          :x="RIGHT_X + NODE_W + 5" :y="n.top + n.h / 2 + 4"
          fill="#e5e7eb" font-size="11" font-weight="600" text-anchor="start"
        >{{ short(n.name) }}</text>
        <!-- Count badge -->
        <text
          :x="RIGHT_X + NODE_W + 5" :y="n.top + n.h / 2 + 16"
          fill="#6b7280" font-size="9" text-anchor="start"
        >{{ n.total }}{{ valUnit }}</text>
      </g>

      <!-- Column labels -->
      <text :x="LEFT_X + NODE_W / 2" :y="H - 2"
            fill="#4b5563" font-size="9" text-anchor="middle">流出元</text>
      <text :x="RIGHT_X + NODE_W / 2" :y="H - 2"
            fill="#4b5563" font-size="9" text-anchor="middle">流入先</text>
    </svg>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { NetworkData } from '../../types'

const props = defineProps<{
  edges: NetworkData['edges']
}>()

// ── SVG定数 ──────────────────────────────────────────────────────────────────
const W = 600
const H = 270
const NODE_W = 10
const LEFT_X = 110   // left node bar x
const RIGHT_X = 480  // right node bar x
const PAD = 15
const GAP = 5

// ── セクターカラー ────────────────────────────────────────────────────────────
const COLORS: Record<string, string> = {
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

const color = (name: string) => COLORS[name] ?? '#60a5fa'
const short = (s: string) => s.length > 7 ? s.slice(0, 6) + '…' : s

// ── 指標の決定 (edge_count があれば回数、なければ絶対値) ─────────────────────
const valUnit = computed(() =>
  props.edges.some(e => e.edge_count != null) ? '回' : ''
)

const layout = computed(() => {
  const raw = props.edges
    .map(e => ({
      from: e.from,
      to: e.to,
      val: e.edge_count != null ? (e.edge_count || 0) : Math.abs(e.value || 0),
    }))
    .filter(e => e.val > 0)

  if (!raw.length) return { srcNodes: [], dstNodes: [], paths: [] }

  // 合計値
  const srcTot: Record<string, number> = {}
  const dstTot: Record<string, number> = {}
  raw.forEach(e => {
    srcTot[e.from] = (srcTot[e.from] || 0) + e.val
    dstTot[e.to]   = (dstTot[e.to]   || 0) + e.val
  })
  const total = Object.values(srcTot).reduce((a, b) => a + b, 0)
  if (total === 0) return { srcNodes: [], dstNodes: [], paths: [] }

  const usableH = H - 2 * PAD
  const cx = (LEFT_X + NODE_W + RIGHT_X) / 2

  // ノード位置計算
  function placeNodes(entries: [string, number][]) {
    const gapSum = GAP * (entries.length - 1)
    const flowH = usableH - gapSum
    let y = PAD
    const pos: Record<string, { top: number; h: number; cur: number; total: number }> = {}
    entries.forEach(([name, tot]) => {
      const h = Math.max(4, (tot / total) * flowH)
      pos[name] = { top: y, h, cur: y, total: tot }
      y += h + GAP
    })
    return pos
  }

  const sortedSrc = Object.entries(srcTot).sort((a, b) => b[1] - a[1])
  const sortedDst = Object.entries(dstTot).sort((a, b) => b[1] - a[1])
  const srcPos = placeNodes(sortedSrc)
  const dstPos = placeNodes(sortedDst)

  // Bezier paths (大きい順に描画して目立たせる)
  const sortedRaw = [...raw].sort((a, b) => b.val - a.val)
  const gapSrc = GAP * (sortedSrc.length - 1)
  const flowH = usableH - gapSrc

  const paths = sortedRaw.flatMap(e => {
    const sp = srcPos[e.from]
    const dp = dstPos[e.to]
    if (!sp || !dp) return []
    const bh = Math.max(1, (e.val / total) * flowH)
    const sy1 = sp.cur, sy2 = sp.cur + bh
    sp.cur += bh
    const dy1 = dp.cur, dy2 = dp.cur + bh
    dp.cur += bh
    return [{
      d: `M ${LEFT_X + NODE_W} ${sy1} C ${cx} ${sy1},${cx} ${dy1},${RIGHT_X} ${dy1}`
       + ` L ${RIGHT_X} ${dy2} C ${cx} ${dy2},${cx} ${sy2},${LEFT_X + NODE_W} ${sy2} Z`,
      color: color(e.from),
      from: e.from, to: e.to, val: e.val,
    }]
  })

  return {
    srcNodes: sortedSrc.map(([name]) => ({ name, ...srcPos[name] })),
    dstNodes: sortedDst.map(([name]) => ({ name, ...dstPos[name] })),
    paths,
  }
})
</script>
