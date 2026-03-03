<template>
  <div class="relative">
    <Bar :data="chartData" :options="chartOptions" />
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Bar } from 'vue-chartjs'
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  BarElement,
  Tooltip,
} from 'chart.js'

ChartJS.register(CategoryScale, LinearScale, BarElement, Tooltip)

const props = defineProps<{ returns: number[] }>()

const chartData = computed(() => {
  const bins = 20
  const min = -0.1, max = 0.1
  const step = (max - min) / bins
  const counts = new Array(bins).fill(0)
  for (const r of props.returns) {
    const i = Math.min(bins - 1, Math.max(0, Math.floor((r - min) / step)))
    counts[i]++
  }
  const labels = Array.from({ length: bins }, (_, i) =>
    ((min + i * step) * 100).toFixed(1) + '%'
  )
  return {
    labels,
    datasets: [{
      data: counts,
      backgroundColor: labels.map((_, i) => i < bins / 2 ? '#ef4444' : '#22c55e'),
    }],
  }
})

const chartOptions = {
  responsive: true,
  maintainAspectRatio: false,
  plugins: { legend: { display: false } },
  scales: {
    x: { ticks: { color: '#6b7280', maxTicksLimit: 10 }, grid: { display: false } },
    y: { ticks: { color: '#6b7280' }, grid: { color: '#e5e7eb' } },
  },
}
</script>
