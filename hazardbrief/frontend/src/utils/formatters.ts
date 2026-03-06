/**
 * 数値・日付フォーマットユーティリティ
 */

/**
 * 日付文字列を日本語形式に変換する
 * "2026-03-06T12:34:56" → "2026年3月6日 12:34"
 */
export function formatDateTime(isoStr: string): string {
	try {
		const d = new Date(isoStr);
		return d.toLocaleString("ja-JP", {
			year: "numeric",
			month: "long",
			day: "numeric",
			hour: "2-digit",
			minute: "2-digit",
		});
	} catch {
		return isoStr;
	}
}

/**
 * 日付文字列を短い形式に変換する
 * "2026-03-06" → "2026/03/06"
 */
export function formatDate(isoStr: string): string {
	try {
		const d = new Date(isoStr);
		return d.toLocaleDateString("ja-JP", {
			year: "numeric",
			month: "2-digit",
			day: "2-digit",
		});
	} catch {
		return isoStr;
	}
}

/**
 * 標高を表示用文字列に変換する
 * 15.3 → "15.3m"
 */
export function formatElevation(elevation: number | null): string {
	if (elevation === null || elevation === undefined) return "不明";
	return `${elevation.toFixed(1)}m`;
}

/**
 * リスクレベルの日本語ラベルを返す
 */
export function formatRiskLevel(level: string): string {
	const labels: Record<string, string> = {
		low: "低",
		medium: "中",
		high: "高",
		unknown: "要確認",
	};
	return labels[level] ?? "要確認";
}

/**
 * リスクレベルの Tailwind CSS クラスを返す
 */
export function getRiskColorClass(level: string): string {
	const classes: Record<string, string> = {
		low: "risk-low",
		medium: "risk-medium",
		high: "risk-high",
		unknown: "risk-unknown",
	};
	return classes[level] ?? "risk-unknown";
}

/**
 * リスクバッジのクラスを返す
 */
export function getRiskBadgeClass(level: string): string {
	const classes: Record<string, string> = {
		low: "risk-badge-low",
		medium: "risk-badge-medium",
		high: "risk-badge-high",
		unknown: "risk-badge-unknown",
	};
	return classes[level] ?? "risk-badge-unknown";
}
