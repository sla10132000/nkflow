import { createRouter, createWebHistory } from "vue-router";

const router = createRouter({
	history: createWebHistory(import.meta.env.VITE_ROUTER_BASE || "/"),
	routes: [
		{
			path: "/",
			component: () => import("../views/OverviewView.vue"),
		},
		{
			path: "/timeseries",
			component: () => import("../views/TimeseriesView.vue"),
		},
		{
			path: "/network",
			component: () => import("../views/NetworkView.vue"),
		},
		{
			path: "/stock/:code",
			component: () => import("../views/StockView.vue"),
			props: true,
		},
		{
			path: "/sector-rotation",
			component: () => import("../views/SectorRotationView.vue"),
		},
		{
			path: "/news",
			component: () => import("../views/NewsView.vue"),
		},
		{
			path: "/us-market",
			component: () => import("../views/USMarketView.vue"),
		},
	],
});

export default router;
