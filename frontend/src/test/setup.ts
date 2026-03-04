// Canvas mock — chart.js requires getContext('2d')
HTMLCanvasElement.prototype.getContext = (() => {
	const noop = () => {};
	const mockCtx = {
		fillRect: noop,
		clearRect: noop,
		getImageData: () => ({ data: new Array(4) }),
		putImageData: noop,
		createImageData: () => [],
		setTransform: noop,
		drawImage: noop,
		save: noop,
		fillText: noop,
		restore: noop,
		beginPath: noop,
		moveTo: noop,
		lineTo: noop,
		closePath: noop,
		stroke: noop,
		translate: noop,
		scale: noop,
		rotate: noop,
		arc: noop,
		fill: noop,
		measureText: () => ({ width: 0 }),
		transform: noop,
		rect: noop,
		clip: noop,
		createLinearGradient: () => ({ addColorStop: noop }),
		createRadialGradient: () => ({ addColorStop: noop }),
		canvas: { width: 300, height: 150 },
	};
	return () => mockCtx;
})() as unknown as typeof HTMLCanvasElement.prototype.getContext;

// ResizeObserver mock
global.ResizeObserver = class ResizeObserver {
	observe() {}
	unobserve() {}
	disconnect() {}
} as unknown as typeof ResizeObserver;
