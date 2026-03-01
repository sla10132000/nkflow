<template>
  <div class="relative">
    <Line :data="chartData" :options="chartOptions" />
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Line } from 'vue-chartjs'
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
  Filler,
} from 'chart.js'
import type { DailyPrice } from '../../types'

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Title, Tooltip, Legend, Filler)

const props = defineProps<{ prices: DailyPrice[] }>()

const chartData = computed(() => ({
  labels: props.prices.map(p => p.date),
  datasets: [
    {
      label: '終値',
      data: props.prices.map(p => p.close),
      borderColor: '#60a5fa',
      backgroundColor: 'rgba(96,165,250,0.1)',
      borderWidth: 1.5,
      pointRadius: 0,
      fill: true,
      tension: 0.1,
    },
  ],
}))

const chartOptions = {
  responsive: true,
  maintainAspectRatio: false,
  plugins: {
    legend: { display: false },
    tooltip: {
      mode: 'index' as const,
      intersect: false,
      callbacks: {
        label: (ctx: { parsed: { y: number | null } }) =>
          ctx.parsed.y != null ? `¥${ctx.parsed.y.toLocaleString()}` : '',
      },
    },
  },
  scales: {
    x: {
      ticks: { color: '#9ca3af', maxTicksLimit: 8 },
      grid: { color: '#1f2937' },
    },
    y: {
      ticks: { color: '#9ca3af' },
      grid: { color: '#1f2937' },
    },
  },
}
</script>
