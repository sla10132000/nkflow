/**
 * 共通日付ユーティリティ — 期間計算・営業日判定
 *
 * 各 View で重複していた toDate / lastBusinessDay / fmt 等を統合。
 */

/** Date → YYYY-MM-DD */
export function fmt(d: Date): string {
  return d.toISOString().slice(0, 10);
}

/** N 日前の日付文字列 (YYYY-MM-DD) */
export function toDate(daysAgo: number): string {
  const d = new Date();
  d.setDate(d.getDate() - daysAgo);
  return d.toISOString().split("T")[0];
}

/** JST の今日の日付文字列 (YYYY-MM-DD) */
export function todayJst(): string {
  return new Date().toLocaleDateString("sv-SE", { timeZone: "Asia/Tokyo" });
}

/** JST の N 日前の日付文字列 (YYYY-MM-DD) */
export function daysAgoJst(days: number): string {
  const d = new Date();
  d.setDate(d.getDate() - days);
  return d.toLocaleDateString("sv-SE", { timeZone: "Asia/Tokyo" });
}

/** 直近の営業日 (土日を除外) */
export function lastBusinessDay(from: Date = new Date()): Date {
  const d = new Date(from);
  const dow = d.getDay();
  if (dow === 0) d.setDate(d.getDate() - 2);
  else if (dow === 6) d.setDate(d.getDate() - 1);
  return d;
}

/** 期間文字列 (例: "20d") → date_from / date_to */
export function periodToDateRange(p: string): { from: string; to: string } {
  const days = Number.parseInt(p, 10) * 1.5;
  const to = new Date();
  const from = new Date();
  from.setDate(to.getDate() - Math.ceil(days));
  return { from: fmt(from), to: fmt(to) };
}
