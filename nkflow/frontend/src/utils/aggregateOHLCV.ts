import type { DailyPrice } from "../types";

export type Timeframe = "daily" | "weekly" | "monthly";

function isoWeekKey(date: Date): string {
	// ISO 8601 week: Monday-based. Return "YYYY-Www" of Monday of that week.
	const d = new Date(date);
	const day = d.getUTCDay() || 7; // Sunday=7
	d.setUTCDate(d.getUTCDate() + 4 - day); // Thursday of same week
	const yearStart = new Date(Date.UTC(d.getUTCFullYear(), 0, 1));
	const weekNo = Math.ceil(
		((d.getTime() - yearStart.getTime()) / 86400000 + 1) / 7,
	);
	// Return the Monday date of that week as key (first trading day representative)
	const monday = new Date(date);
	const dayOfWeek = monday.getUTCDay() || 7;
	monday.setUTCDate(monday.getUTCDate() - dayOfWeek + 1);
	return monday.toISOString().slice(0, 10);
}

function monthKey(dateStr: string): string {
	// Return first day of month as key
	return `${dateStr.slice(0, 7)}-01`;
}

export function aggregateOHLCV(
	prices: DailyPrice[],
	timeframe: Timeframe,
): DailyPrice[] {
	if (timeframe === "daily") return prices;

	const grouped = new Map<string, DailyPrice[]>();

	for (const p of prices) {
		const d = new Date(`${p.date}T00:00:00Z`);
		const key = timeframe === "weekly" ? isoWeekKey(d) : monthKey(p.date);
		if (!grouped.has(key)) grouped.set(key, []);
		grouped.get(key)?.push(p);
	}

	const result: DailyPrice[] = [];

	for (const [key, bars] of grouped) {
		// bars は昇順 (API が昇順で返す前提)
		const first = bars[0];
		const last = bars[bars.length - 1];
		result.push({
			code: first.code,
			date: key,
			open: first.open,
			high: Math.max(...bars.map((b) => b.high)),
			low: Math.min(...bars.map((b) => b.low)),
			close: last.close,
			volume: bars.reduce((s, b) => s + b.volume, 0),
			return_rate: last.return_rate,
			price_range:
				Math.max(...bars.map((b) => b.high)) -
				Math.min(...bars.map((b) => b.low)),
		});
	}

	// Map は挿入順を保持するが、念のためソート
	result.sort((a, b) => a.date.localeCompare(b.date));
	return result;
}
