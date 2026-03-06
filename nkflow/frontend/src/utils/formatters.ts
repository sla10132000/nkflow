/**
 * 共通フォーマッタ — 数値・日付・リターン率
 *
 * 各 View で重複していた formatReturn / fmtNum / formatChangePct 等を統合。
 */

/** リターン率 (小数) → ±X.XX% */
export function formatReturn(r: number | null | undefined): string {
  if (r == null) return "—";
  return `${r >= 0 ? "+" : ""}${(r * 100).toFixed(2)}%`;
}

/** 変化率 (%) → ±X.XX%  (既にパーセント値のもの) */
export function formatChangePct(v: number | null | undefined): string {
  if (v == null) return "—";
  return `${v >= 0 ? "+" : ""}${v.toFixed(2)}%`;
}

/** 変化率 (小数) → ±X.XX%  (小数をパーセントに変換) */
export function formatChangeRate(v: number | null | undefined): string {
  if (v == null) return "—";
  const pct = v * 100;
  return `${pct >= 0 ? "+" : ""}${pct.toFixed(2)}%`;
}

/** 数値 → 固定小数点 */
export function fmtNum(v: number | null | undefined, decimals = 2): string {
  if (v == null) return "—";
  return v.toFixed(decimals);
}

/** 日時文字列 → MM/DD HH:mm (JST) */
export function formatDateTime(dt: string): string {
  if (!dt) return "";
  try {
    return new Date(dt).toLocaleString("ja-JP", {
      timeZone: "Asia/Tokyo",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return "";
  }
}

/** 日時文字列 → YYYY/MM/DD HH:mm (JST) */
export function formatDateFull(dt: string): string {
  if (!dt) return "";
  try {
    return new Date(dt).toLocaleString("ja-JP", {
      timeZone: "Asia/Tokyo",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return "";
  }
}

/** 終値フォーマット (VIX は小数2桁、その他はカンマ区切り) */
export function formatClose(
  v: number | null,
  ticker?: string,
): string {
  if (v == null) return "—";
  if (ticker === "^VIX") return v.toFixed(2);
  return v.toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}
