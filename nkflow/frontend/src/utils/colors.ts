/**
 * 共通カラー定数 — セクター色・ゾーン色・状態色・条件別 CSS クラス
 *
 * 各 View / Chart で散在していたカラーマッピングを統合。
 */

// ── セクター色 (FundFlowTimeline, GraphView 等) ──────────────────────

export const SECTOR_COLORS: Record<string, string> = {
  食料品: "#f59e0b",
  "水産・農林業": "#84cc16",
  鉱業: "#6b7280",
  建設業: "#f97316",
  繊維製品: "#ec4899",
  "パルプ・紙": "#a3e635",
  化学: "#38bdf8",
  医薬品: "#34d399",
  ゴム製品: "#fb923c",
  "ガラス・土石製品": "#a78bfa",
  鉄鋼: "#94a3b8",
  非鉄金属: "#fbbf24",
  金属製品: "#e2e8f0",
  機械: "#60a5fa",
  電気機器: "#818cf8",
  輸送用機器: "#c084fc",
  精密機器: "#f0abfc",
  その他製品: "#fdba74",
  "電気・ガス業": "#fde68a",
  陸運業: "#bbf7d0",
  海運業: "#7dd3fc",
  空運業: "#93c5fd",
  "倉庫・運輸関連業": "#6ee7b7",
  "情報・通信業": "#67e8f9",
  卸売業: "#fca5a5",
  小売業: "#fde047",
  銀行業: "#86efac",
  "証券・商品先物取引業": "#fdba74",
  保険業: "#f9a8d4",
  その他金融業: "#d9f99d",
  不動産業: "#fcd34d",
  サービス業: "#a5b4fc",
};

// ── セクターローテーション状態色 (SectorRotationView 等) ────────────────

export const STATE_COLORS = [
  "#3b82f6", // 青
  "#22c55e", // 緑
  "#f59e0b", // 琥珀
  "#ef4444", // 赤
  "#a855f7", // 紫
];

export function stateColor(id: number): string {
  return STATE_COLORS[id % STATE_COLORS.length] ?? "#6b7280";
}

export function stateColorBg(id: number): string {
  return `${stateColor(id)}1a`; // 10% opacity
}

// ── 市場圧力ゾーン背景色 (MarketPressureTimeline) ──────────────────────

export const ZONE_BG_COLORS: Record<string, string> = {
  ceiling: "rgba(220,38,38,0.15)",
  overheat: "rgba(202,138,4,0.12)",
  neutral: "rgba(107,114,128,0.06)",
  weak: "rgba(59,130,246,0.08)",
  selling: "rgba(79,70,229,0.12)",
  bottom: "rgba(16,185,129,0.15)",
};

// ── ニュースカテゴリ色 (NewsView) ─────────────────────────────────────

export const NEWS_CATEGORY_COLORS: Record<string, string> = {
  決算: "bg-purple-100 text-purple-700",
  金融政策: "bg-blue-100 text-blue-700",
  為替: "bg-cyan-100 text-cyan-700",
  米国市場: "bg-indigo-100 text-indigo-700",
  半導体: "bg-orange-100 text-orange-700",
  AI: "bg-pink-100 text-pink-700",
  エネルギー: "bg-amber-100 text-amber-700",
  地政学: "bg-red-100 text-red-700",
};

// ── 条件別 CSS クラス ─────────────────────────────────────────────────

/** リターン率 → text-green / text-red */
export function returnClass(r: number | null | undefined): string {
  if (r == null) return "";
  return r >= 0 ? "text-green-600" : "text-red-600";
}

/** 変化率 (%) → text-green / text-red (+ font-medium) */
export function changePctClass(v: number | null | undefined): string {
  if (v == null) return "text-gray-400";
  if (v > 0) return "text-green-600 font-medium";
  if (v < 0) return "text-red-600 font-medium";
  return "text-gray-500";
}

/** レジーム → text 色 */
export function regimeClass(regime: string | null | undefined): string {
  if (regime === "risk_on") return "text-green-600";
  if (regime === "risk_off") return "text-red-600";
  return "text-amber-600";
}

/** VIX 値 → text 色 */
export function vixClass(value: number): string {
  if (value < 20) return "text-green-600";
  if (value < 30) return "text-amber-500";
  return "text-red-600";
}

/** BTC Fear & Greed 値 → text 色 */
export function fngClass(value: number): string {
  if (value > 60) return "text-green-600";
  if (value > 40) return "text-amber-500";
  return "text-red-600";
}

/** ニュースカテゴリ → badge CSS クラス */
export function newsCategoryColor(cat: string | null): string {
  return NEWS_CATEGORY_COLORS[cat || ""] || "bg-gray-100 text-gray-600";
}
