"""
シグナル生成モジュール: mega_trend_follow

複数の移動平均アライメント・RSI・相対強度・市場環境から
メガトレンドフォローシグナルを生成する。

実行条件:
  - 120日以上のデータがある銘柄のみ対象
  - SMA20 > SMA60 > SMA120 (bullish) または逆 (bearish)
  - RSI 50-80 (bullish) / RSI 20-50 (bearish)
  - 直近10日の勝ち日数 >= 6 (bullish) / 負け日数 >= 6 (bearish)
  - 相対強度が方向と一致

重複排除:
  - 同一銘柄で過去 DEDUP_DAYS 以内に同じシグナルタイプが存在する場合はスキップ
"""

import json
import logging
import sqlite3

from src.db import duckdb_sqlite
import pandas as pd

logger = logging.getLogger(__name__)

# ── 定数 ───────────────────────────────────────────────────────────
SIGNAL_TYPE = "mega_trend_follow"
MIN_CONFIDENCE = 0.40
DEDUP_DAYS = 5
TREND_CONSISTENCY_MIN = 6
RSI_BULLISH_RANGE = (50.0, 80.0)
RSI_BEARISH_RANGE = (20.0, 50.0)

# スコア重み
W_MA = 0.35
W_TREND = 0.25
W_RS = 0.20
W_ENV = 0.20

# MA スプレッド正規化 (合計6%でスコア1.0)
MA_SPREAD_NORM = 0.06
# 相対強度正規化 (±3%で0〜1)
RS_NORM = 0.03


# ── テクニカル指標計算 (DuckDB) ────────────────────────────────────
_INDICATORS_SQL = """
WITH indicators AS (
    SELECT
        code, date, close, volume, return_rate, relative_strength,
        AVG(close) OVER (
            PARTITION BY code ORDER BY date
            ROWS BETWEEN 19 PRECEDING AND CURRENT ROW
        ) AS sma20,
        AVG(close) OVER (
            PARTITION BY code ORDER BY date
            ROWS BETWEEN 59 PRECEDING AND CURRENT ROW
        ) AS sma60,
        AVG(close) OVER (
            PARTITION BY code ORDER BY date
            ROWS BETWEEN 119 PRECEDING AND CURRENT ROW
        ) AS sma120,
        AVG(CASE WHEN return_rate > 0 THEN return_rate ELSE 0 END) OVER (
            PARTITION BY code ORDER BY date
            ROWS BETWEEN 13 PRECEDING AND CURRENT ROW
        ) AS avg_gain_14,
        AVG(CASE WHEN return_rate < 0 THEN ABS(return_rate) ELSE 0 END) OVER (
            PARTITION BY code ORDER BY date
            ROWS BETWEEN 13 PRECEDING AND CURRENT ROW
        ) AS avg_loss_14,
        COUNT(CASE WHEN return_rate > 0 THEN 1 END) OVER (
            PARTITION BY code ORDER BY date
            ROWS BETWEEN 9 PRECEDING AND CURRENT ROW
        ) AS positive_days_10,
        COUNT(CASE WHEN return_rate < 0 THEN 1 END) OVER (
            PARTITION BY code ORDER BY date
            ROWS BETWEEN 9 PRECEDING AND CURRENT ROW
        ) AS negative_days_10,
        COUNT(*) OVER (
            PARTITION BY code ORDER BY date
            ROWS BETWEEN 119 PRECEDING AND CURRENT ROW
        ) AS data_count_120
    FROM sq.daily_prices
    WHERE date <= $target_date
      AND close IS NOT NULL
      AND return_rate IS NOT NULL
)
SELECT
    i.code,
    s.name,
    s.sector,
    i.close,
    i.return_rate,
    i.relative_strength,
    i.sma20,
    i.sma60,
    i.sma120,
    i.volume AS today_volume,
    i.positive_days_10,
    i.negative_days_10,
    CASE
        WHEN i.avg_loss_14 = 0 THEN 100.0
        ELSE 100.0 - 100.0 / (1.0 + i.avg_gain_14 / i.avg_loss_14)
    END AS rsi14,
    (i.sma20 - i.sma60) / NULLIF(i.sma60, 0) AS ma20_vs_ma60,
    (i.sma60 - i.sma120) / NULLIF(i.sma120, 0) AS ma60_vs_ma120
FROM indicators i
JOIN sq.stocks s ON i.code = s.code
WHERE i.date = $target_date
  AND i.sma120 IS NOT NULL
  AND i.data_count_120 >= 120
"""


def _compute_indicators(db_path: str, target_date: str) -> pd.DataFrame:
    """DuckDB で移動平均・RSI 等のテクニカル指標をオンザフライ計算する。"""
    with duckdb_sqlite(db_path) as duck:
        df = duck.execute(_INDICATORS_SQL, {"target_date": target_date}).df()
    return df


# ── 市場環境コンテキスト ──────────────────────────────────────────
def _load_market_context(db_path: str, target_date: str) -> dict:
    """regime / pl_zone / VIX / 信用過熱フラグを取得する。"""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        # regime
        row = conn.execute(
            "SELECT regime FROM daily_summary WHERE date <= ? ORDER BY date DESC LIMIT 1",
            (target_date,),
        ).fetchone()
        regime = row["regime"] if row else "neutral"

        # market pressure
        mp = conn.execute(
            "SELECT pl_zone, buy_growth_4w, signal_flags "
            "FROM market_pressure_daily WHERE date <= ? ORDER BY date DESC LIMIT 1",
            (target_date,),
        ).fetchone()
        pl_zone = mp["pl_zone"] if mp else "neutral"
        credit_overheating = False
        if mp and mp["signal_flags"]:
            flags = json.loads(mp["signal_flags"])
            credit_overheating = flags.get("credit_overheating", False)

        # VIX
        vix_row = conn.execute(
            "SELECT close FROM us_indices WHERE ticker = '^VIX' "
            "AND date <= ? ORDER BY date DESC LIMIT 1",
            (target_date,),
        ).fetchone()
        vix = vix_row["close"] if vix_row else None
    finally:
        conn.close()

    return {
        "regime": regime,
        "pl_zone": pl_zone,
        "credit_overheating": credit_overheating,
        "vix": vix,
    }


# ── 重複排除 ──────────────────────────────────────────────────────
def _get_recent_signal_codes(db_path: str, target_date: str) -> set[str]:
    """過去 DEDUP_DAYS 以内に mega_trend_follow シグナルが出た銘柄コードを返す。"""
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            """
            SELECT DISTINCT code FROM signals
            WHERE signal_type = ?
              AND date >= date(?, ?)
              AND date < ?
            """,
            (SIGNAL_TYPE, target_date, f"-{DEDUP_DAYS} days", target_date),
        ).fetchall()
    finally:
        conn.close()
    return {r[0] for r in rows if r[0]}


# ── 方向判定 ──────────────────────────────────────────────────────
def _classify_direction(row) -> str | None:
    """bullish / bearish / None を返す。"""
    close = row.close
    sma20 = row.sma20
    sma60 = row.sma60
    sma120 = row.sma120
    rsi = row.rsi14
    rs = row.relative_strength or 0.0

    # bullish: close > sma20 > sma60 > sma120, RSI 50-80, positive trend, RS > 0
    if (
        close > sma20 > sma60 > sma120
        and RSI_BULLISH_RANGE[0] < rsi < RSI_BULLISH_RANGE[1]
        and row.positive_days_10 >= TREND_CONSISTENCY_MIN
        and rs > 0
    ):
        return "bullish"

    # bearish: close < sma20 < sma60 < sma120, RSI 20-50, negative trend, RS < 0
    if (
        close < sma20 < sma60 < sma120
        and RSI_BEARISH_RANGE[0] < rsi < RSI_BEARISH_RANGE[1]
        and row.negative_days_10 >= TREND_CONSISTENCY_MIN
        and rs < 0
    ):
        return "bearish"

    return None


# ── 市場環境スコア ────────────────────────────────────────────────
def _market_env_score(
    direction: str,
    regime: str,
    pl_zone: str,
    vix: float | None,
    credit_overheating: bool,
) -> float:
    """市場環境から 0.0〜1.0 のスコアを算出する。"""
    score = 0.5

    # regime
    if direction == "bullish":
        if regime == "risk_on":
            score += 0.25
        elif regime == "risk_off":
            score -= 0.30
    else:
        if regime == "risk_off":
            score += 0.25
        elif regime == "risk_on":
            score -= 0.30

    # VIX
    if vix is not None:
        if direction == "bullish":
            if vix > 25:
                score -= 0.15
            elif vix < 15:
                score += 0.10
        else:
            if vix > 25:
                score += 0.10
            elif vix < 15:
                score -= 0.10

    # 信用圧力
    if direction == "bullish" and pl_zone in ("ceiling", "overheat"):
        score -= 0.20
    if direction == "bearish" and pl_zone in ("bottom", "sellin"):
        score += 0.10

    # 信用過熱フラグ
    if credit_overheating and direction == "bullish":
        score -= 0.20

    return min(1.0, max(0.0, score))


# ── 信頼度計算 ────────────────────────────────────────────────────
def _compute_confidence(row, direction: str, ctx: dict) -> tuple[float, dict]:
    """信頼度スコアとスコア内訳を返す。"""
    # MA 整列スコア
    ma_spread = abs(row.ma20_vs_ma60 or 0) + abs(row.ma60_vs_ma120 or 0)
    ma_score = min(1.0, ma_spread / MA_SPREAD_NORM)

    # トレンド一貫性スコア
    if direction == "bullish":
        trend_score = max(0.0, min(1.0, (row.positive_days_10 - TREND_CONSISTENCY_MIN) / 4.0))
    else:
        trend_score = max(0.0, min(1.0, (row.negative_days_10 - TREND_CONSISTENCY_MIN) / 4.0))

    # 相対強度スコア
    rs = row.relative_strength or 0.0
    if direction == "bullish":
        rs_score = min(1.0, max(0.0, (rs + RS_NORM) / (2 * RS_NORM)))
    else:
        rs_score = min(1.0, max(0.0, (-rs + RS_NORM) / (2 * RS_NORM)))

    # 市場環境スコア
    env_score = _market_env_score(
        direction,
        ctx["regime"],
        ctx["pl_zone"],
        ctx["vix"],
        ctx["credit_overheating"],
    )

    confidence = W_MA * ma_score + W_TREND * trend_score + W_RS * rs_score + W_ENV * env_score

    breakdown = {
        "ma_alignment": round(ma_score, 3),
        "trend_consistency": round(trend_score, 3),
        "relative_strength": round(rs_score, 3),
        "market_env": round(env_score, 3),
        "final": round(confidence, 3),
    }

    return round(confidence, 4), breakdown


# ── reasoning JSON 生成 ───────────────────────────────────────────
def _build_reasoning(row, direction: str, ctx: dict, breakdown: dict) -> dict:
    return {
        "ma_alignment": {
            "close": round(row.close, 1),
            "sma20": round(row.sma20, 1),
            "sma60": round(row.sma60, 1),
            "sma120": round(row.sma120, 1),
            "ma20_vs_ma60_pct": round((row.ma20_vs_ma60 or 0) * 100, 2),
            "ma60_vs_ma120_pct": round((row.ma60_vs_ma120 or 0) * 100, 2),
        },
        "momentum": {
            "rsi14": round(row.rsi14, 1),
            "positive_days_10": int(row.positive_days_10),
            "negative_days_10": int(row.negative_days_10),
            "relative_strength": round(row.relative_strength or 0, 4),
        },
        "market_context": {
            "regime": ctx["regime"],
            "pl_zone": ctx["pl_zone"],
            "vix": round(ctx["vix"], 1) if ctx["vix"] is not None else None,
            "credit_overheating": ctx["credit_overheating"],
        },
        "score_breakdown": breakdown,
    }


# ── 公開 API ─────────────────────────────────────────────────────
def generate(db_path: str, target_date: str, graph_results: dict) -> int:
    """
    mega_trend_follow シグナルを生成して signals テーブルに保存する。

    Args:
        db_path: SQLite ファイルパス
        target_date: 'YYYY-MM-DD'
        graph_results: graph.update_and_query() の返り値 (将来拡張用)
    Returns:
        生成したシグナル数
    """
    try:
        df = _compute_indicators(db_path, target_date)
    except Exception as e:
        logger.error(f"signals._compute_indicators 失敗: {e}")
        return 0

    if df.empty:
        logger.info(f"signals: 対象銘柄なし ({target_date})")
        return 0

    try:
        ctx = _load_market_context(db_path, target_date)
    except Exception:
        logger.warning("signals._load_market_context 失敗 — デフォルト値を使用")
        ctx = {
            "regime": "neutral",
            "pl_zone": "neutral",
            "credit_overheating": False,
            "vix": None,
        }

    try:
        recent_codes = _get_recent_signal_codes(db_path, target_date)
    except Exception:
        logger.warning("signals._get_recent_signal_codes 失敗 — 重複排除スキップ")
        recent_codes = set()

    rows_to_insert: list[tuple] = []

    for row in df.itertuples(index=False):
        if row.code in recent_codes:
            continue

        direction = _classify_direction(row)
        if direction is None:
            continue

        confidence, breakdown = _compute_confidence(row, direction, ctx)
        if confidence < MIN_CONFIDENCE:
            continue

        reasoning = _build_reasoning(row, direction, ctx, breakdown)
        rows_to_insert.append((
            target_date,
            SIGNAL_TYPE,
            row.code,
            row.sector,
            direction,
            confidence,
            json.dumps(reasoning, ensure_ascii=False),
        ))

    if not rows_to_insert:
        logger.info(f"signals.generate: シグナルなし ({target_date})")
        return 0

    conn = sqlite3.connect(db_path)
    try:
        conn.executemany(
            """
            INSERT INTO signals (date, signal_type, code, sector, direction, confidence, reasoning)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            rows_to_insert,
        )
        conn.commit()
    finally:
        conn.close()

    logger.info(f"signals.generate: {len(rows_to_insert)} 件生成 ({target_date})")
    return len(rows_to_insert)
