import { defineStore } from "pinia";
import { ref, computed } from "vue";

/**
 * 認証状態ストア
 * Auth0 の状態を Pinia で管理する。
 */
export const useAuthStore = defineStore("auth", () => {
	const companyId = ref<string | null>(null);
	const companyName = ref<string | null>(null);

	const hasCompany = computed(() => companyId.value !== null);

	function setCompany(id: string, name: string) {
		companyId.value = id;
		companyName.value = name;
	}

	function clearCompany() {
		companyId.value = null;
		companyName.value = null;
	}

	return {
		companyId,
		companyName,
		hasCompany,
		setCompany,
		clearCompany,
	};
});
