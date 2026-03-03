import { createRouter, createWebHashHistory } from 'vue-router'

const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    {
      path: '/',
      component: () => import('../views/OverviewView.vue'),
    },
    {
      path: '/timeseries',
      component: () => import('../views/TimeseriesView.vue'),
    },
    {
      path: '/network',
      component: () => import('../views/NetworkView.vue'),
    },
    {
      path: '/signals',
      component: () => import('../views/SignalsView.vue'),
    },
    {
      path: '/stock/:code',
      component: () => import('../views/StockView.vue'),
      props: true,
    },
    {
      path: '/sector-rotation',
      component: () => import('../views/SectorRotationView.vue'),
    },
    {
      path: '/news',
      component: () => import('../views/NewsView.vue'),
    },
  ],
})

export default router
