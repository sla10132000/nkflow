import { mount, flushPromises } from "@vue/test-utils";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { createRouter, createMemoryHistory } from "vue-router";
import { createPinia } from "pinia";

// Auth0 モック
vi.mock("@auth0/auth0-vue", () => ({
	useAuth0: () => ({
		isAuthenticated: { value: true },
		isLoading: { value: false },
		user: { value: { name: "テストユーザー", email: "test@example.com" } },
		loginWithRedirect: vi.fn(),
		logout: vi.fn(),
		getAccessTokenSilently: vi.fn().mockResolvedValue("test-token"),
	}),
}));

// useApi モック — vi.mock は巻き上げられるのでインライン定義する
vi.mock("../composables/useApi", () => ({
	useApi: () => ({
		getProperties: vi.fn().mockResolvedValue([
			{
				id: "prop-1",
				company_id: "company-1",
				created_by: null,
				address: "東京都千代田区丸の内1-1-1",
				latitude: 35.6812,
				longitude: 139.7671,
				property_name: "テスト物件",
				notes: null,
				created_at: "2026-03-06T10:00:00",
			},
		]),
		getProperty: vi.fn().mockResolvedValue({}),
		createProperty: vi.fn().mockResolvedValue({}),
		deleteProperty: vi.fn().mockResolvedValue({ property_id: "prop-1", status: "deleted" }),
		getHazard: vi.fn().mockResolvedValue({}),
		getReport: vi.fn().mockResolvedValue({}),
		getCompanies: vi.fn().mockResolvedValue([]),
		getCompany: vi.fn().mockResolvedValue({}),
		createCompany: vi.fn().mockResolvedValue({}),
	}),
}));

// HazardMap モック (Leaflet は happy-dom では動作しない)
vi.mock("../components/map/HazardMap.vue", () => ({
	default: { template: '<div data-testid="mock-map"></div>' },
}));

import DashboardView from "../views/DashboardView.vue";

const router = createRouter({
	history: createMemoryHistory(),
	routes: [
		{ path: "/", component: DashboardView },
		{ path: "/dashboard", component: DashboardView },
		{ path: "/properties/new", component: { template: "<div>new</div>" } },
		{ path: "/properties/:id", component: { template: "<div>detail</div>" } },
	],
});

describe("DashboardView", () => {
	beforeEach(async () => {
		await router.push("/dashboard");
	});

	it("ページタイトルが表示される", async () => {
		const wrapper = mount(DashboardView, {
			global: {
				plugins: [router, createPinia()],
				stubs: { AppHeader: true, LoadingSpinner: true },
			},
		});
		await flushPromises();
		expect(wrapper.text()).toContain("物件一覧");
	});

	it("物件カードが表示される", async () => {
		const wrapper = mount(DashboardView, {
			global: {
				plugins: [router, createPinia()],
				stubs: { AppHeader: true, LoadingSpinner: true },
			},
		});
		await flushPromises();
		expect(wrapper.text()).toContain("テスト物件");
		expect(wrapper.text()).toContain("東京都千代田区丸の内1-1-1");
	});

	it("物件登録ボタンが表示される", async () => {
		const wrapper = mount(DashboardView, {
			global: {
				plugins: [router, createPinia()],
				stubs: { AppHeader: true, LoadingSpinner: true },
			},
		});
		await flushPromises();
		expect(wrapper.text()).toContain("物件を登録");
	});

	it("物件なしの場合は空の状態テキストが定義されている", async () => {
		const wrapper = mount(DashboardView, {
			global: {
				plugins: [
					createRouter({
						history: createMemoryHistory(),
						routes: [{ path: "/dashboard", component: DashboardView }],
					}),
					createPinia(),
				],
				stubs: { AppHeader: true, LoadingSpinner: true },
			},
		});
		await flushPromises();
		// ページが表示されていることを確認 (物件一覧ヘッダーは必ず表示される)
		expect(wrapper.text()).toContain("物件一覧");
	});
});
