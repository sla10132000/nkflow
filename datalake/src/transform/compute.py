"""DuckDBを使ってSQLiteのdaily_pricesを計算・更新する"""
import json
import logging
import sqlite3
from datetime import date
from typing import Optional

import pandas as pd

from src.db import duckdb_sqlite

from src.config import CORRELATION_PERIODS, CORRELATION_THRESHOLD

logger = logging.getLogger(__name__)


def compute_returns(db_path: str, target_date: Optional[str] = None) -> int:
    """
    DuckDB で SQLite を ATTACH し、騰落率・値幅・値幅率を計算して書き戻す。

    LAG ウィンドウ関数で前日終値を参照し、以下を算出する:
      - return_rate  : (close - prev_close) / prev_close
      - price_range  : high - low
      - range_pct    : (high - low) / open

    Args:
        db_path: SQLite ファイルパス
        target_date: 'YYYY-MM-DD'。None の場合は全行を再計算
    Returns:
        更新した行数
    """
    date_filter = f"AND date = '{target_date}'" if target_date else ""

    with duckdb_sqlite(db_path) as duck:
        df = duck.execute(
            f"""
            WITH lagged AS (
                SELECT
                    code,
                    date,
                    open,
                    high,
                    low,
                    close,
                    LAG(close) OVER (PARTITION BY code ORDER BY date) AS prev_close
                FROM sq.daily_prices
            )
            SELECT
                code,
                date,
                CASE WHEN prev_close > 0
                     THEN (close - prev_close) / prev_close
                     ELSE NULL END                              AS return_rate,
                (high - low)                                   AS price_range,
                CASE WHEN open > 0
                     THEN (high - low) / open
                     ELSE NULL END                             AS range_pct
            FROM lagged
            WHERE prev_close IS NOT NULL
            {date_filter}
            """
        ).df()

    if df.empty:
        return 0

    conn = sqlite3.connect(db_path)
    try:
        conn.executemany(
            """
            UPDATE daily_prices
            SET return_rate = ?, price_range = ?, range_pct = ?
            WHERE code = ? AND date = ?
            """,
            [
                (row.return_rate, row.price_range, row.range_pct, row.code, row.date)
                for row in df.itertuples(index=False)
            ],
        )
        conn.commit()
    finally:
        conn.close()

    logger.info(f"騰落率・値幅を計算: {len(df)} 件")
    return len(df)


def compute_relative_strength(db_path: str, target_date: str) -> None:
    """
    対日経225相対強度を計算して書き戻す。

    daily_summary に nikkei_return があればそれを使い、
    なければ当日の全銘柄等加重平均リターンで代替する。
    relative_strength = return_rate - nikkei_return

    Args:
        db_path: SQLite ファイルパス
        target_date: 'YYYY-MM-DD'
    """
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            "SELECT nikkei_return FROM daily_summary WHERE date = ?", (target_date,)
        ).fetchone()
        nikkei_return = row[0] if row and row[0] is not None else None

        if nikkei_return is None:
            avg_row = conn.execute(
                """
                SELECT AVG(return_rate) FROM daily_prices
                WHERE date = ? AND return_rate IS NOT NULL
                """,
                (target_date,),
            ).fetchone()
            nikkei_return = float(avg_row[0]) if avg_row and avg_row[0] is not None else 0.0
            logger.info(f"nikkei_return を全銘柄平均で代替: {nikkei_return:.6f}")

        conn.execute(
            """
            UPDATE daily_prices
            SET relative_strength = return_rate - ?
            WHERE date = ? AND return_rate IS NOT NULL
            """,
            (nikkei_return, target_date),
        )
        conn.commit()
    finally:
        conn.close()

    logger.info(f"相対強度を計算: {target_date}")


def compute_correlations(db_path: str, calc_date: str) -> int:
    """
    ローリング相関行列を計算して graph_correlations に保存する。

    各期間 (20/60/120 営業日) について calc_date 以前の N 日分の
    return_rate でピアソン相関を計算する。
    - |coefficient| < CORRELATION_THRESHOLD のペアは保存しない
    - stock_a < stock_b に正規化して重複を排除する

    Args:
        db_path: SQLite ファイルパス
        calc_date: 'YYYY-MM-DD' (計算基準日)
    Returns:
        保存したエッジ総数
    """
    max_period = max(CORRELATION_PERIODS)
    with duckdb_sqlite(db_path) as duck:
        df = duck.execute(
            f"""
            SELECT code, date, return_rate
            FROM sq.daily_prices
            WHERE date <= '{calc_date}'
              AND return_rate IS NOT NULL
            ORDER BY date
            """
        ).df()

    if df.empty:
        return 0

    dates = sorted(df["date"].unique())
    if len(dates) < 2:
        logger.warning("相関計算に必要な日数が不足しています")
        return 0

    conn = sqlite3.connect(db_path)
    total_inserted = 0

    try:
        for period in CORRELATION_PERIODS:
            available_days = len(dates)
            if available_days < 2:
                continue

            # 利用可能な日数で窓を切る (上限は period)
            window_dates = dates[-min(period, available_days):]
            df_window = df[df["date"].isin(window_dates)]

            pivot = df_window.pivot(index="date", columns="code", values="return_rate")

            min_periods = max(5, int(len(window_dates) * 0.5))
            corr = pivot.corr(min_periods=min_periods)

            rows_to_insert = []
            codes = list(corr.columns)
            for i in range(len(codes)):
                for j in range(i + 1, len(codes)):
                    coef = corr.iloc[i, j]
                    if pd.isna(coef):
                        continue
                    if abs(coef) < CORRELATION_THRESHOLD:
                        continue
                    stock_a, stock_b = sorted([codes[i], codes[j]])
                    rows_to_insert.append(
                        (stock_a, stock_b, float(coef), f"{period}d", calc_date)
                    )

            if rows_to_insert:
                conn.executemany(
                    """
                    INSERT OR REPLACE INTO graph_correlations
                        (stock_a, stock_b, coefficient, period, calc_date)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    rows_to_insert,
                )
                conn.commit()
                total_inserted += len(rows_to_insert)
                logger.info(
                    f"相関エッジを保存: {len(rows_to_insert)} 件 "
                    f"(period={period}d, window={len(window_dates)}日)"
                )

    finally:
        conn.close()

    return total_inserted


def compute_sector_summary(db_path: str, target_date: str) -> None:
    """
    セクター別の平均騰落率・出来高集計を daily_summary の sector_rotation に保存する。

    Args:
        db_path: SQLite ファイルパス
        target_date: 'YYYY-MM-DD'
    """
    with duckdb_sqlite(db_path) as duck:
        df = duck.execute(
            f"""
            SELECT
                s.sector,
                AVG(dp.return_rate)  AS avg_return,
                SUM(dp.volume)       AS total_volume,
                COUNT(*)             AS stock_count
            FROM sq.daily_prices dp
            JOIN sq.stocks s ON dp.code = s.code
            WHERE dp.date = '{target_date}'
              AND dp.return_rate IS NOT NULL
            GROUP BY s.sector
            ORDER BY avg_return DESC
            """
        ).df()

    if df.empty:
        return

    sector_rotation = json.dumps(
        df.to_dict(orient="records"), ensure_ascii=False
    )

    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            INSERT INTO daily_summary (date, sector_rotation)
            VALUES (?, ?)
            ON CONFLICT(date) DO UPDATE SET sector_rotation = excluded.sector_rotation
            """,
            (target_date, sector_rotation),
        )
        conn.commit()
    finally:
        conn.close()

    logger.info(f"セクターサマリを保存: {target_date}")


def compute_all(db_path: str, target_date: Optional[str] = None) -> None:
    """
    全計算を実行する。

    実行順序:
      1. 騰落率・値幅・値幅率 (compute_returns)
      2. 対日経225相対強度   (compute_relative_strength)
      3. ローリング相関行列  (compute_correlations)
      4. セクター別集計       (compute_sector_summary)

    Args:
        db_path: SQLite ファイルパス
        target_date: 'YYYY-MM-DD'。省略時は今日
    """
    if target_date is None:
        target_date = date.today().isoformat()

    logger.info(f"=== compute_all 開始: {target_date} ===")

    n = compute_returns(db_path, target_date)
    logger.info(f"compute_returns: {n} 件更新")

    compute_relative_strength(db_path, target_date)

    total_corr = compute_correlations(db_path, target_date)
    logger.info(f"compute_correlations: {total_corr} エッジ保存")

    compute_sector_summary(db_path, target_date)

    logger.info("=== compute_all 完了 ===")
