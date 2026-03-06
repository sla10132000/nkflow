import { computed, ref } from "vue";

const STORAGE_KEY = "nkflow:news-favorites";

function loadFromStorage(): Set<string> {
	try {
		const raw = localStorage.getItem(STORAGE_KEY);
		if (raw) return new Set(JSON.parse(raw) as string[]);
	} catch {
		// ignore
	}
	return new Set();
}

function saveToStorage(ids: Set<string>) {
	localStorage.setItem(STORAGE_KEY, JSON.stringify([...ids]));
}

const favorites = ref<Set<string>>(loadFromStorage());

export function useFavorites() {
	const favoritesCount = computed(() => favorites.value.size);

	function isFavorite(id: string): boolean {
		return favorites.value.has(id);
	}

	function toggleFavorite(id: string) {
		const next = new Set(favorites.value);
		if (next.has(id)) {
			next.delete(id);
		} else {
			next.add(id);
		}
		favorites.value = next;
		saveToStorage(next);
	}

	return { favorites, favoritesCount, isFavorite, toggleFavorite };
}
