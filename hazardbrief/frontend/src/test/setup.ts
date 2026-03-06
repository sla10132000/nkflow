/**
 * Vitest テストセットアップ
 */

// Leaflet の canvas 関連 API をモック
HTMLCanvasElement.prototype.getContext = () => null;

// ResizeObserver モック
global.ResizeObserver = class ResizeObserver {
	observe() {}
	unobserve() {}
	disconnect() {}
};

// matchMedia モック
Object.defineProperty(window, "matchMedia", {
	writable: true,
	value: (query: string) => ({
		matches: false,
		media: query,
		onchange: null,
		addListener: () => {},
		removeListener: () => {},
		addEventListener: () => {},
		removeEventListener: () => {},
		dispatchEvent: () => false,
	}),
});
