import { useAuth0 } from "@auth0/auth0-vue";
import { computed } from "vue";

/**
 * Auth0 認証 composable
 * useAuth0 のラッパー。HazardBrief 固有の拡張を含む。
 */
export function useAuth() {
	const {
		isAuthenticated,
		isLoading,
		user,
		loginWithRedirect,
		logout,
		getAccessTokenSilently,
	} = useAuth0();

	const displayName = computed(() => {
		if (!user.value) return "";
		return user.value.name || user.value.email || "ユーザー";
	});

	const userEmail = computed(() => user.value?.email || "");

	const login = () =>
		loginWithRedirect({
			appState: { targetUrl: window.location.pathname },
		});

	const logoutUser = () =>
		logout({
			logoutParams: {
				returnTo: window.location.origin,
			},
		});

	const getToken = async (): Promise<string | null> => {
		try {
			return await getAccessTokenSilently();
		} catch (e) {
			console.error("トークン取得失敗:", e);
			return null;
		}
	};

	return {
		isAuthenticated,
		isLoading,
		user,
		displayName,
		userEmail,
		login,
		logout: logoutUser,
		getToken,
	};
}
