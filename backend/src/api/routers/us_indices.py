"""GET /api/us-indices — 米国主要株価指数 (Phase 20) / GET /api/us-sectors — セクター ETF (Phase 23b)"""
from sqlite3 import Connection
from typing import Optional

from fastapi import APIRouter, Depends, Query

from src.api.storage import get_connection

# セクター ETF ティッカー一覧 (パラメータ検証・レスポンス補完用)
_SECTOR_ETF_TICKERS = (
    "XLK", "XLF", "XLV", "XLE", "XLI", "XLY", "XLP", "XLU", "XLB", "XLRE", "XLC"
)
_SECTOR_ETF_PLACEHOLDERS = ",".join(f"'{t}'" for t in _SECTOR_ETF_TICKERS)

router = APIRouter()


@router.get("/us-indices")
def get_us_indices(
    ticker: Optional[str] = None,
    days: int = Query(default=90, ge=1, le=1825),
    conn: Connection = Depends(get_connection),
):
    """
    米国主要株価指数の時系列データを返す。

    Args:
        ticker: 指数ティッカー (例: ^GSPC)。省略時は全指数
        days: 取得日数 (デフォルト 90)
    """
    if ticker:
        rows = conn.execute(
            """
            SELECT date, ticker, name, open, high, low, close, volume,
                   ROUND((close - LAG(close) OVER (PARTITION BY ticker ORDER BY date))
                         / LAG(close) OVER (PARTITION BY ticker ORDER BY date) * 100, 4)
                   AS change_pct
            FROM (
                SELECT date, ticker, name, open, high, low, close, volume
                FROM us_indices
                WHERE ticker = ?
                ORDER BY date DESC
                LIMIT ?
            ) sub
            ORDER BY date ASC
            """,
            (ticker.upper(), days),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT date, ticker, name, open, high, low, close, volume,
                   ROUND((close - LAG(close) OVER (PARTITION BY ticker ORDER BY date))
                         / LAG(close) OVER (PARTITION BY ticker ORDER BY date) * 100, 4)
                   AS change_pct
            FROM (
                SELECT date, ticker, name, open, high, low, close, volume
                FROM us_indices
                WHERE date >= (
                    SELECT DATE(MAX(date), ? || ' days')
                    FROM us_indices
                )
                ORDER BY ticker, date
            ) sub
            ORDER BY ticker, date ASC
            """,
            (f"-{days}",),
        ).fetchall()

    return [dict(row) for row in rows]


@router.get("/us-indices/summary")
def get_us_indices_summary(conn: Connection = Depends(get_connection)):
    """
    各指数の最新値・前日比・年初来リターンを返す。
    """
    rows = conn.execute(
        """
        WITH latest AS (
            SELECT ui.ticker, ui.name, ui.date, ui.close
            FROM us_indices ui
            INNER JOIN (
                SELECT ticker, MAX(date) AS max_date
                FROM us_indices
                GROUP BY ticker
            ) m ON ui.ticker = m.ticker AND ui.date = m.max_date
        ),
        prev AS (
            SELECT ui.ticker, ui.close AS prev_close
            FROM us_indices ui
            INNER JOIN (
                SELECT ticker, MAX(date) AS prev_date
                FROM us_indices
                WHERE date < (SELECT MAX(date) FROM us_indices)
                GROUP BY ticker
            ) p ON ui.ticker = p.ticker AND ui.date = p.prev_date
        ),
        ytd_start AS (
            SELECT ui.ticker, ui.close AS ytd_close
            FROM us_indices ui
            INNER JOIN (
                SELECT ticker, MIN(date) AS first_date
                FROM us_indices
                WHERE date >= STRFTIME('%Y-01-01', 'now')
                GROUP BY ticker
            ) y ON ui.ticker = y.ticker AND ui.date = y.first_date
        )
        SELECT
            l.ticker,
            l.name,
            l.date,
            l.close,
            ROUND((l.close - p.prev_close) / p.prev_close * 100, 4) AS change_pct,
            ROUND((l.close - y.ytd_close)  / y.ytd_close  * 100, 4) AS ytd_return_pct
        FROM latest l
        LEFT JOIN prev p     ON l.ticker = p.ticker
        LEFT JOIN ytd_start y ON l.ticker = y.ticker
        ORDER BY l.ticker
        """
    ).fetchall()

    return [dict(row) for row in rows]


# ─────────────────────────────────────────────────────────────────────────────
# Phase 23b: 米国セクター ETF
# ─────────────────────────────────────────────────────────────────────────────

# 期間ごとの「何営業日前を基準にするか」マッピング
_PERIOD_OFFSET: dict[str, int] = {
    "1d": 1,
    "1w": 5,
    "1m": 21,
    "3m": 63,
}


@router.get("/us-sectors/performance")
def get_us_sectors_performance(
    period: str = Query(default="1d", pattern="^(1d|1w|1m|3m)$"),
    conn: Connection = Depends(get_connection),
):
    """
    セクター ETF の騰落率 + volume を返す (騰落率降順)。

    Args:
        period: 1d / 1w / 1m / 3m
    """
    offset = _PERIOD_OFFSET.get(period, 1)

    rows = conn.execute(
        f"""
        WITH latest_date AS (
            SELECT MAX(date) AS max_date
            FROM us_indices
            WHERE ticker IN ({_SECTOR_ETF_PLACEHOLDERS})
        ),
        base AS (
            SELECT ticker,
                   close AS base_close
            FROM us_indices
            WHERE ticker IN ({_SECTOR_ETF_PLACEHOLDERS})
              AND date = (
                  SELECT MAX(date) FROM us_indices
                  WHERE ticker IN ({_SECTOR_ETF_PLACEHOLDERS})
                    AND date < (
                        SELECT DATE(max_date, ? || ' days')
                        FROM latest_date
                    )
              )
        )
        SELECT
            t.ticker,
            t.name,
            t.close,
            t.volume,
            ROUND((t.close - b.base_close) / b.base_close * 100, 2) AS change_pct
        FROM us_indices t
        JOIN latest_date ld ON t.date = ld.max_date
        JOIN base b ON b.ticker = t.ticker
        WHERE t.ticker IN ({_SECTOR_ETF_PLACEHOLDERS})
        ORDER BY change_pct DESC
        """,
        (f"-{offset}",),
    ).fetchall()

    if not rows:
        return {"date": None, "period": period, "sectors": []}

    from src.config import US_SECTOR_ETF_TICKERS
    sector_map = {k: v["sector"] for k, v in US_SECTOR_ETF_TICKERS.items()}

    latest_date = conn.execute(
        f"SELECT MAX(date) FROM us_indices WHERE ticker IN ({_SECTOR_ETF_PLACEHOLDERS})"
    ).fetchone()[0]

    sectors = [
        {
            "ticker": row["ticker"],
            "name": row["name"],
            "sector": sector_map.get(row["ticker"], row["ticker"]),
            "close": row["close"],
            "change_pct": row["change_pct"],
            "volume": row["volume"],
        }
        for row in rows
    ]
    return {"date": latest_date, "period": period, "sectors": sectors}


@router.get("/us-sectors/heatmap")
def get_us_sectors_heatmap(
    periods: int = Query(default=12, ge=1, le=52),
    period_type: str = Query(default="weekly", pattern="^(weekly|monthly)$"),
    conn: Connection = Depends(get_connection),
):
    """
    セクター ETF の週次/月次パフォーマンスをヒートマップ用に返す。

    Args:
        periods: 取得期間数 (デフォルト 12)
        period_type: weekly / monthly
    """
    from collections import defaultdict

    from src.config import US_SECTOR_ETF_TICKERS
    sector_map = {k: v["sector"] for k, v in US_SECTOR_ETF_TICKERS.items()}

    if period_type == "weekly":
        period_key_expr = "STRFTIME('%Y-W%W', date)"
    else:
        period_key_expr = "STRFTIME('%Y-%m', date)"

    rows = conn.execute(
        f"""
        WITH period_bounds AS (
            SELECT
                ticker,
                {period_key_expr} AS period_key,
                MIN(date) AS first_date,
                MAX(date) AS last_date
            FROM us_indices
            WHERE ticker IN ({_SECTOR_ETF_PLACEHOLDERS})
            GROUP BY ticker, {period_key_expr}
        ),
        period_returns AS (
            SELECT
                pb.ticker,
                pb.period_key,
                ROUND(
                    (last_row.close - first_row.close) / first_row.close * 100,
                    2
                ) AS return_pct
            FROM period_bounds pb
            JOIN us_indices first_row
              ON first_row.ticker = pb.ticker AND first_row.date = pb.first_date
            JOIN us_indices last_row
              ON last_row.ticker = pb.ticker AND last_row.date = pb.last_date
        ),
        ranked_periods AS (
            SELECT DISTINCT period_key
            FROM period_returns
            ORDER BY period_key DESC
            LIMIT {periods}
        )
        SELECT pr.ticker, pr.period_key, pr.return_pct
        FROM period_returns pr
        INNER JOIN ranked_periods rp ON pr.period_key = rp.period_key
        ORDER BY pr.period_key ASC, pr.ticker
        """
    ).fetchall()

    period_keys: list[str] = []
    seen: set[str] = set()
    for row in rows:
        if row["period_key"] not in seen:
            period_keys.append(row["period_key"])
            seen.add(row["period_key"])

    ticker_values: dict[str, dict[str, float | None]] = defaultdict(dict)
    for row in rows:
        ticker_values[row["ticker"]][row["period_key"]] = row["return_pct"]

    sectors = [
        {
            "ticker": ticker,
            "sector": sector_map.get(ticker, ticker),
            "values": [ticker_values[ticker].get(pk) for pk in period_keys],
        }
        for ticker in _SECTOR_ETF_TICKERS
        if ticker in ticker_values
    ]

    return {"periods": period_keys, "sectors": sectors}
