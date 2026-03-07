import { describe, expect, it } from "vitest";
import type { DailyPrice } from "../types";
import { aggregateOHLCV } from "./aggregateOHLCV";

function makePrice(
	date: string,
	open: number,
	high: number,
	low: number,
	close: number,
	volume = 1000,
): DailyPrice {
	return {
		code: "7203",
		date,
		open,
		high,
		low,
		close,
		volume,
		return_rate: 0,
		price_range: high - low,
	};
}

describe("aggregateOHLCV", () => {
	it("daily: 入力をそのまま返す", () => {
		const prices = [makePrice("2026-03-02", 100, 110, 90, 105)];
		expect(aggregateOHLCV(prices, "daily")).toEqual(prices);
	});

	it("空配列を返す", () => {
		expect(aggregateOHLCV([], "weekly")).toEqual([]);
		expect(aggregateOHLCV([], "monthly")).toEqual([]);
	});

	describe("weekly", () => {
		it("同じ週の日足を1本に集約する", () => {
			// 2026-03-02 (月) ~ 2026-03-06 (金)
			const prices = [
				makePrice("2026-03-02", 100, 115, 95, 108, 1000),
				makePrice("2026-03-03", 108, 120, 105, 112, 2000),
				makePrice("2026-03-04", 112, 125, 110, 110, 1500),
				makePrice("2026-03-05", 110, 118, 108, 115, 1200),
				makePrice("2026-03-06", 115, 122, 112, 120, 1800),
			];
			const result = aggregateOHLCV(prices, "weekly");
			expect(result).toHaveLength(1);
			const bar = result[0];
			expect(bar.open).toBe(100); // 最初の日の open
			expect(bar.close).toBe(120); // 最後の日の close
			expect(bar.high).toBe(125); // 全日の最高値
			expect(bar.low).toBe(95); // 全日の最安値
			expect(bar.volume).toBe(7500); // 合計出来高
		});

		it("異なる週の日足を別々に集約する", () => {
			const prices = [
				makePrice("2026-03-02", 100, 110, 90, 105), // 月曜
				makePrice("2026-03-09", 105, 115, 100, 110), // 翌月曜
			];
			const result = aggregateOHLCV(prices, "weekly");
			expect(result).toHaveLength(2);
			expect(result[0].date < result[1].date).toBe(true); // 昇順
		});

		it("週足のキーは月曜日の日付", () => {
			const prices = [
				makePrice("2026-03-04", 100, 110, 90, 105), // 水曜
			];
			const result = aggregateOHLCV(prices, "weekly");
			expect(result[0].date).toBe("2026-03-02"); // その週の月曜
		});
	});

	describe("monthly", () => {
		it("同じ月の日足を1本に集約する", () => {
			const prices = [
				makePrice("2026-03-01", 100, 115, 90, 108, 1000),
				makePrice("2026-03-15", 108, 125, 105, 112, 2000),
				makePrice("2026-03-31", 112, 120, 100, 118, 1500),
			];
			const result = aggregateOHLCV(prices, "monthly");
			expect(result).toHaveLength(1);
			const bar = result[0];
			expect(bar.open).toBe(100);
			expect(bar.close).toBe(118);
			expect(bar.high).toBe(125);
			expect(bar.low).toBe(90);
			expect(bar.volume).toBe(4500);
		});

		it("月足のキーは月の1日", () => {
			const prices = [makePrice("2026-03-15", 100, 110, 90, 105)];
			const result = aggregateOHLCV(prices, "monthly");
			expect(result[0].date).toBe("2026-03-01");
		});

		it("異なる月の日足を別々に集約する", () => {
			const prices = [
				makePrice("2026-02-28", 100, 110, 90, 105),
				makePrice("2026-03-01", 105, 115, 100, 110),
			];
			const result = aggregateOHLCV(prices, "monthly");
			expect(result).toHaveLength(2);
			expect(result[0].date).toBe("2026-02-01");
			expect(result[1].date).toBe("2026-03-01");
		});

		it("結果を昇順にソートする", () => {
			const prices = [
				makePrice("2026-01-15", 100, 110, 90, 105),
				makePrice("2026-03-15", 105, 115, 100, 110),
				makePrice("2026-02-15", 110, 120, 105, 115),
			];
			const result = aggregateOHLCV(prices, "monthly");
			expect(result).toHaveLength(3);
			expect(result[0].date).toBe("2026-01-01");
			expect(result[1].date).toBe("2026-02-01");
			expect(result[2].date).toBe("2026-03-01");
		});
	});
});
