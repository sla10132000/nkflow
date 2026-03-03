import { createRouter, createWebHashHistory } from 'vue-router'
import { authGuard } from '@auth0/auth0-vue'

const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    {
      path: '/callback',
      component: () => import('../views/AuthCallbackView.vue'),
    },
    {
      path: '/',
      component: () => import('../views/OverviewView.vue'),
      beforeEnter: authGuard,
    },
    {
      path: '/timeseries',
      component: () => import('../views/TimeseriesView.vue'),
      beforeEnter: authGuard,
    },
    {
      path: '/network',
      component: () => import('../views/NetworkView.vue'),
      beforeEnter: authGuard,
    },
    {
      path: '/signals',
      component: () => import('../views/SignalsView.vue'),
      beforeEnter: authGuard,
    },
    {
      path: '/stock/:code',
      component: () => import('../views/StockView.vue'),
      props: true,
      beforeEnter: authGuard,
    },
    {
      path: '/sector-rotation',
      component: () => import('../views/SectorRotationView.vue'),
      beforeEnter: authGuard,
    },
  ],
})

export default router
