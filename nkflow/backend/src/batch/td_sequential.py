"""
TD Sequential (Tom DeMark Sequential) 計算モジュール (Phase 22)

アルゴリズム:
  セットアップフェーズ:
    - 強気セットアップ: close[i] < close[i-4] が連続 → 9本でセットアップ完成
    - 弱気セットアップ: close[i] > close[i-4] が連続 → 9本でセットアップ完成
    - 条件が崩れるとカウントリセット

  カウントダウンフェーズ (セットアップ9完成後、連続不要):
    - 強気カウントダウン: close[i] <= low[i-2]  → 13本でカウントダウン完成
    - 弱気カウントダウン: close[i] >= high[i-2] → 13本でカウントダウン完成
    - 反対方向のセットアップ完成でキャンセル
"""
import logging
import sqlite3
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

SETUP_COUNT = 9
COUNTDOWN_COUNT = 13
MIN_LOOKBACK = 4        # close[i-4] を参照するため
COUNTDOWN_LOOKBACK = 2  # low/high[i-2] を参照するため


def _compute_td_for_stock(df: pd.DataFrame) -> pd.DataFrame:
    """
    1銘柄分の price DataFrame から TD Sequential を計算して返す。

    Args:
        df: columns=['date','open','high','low','close'] — date 昇順ソート済み

    Returns:
        columns=['date','setup_bull','setup_bear','countdown_bull','countdown_bear']
    """
    n = len(df)
    if n == 0:
        return df[["date"]].assign(
            setup_bull=[], setup_bear=[], countdown_bull=[], countdown_bear=[]
        )

    closes = df["close"].to_numpy()
    highs  = df["high"].to_numpy()
    lows   = df["low"].to_numpy()

    setup_bull     = [0] * n
    setup_bear     = [0] * n
    countdown_bull = [0] * n
    countdown_bear = [0] * n

    bull_setup_count = 0
    bear_setup_count = 0
    bull_cd_active   = False
    bear_cd_active   = False
    bull_cd_count    = 0
    bear_cd_count    = 0

    for i in range(n):
        # ── セットアップフェーズ ──────────────────────────────────
        if i >= MIN_LOOKBACK:
            if closes[i] < closes[i - MIN_LOOKBACK]:
                bull_setup_count += 1
                bear_setup_count = 0
            elif closes[i] > closes[i - MIN_LOOKBACK]:
                bear_setup_count += 1
                bull_setup_count = 0
            else:
                bull_setup_count = 0
                bear_setup_count = 0

        # セットアップ表示: 1-9 の間だけ表示、9 超過後は 0 (完成済み)
        setup_bull[i] = bull_setup_count if 1 <= bull_setup_count <= SETUP_COUNT else 0
        setup_bear[i] = bear_setup_count if 1 <= bear_setup_count <= SETUP_COUNT else 0

        # ── カウントダウン開始 / キャンセル ─────────────────────
        # == SETUP_COUNT は一度しか成立しない (カウントは増え続けるため)
        if bull_setup_count == SETUP_COUNT:
            bull_cd_active = True
            bull_cd_count  = 0
            bear_cd_active = False
            bear_cd_count  = 0

        if bear_setup_count == SETUP_COUNT:
            bear_cd_active = True
            bear_cd_count  = 0
            bull_cd_active = False
            bull_cd_count  = 0

        # ── カウントダウンフェーズ ────────────────────────────────
        if i >= COUNTDOWN_LOOKBACK:
            if bull_cd_active and bull_cd_count < COUNTDOWN_COUNT:
                if closes[i] <= lows[i - COUNTDOWN_LOOKBACK]:
                    bull_cd_count += 1

            if bear_cd_active and bear_cd_count < COUNTDOWN_COUNT:
                if closes[i] >= highs[i - COUNTDOWN_LOOKBACK]:
                    bear_cd_count += 1

        countdown_bull[i] = bull_cd_count if bull_cd_active else 0
        countdown_bear[i] = bear_cd_count if bear_cd_active else 0

        # ── カウントダウン完成 → 非アクティブ化 ─────────────────
        # (13 を記録した次のバーから 0 になる)
        if bull_cd_active and bull_cd_count >= COUNTDOWN_COUNT:
            bull_cd_active = False
        if bear_cd_active and bear_cd_count >= COUNTDOWN_COUNT:
            bear_cd_active = False

    result = df[["date"]].copy()
    result["setup_bull"]     = setup_bull
    result["setup_bear"]     = setup_bear
    result["countdown_bull"] = countdown_bull
    result["countdown_bear"] = countdown_bear
    return result


def compute_td_sequential(db_path: str, target_date: Optional[str] = None) -> int:
    """
    指定日の全銘柄の TD Sequential を計算して td_sequential テーブルに UPSERT する。

    target_date を指定した場合でも、ステートマシンの性質上、
    各銘柄の全履歴を読み込んで計算し、target_date の行だけ UPSERT する。

    Args:
        db_path: SQLite ファイルパス
        target_date: 'YYYY-MM-DD'。None の場合は today
    Returns:
        UPSERT した行数
    """
    from datetime import date
    if target_date is None:
        target_date = date.today().isoformat()

    conn = sqlite3.connect(db_path)
    try:
        codes = conn.execute(
            "SELECT DISTINCT code FROM daily_prices WHERE date = ?",
            (target_date,),
        ).fetchall()
        codes = [r[0] for r in codes]

        if not codes:
            logger.info(f"TD Sequential: {target_date} に価格データなし")
            return 0

        rows_to_insert = []
        for code in codes:
            price_rows = conn.execute(
                """
                SELECT date, open, high, low, close
                FROM daily_prices
                WHERE code = ? AND close IS NOT NULL
                ORDER BY date ASC
                """,
                (code,),
            ).fetchall()

            if len(price_rows) < MIN_LOOKBACK + 1:
                continue

            df = pd.DataFrame(price_rows, columns=["date", "open", "high", "low", "close"])
            result = _compute_td_for_stock(df)

            row = result[result["date"] == target_date]
            if row.empty:
                continue

            r = row.iloc[0]
            rows_to_insert.append((
                code,
                r["date"],
                int(r["setup_bull"]),
                int(r["setup_bear"]),
                int(r["countdown_bull"]),
                int(r["countdown_bear"]),
            ))

        if rows_to_insert:
            conn.executemany(
                """
                INSERT INTO td_sequential
                    (code, date, setup_bull, setup_bear, countdown_bull, countdown_bear)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(code, date) DO UPDATE SET
                    setup_bull     = excluded.setup_bull,
                    setup_bear     = excluded.setup_bear,
                    countdown_bull = excluded.countdown_bull,
                    countdown_bear = excluded.countdown_bear
                """,
                rows_to_insert,
            )
            conn.commit()
            logger.info(f"TD Sequential UPSERT: {len(rows_to_insert)} 件 ({target_date})")

    finally:
        conn.close()

    return len(rows_to_insert) if rows_to_insert else 0


def backfill_td_sequential(db_path: str) -> int:
    """
    全銘柄・全日付の TD Sequential を再計算して保存する (初回バックフィル用)。

    Returns:
        UPSERT した総行数
    """
    conn = sqlite3.connect(db_path)
    try:
        codes = conn.execute(
            "SELECT DISTINCT code FROM daily_prices"
        ).fetchall()
        codes = [r[0] for r in codes]

        total_upserted = 0
        for code in codes:
            price_rows = conn.execute(
                """
                SELECT date, open, high, low, close
                FROM daily_prices
                WHERE code = ? AND close IS NOT NULL
                ORDER BY date ASC
                """,
                (code,),
            ).fetchall()

            if len(price_rows) < MIN_LOOKBACK + 1:
                continue

            df = pd.DataFrame(price_rows, columns=["date", "open", "high", "low", "close"])
            result = _compute_td_for_stock(df)

            rows = [
                (
                    code,
                    row["date"],
                    int(row["setup_bull"]),
                    int(row["setup_bear"]),
                    int(row["countdown_bull"]),
                    int(row["countdown_bear"]),
                )
                for _, row in result.iterrows()
            ]

            conn.executemany(
                """
                INSERT INTO td_sequential
                    (code, date, setup_bull, setup_bear, countdown_bull, countdown_bear)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(code, date) DO UPDATE SET
                    setup_bull     = excluded.setup_bull,
                    setup_bear     = excluded.setup_bear,
                    countdown_bull = excluded.countdown_bull,
                    countdown_bear = excluded.countdown_bear
                """,
                rows,
            )
            conn.commit()
            total_upserted += len(rows)

        logger.info(f"TD Sequential バックフィル完了: {total_upserted} 件")
    finally:
        conn.close()

    return total_upserted
