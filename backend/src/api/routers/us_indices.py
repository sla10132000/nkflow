"""GET /api/us-indices — 米国主要株価指数 (Phase 20)"""
from sqlite3 import Connection
from typing import Optional

from fastapi import APIRouter, Depends, Query

from src.api.storage import get_connection

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
