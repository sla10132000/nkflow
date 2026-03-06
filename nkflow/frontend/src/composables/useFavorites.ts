import { computed, ref } from "vue";
import type { NewsArticle } from "../types";

const STORAGE_KEY = "nkflow:news-favorites";

function loadFromStorage(): Map<string, NewsArticle> {
	try {
		const raw = localStorage.getItem(STORAGE_KEY);
		if (raw) {
			const arr = JSON.parse(raw) as NewsArticle[];
			return new Map(arr.map((a) => [a.id, a]));
		}
	} catch {
		// ignore
	}
	return new Map();
}

function saveToStorage(map: Map<string, NewsArticle>) {
	localStorage.setItem(STORAGE_KEY, JSON.stringify([...map.values()]));
}

const favoritesMap = ref<Map<string, NewsArticle>>(loadFromStorage());

export function useFavorites() {
	const favoritesCount = computed(() => favoritesMap.value.size);
	const favoriteArticles = computed(() => [...favoritesMap.value.values()]);

	function isFavorite(id: string): boolean {
		return favoritesMap.value.has(id);
	}

	function toggleFavorite(article: NewsArticle) {
		const next = new Map(favoritesMap.value);
		if (next.has(article.id)) {
			next.delete(article.id);
		} else {
			next.set(article.id, article);
		}
		favoritesMap.value = next;
		saveToStorage(next);
	}

	return { favoriteArticles, favoritesCount, isFavorite, toggleFavorite };
}
