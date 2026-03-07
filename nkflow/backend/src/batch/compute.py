"""DuckDBを使ってSQLiteのdaily_pricesを計算・更新する"""
import json
import logging
import sqlite3
from datetime import date
from typing import Optional

import pandas as pd

from src.batch.db import duckdb_sqlite

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


def generate_overview_snapshot(db_path: str, target_date: str) -> dict:
    """
    概要ページ用の事前計算スナップショットを生成して SQLite に保存する。

    含まれるデータ:
      - daily_summary       : 最新レコード + 30日履歴
      - news_articles       : 最新 5 件
      - fear_indices        : VIX / BTC Fear & Greed
      - ytd_highs           : 年初来高値圏 銘柄 (上位 10)
      - sector_performance  : 日本・米国 全期間 (1d/1w/1m/3m)
      - nikkei_ohlcv        : ^N225 60日分 (チャート用)

    Args:
        db_path: SQLite ファイルパス
        target_date: 'YYYY-MM-DD' (スナップショット生成日)
    Returns:
        スナップショット dict
    """
    from src.config import US_SECTOR_ETF_TICKERS

    _sector_etf_tickers = tuple(US_SECTOR_ETF_TICKERS.keys())
    _sector_etf_placeholders = ",".join(f"'{t}'" for t in _sector_etf_tickers)
    _period_offset = {"1d": 1, "1w": 5, "1m": 21, "3m": 63}
    sector_map = {k: v["sector"] for k, v in US_SECTOR_ETF_TICKERS.items()}

    def _parse_json(val):
        if not val:
            return []
        try:
            return json.loads(val)
        except Exception:
            return []

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        # 1. daily_summary — 最新 30 日分
        summary_rows = conn.execute(
            """
            SELECT date, nikkei_close, nikkei_return, regime,
                   top_gainers, top_losers, sector_rotation
            FROM daily_summary
            ORDER BY date DESC
            LIMIT 30
            """
        ).fetchall()

        summary_history = [
            {
                "date": r["date"],
                "nikkei_close": r["nikkei_close"],
                "nikkei_return": r["nikkei_return"],
                "regime": r["regime"],
                "top_gainers": _parse_json(r["top_gainers"]),
                "top_losers": _parse_json(r["top_losers"]),
                "sector_rotation": _parse_json(r["sector_rotation"]),
            }
            for r in summary_rows
        ]
        summary = summary_history[0] if summary_history else None

        # 2. ニュース — 最新 5 件
        news_rows = conn.execute(
            """
            SELECT id, title, title_ja, url, source, source_name,
                   published_at, category, sentiment
            FROM news_articles
            ORDER BY published_at DESC
            LIMIT 5
            """
        ).fetchall()
        news = [dict(r) for r in news_rows]

        # 3. 恐怖指数
        vix = None
        try:
            vix_rows = conn.execute(
                """
                SELECT date, close FROM us_indices
                WHERE ticker = '^VIX'
                ORDER BY date DESC LIMIT 2
                """
            ).fetchall()
            if vix_rows:
                latest = dict(vix_rows[0])
                change_pct = None
                if len(vix_rows) >= 2:
                    prev_close = vix_rows[1]["close"]
                    if prev_close:
                        change_pct = round(
                            (latest["close"] - prev_close) / prev_close * 100, 4
                        )
                vix = {
                    "value": round(latest["close"], 2),
                    "change_pct": change_pct,
                    "date": latest["date"],
                }
        except sqlite3.OperationalError:
            pass

        btc_fear_greed = None
        try:
            fng_row = conn.execute(
                """
                SELECT date, value, value_classification
                FROM crypto_fear_greed
                ORDER BY date DESC LIMIT 1
                """
            ).fetchone()
            if fng_row:
                btc_fear_greed = {
                    "value": fng_row["value"],
                    "classification": fng_row["value_classification"],
                    "date": fng_row["date"],
                }
        except sqlite3.OperationalError:
            pass

        # 4. YTD 高値圏銘柄 (年初来 5% 以内)
        ytd_start = f"{target_date[:4]}-01-01"
        ytd_rows = conn.execute(
            """
            WITH latest_date AS (SELECT MAX(date) AS d FROM daily_prices),
            ytd AS (
                SELECT dp.code, MAX(dp.high) AS ytd_high
                FROM daily_prices dp, latest_date
                WHERE dp.date >= ? AND dp.date <= latest_date.d
                  AND dp.high IS NOT NULL
                GROUP BY dp.code
            ),
            latest AS (
                SELECT dp.code, dp.close
                FROM daily_prices dp
                JOIN latest_date ON dp.date = latest_date.d
                WHERE dp.close IS NOT NULL
            )
            SELECT l.code, s.name, s.sector, l.close, y.ytd_high,
                   (l.close - y.ytd_high) / y.ytd_high * 100.0 AS gap_pct
            FROM latest l
            JOIN ytd y ON y.code = l.code
            JOIN stocks s ON s.code = l.code
            WHERE (l.close - y.ytd_high) / y.ytd_high * 100.0 >= -5.0
            ORDER BY gap_pct DESC
            LIMIT 10
            """,
            (ytd_start,),
        ).fetchall()
        ytd_highs = [dict(r) for r in ytd_rows]

        # 5. 日本セクターパフォーマンス (全期間)
        def _jp_sector(period: str):
            try:
                if period == "1d":
                    rows = conn.execute(
                        """
                        SELECT sector, return_rate FROM sector_daily_returns
                        WHERE date = (SELECT MAX(date) FROM sector_daily_returns)
                        ORDER BY sector
                        """
                    ).fetchall()
                elif period == "1w":
                    rows = conn.execute(
                        """
                        SELECT sector, return_rate FROM sector_weekly_returns
                        WHERE week_date = (SELECT MAX(week_date) FROM sector_weekly_returns)
                        ORDER BY sector
                        """
                    ).fetchall()
                elif period == "1m":
                    rows = conn.execute(
                        """
                        SELECT sector, return_rate FROM sector_monthly_returns
                        WHERE month_date = (SELECT MAX(month_date) FROM sector_monthly_returns)
                        ORDER BY sector
                        """
                    ).fetchall()
                elif period == "3m":
                    rows = conn.execute(
                        """
                        SELECT sector, SUM(return_rate) AS return_rate
                        FROM sector_monthly_returns
                        WHERE month_date IN (
                            SELECT DISTINCT month_date FROM sector_monthly_returns
                            ORDER BY month_date DESC LIMIT 3
                        )
                        GROUP BY sector ORDER BY sector
                        """
                    ).fetchall()
                else:
                    return []
                return [{"sector": r[0], "avg_return": r[1] or 0} for r in rows]
            except Exception:
                return []

        # 6. 米国セクターパフォーマンス (全期間)
        def _us_sector(period: str):
            offset = _period_offset.get(period, 1)
            try:
                rows = conn.execute(
                    f"""
                    WITH latest_date AS (
                        SELECT MAX(date) AS max_date FROM us_indices
                        WHERE ticker IN ({_sector_etf_placeholders})
                    ),
                    base AS (
                        SELECT ticker, close AS base_close FROM us_indices
                        WHERE ticker IN ({_sector_etf_placeholders})
                          AND date = (
                              SELECT MAX(date) FROM us_indices
                              WHERE ticker IN ({_sector_etf_placeholders})
                                AND date < (
                                    SELECT DATE(max_date, ? || ' days')
                                    FROM latest_date
                                )
                          )
                    )
                    SELECT t.ticker, t.name, t.close, t.volume,
                           ROUND((t.close - b.base_close) / b.base_close * 100, 2) AS change_pct
                    FROM us_indices t
                    JOIN latest_date ld ON t.date = ld.max_date
                    JOIN base b ON b.ticker = t.ticker
                    WHERE t.ticker IN ({_sector_etf_placeholders})
                    ORDER BY change_pct DESC
                    """,
                    (f"-{offset}",),
                ).fetchall()

                if not rows:
                    return {"date": None, "period": period, "sectors": []}

                latest_date = conn.execute(
                    f"SELECT MAX(date) FROM us_indices WHERE ticker IN ({_sector_etf_placeholders})"
                ).fetchone()[0]

                return {
                    "date": latest_date,
                    "period": period,
                    "sectors": [
                        {
                            "ticker": r[0],
                            "name": r[1],
                            "sector": sector_map.get(r[0], r[0]),
                            "close": r[2],
                            "change_pct": r[4],
                            "volume": r[3],
                        }
                        for r in rows
                    ],
                }
            except Exception:
                return {"date": None, "period": period, "sectors": []}

        # 7. 日経平均 OHLCV (^N225, 60日) — チャート用
        nikkei_ohlcv: list = []
        try:
            n225_rows = conn.execute(
                """
                SELECT date, open, high, low, close, volume FROM us_indices
                WHERE ticker = '^N225'
                ORDER BY date DESC LIMIT 60
                """
            ).fetchall()
            nikkei_ohlcv = [dict(r) for r in reversed(n225_rows)]
        except sqlite3.OperationalError:
            pass

        snapshot = {
            "generated_at": target_date,
            "date": summary["date"] if summary else target_date,
            "summary": summary,
            "summary_history": list(reversed(summary_history)),  # oldest first
            "news": news,
            "fear_indices": {"vix": vix, "btc_fear_greed": btc_fear_greed},
            "ytd_highs": ytd_highs,
            "sector_performance": {
                "jp": {p: _jp_sector(p) for p in ["1d", "1w", "1m", "3m"]},
                "us": {p: _us_sector(p) for p in ["1d", "1w", "1m", "3m"]},
            },
            "nikkei_ohlcv": nikkei_ohlcv,
        }

    finally:
        conn.close()

    # SQLite に保存 (別接続で書き込み)
    snapshot_json = json.dumps(snapshot, ensure_ascii=False, default=str)
    write_conn = sqlite3.connect(db_path)
    try:
        write_conn.execute(
            """
            INSERT INTO overview_snapshot (date, snapshot_json)
            VALUES (?, ?)
            ON CONFLICT(date) DO UPDATE SET snapshot_json = excluded.snapshot_json
            """,
            (target_date, snapshot_json),
        )
        write_conn.commit()
    finally:
        write_conn.close()

    logger.info(f"概要スナップショットを生成・保存しました: {target_date}")
    return snapshot


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
