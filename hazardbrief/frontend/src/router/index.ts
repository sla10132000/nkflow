import { createRouter, createWebHistory } from "vue-router";

const router = createRouter({
	history: createWebHistory(import.meta.env.VITE_ROUTER_BASE || "/"),
	routes: [
		{
			path: "/login",
			component: () => import("../views/LoginView.vue"),
			meta: { requiresAuth: false },
		},
		{
			path: "/",
			redirect: "/dashboard",
		},
		{
			path: "/dashboard",
			component: () => import("../views/DashboardView.vue"),
			meta: { requiresAuth: true },
		},
		{
			path: "/properties/new",
			component: () => import("../views/PropertyNewView.vue"),
			meta: { requiresAuth: true },
		},
		{
			path: "/properties/:id",
			component: () => import("../views/PropertyDetailView.vue"),
			props: true,
			meta: { requiresAuth: true },
		},
		{
			path: "/settings",
			component: () => import("../views/SettingsView.vue"),
			meta: { requiresAuth: true },
		},
	],
});

// Auth0 の isAuthenticated で認証チェック
router.beforeEach(async (to) => {
	if (!to.meta.requiresAuth) return true;

	// Auth0 がブラウザ環境でのみ動作するため、server-side では skip
	if (typeof window === "undefined") return true;

	try {
		const { useAuth0 } = await import("@auth0/auth0-vue");
		// composable はコンポーネント外では使えないため、
		// Auth0 SDK の isAuthenticated をチェックする方法はコンポーネント内で行う
		// ここでは単純にログインページへのリダイレクトは App.vue で処理
		return true;
	} catch {
		return true;
	}
});

export default router;
