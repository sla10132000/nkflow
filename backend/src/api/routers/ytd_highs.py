"""GET /api/ytd-highs — 年初来高値に近い銘柄一覧"""
from datetime import date
from sqlite3 import Connection

from fastapi import APIRouter, Depends

from src.api.storage import get_connection

router = APIRouter()


@router.get("/ytd-highs")
def get_ytd_highs(
    limit: int = 10,
    threshold_pct: float = 5.0,
    conn: Connection = Depends(get_connection),
):
    """年初来高値との乖離率が threshold_pct % 以内の銘柄を返す。

    - ytd_high: 年初来最高値 (high の最大値)
    - close: 最新終値
    - gap_pct: (close - ytd_high) / ytd_high * 100 (0 = 年初来高値更新、負 = 以下)
    """
    ytd_start = f"{date.today().year}-01-01"

    rows = conn.execute(
        """
        WITH latest_date AS (
            SELECT MAX(date) AS d FROM daily_prices
        ),
        ytd AS (
            SELECT dp.code,
                   MAX(dp.high) AS ytd_high
            FROM daily_prices dp, latest_date
            WHERE dp.date >= ?
              AND dp.date <= latest_date.d
              AND dp.high IS NOT NULL
            GROUP BY dp.code
        ),
        latest AS (
            SELECT dp.code, dp.close
            FROM daily_prices dp
            JOIN latest_date ON dp.date = latest_date.d
            WHERE dp.close IS NOT NULL
        )
        SELECT l.code,
               s.name,
               s.sector,
               l.close,
               y.ytd_high,
               (l.close - y.ytd_high) / y.ytd_high * 100.0 AS gap_pct
        FROM latest l
        JOIN ytd y ON y.code = l.code
        JOIN stocks s ON s.code = l.code
        WHERE (l.close - y.ytd_high) / y.ytd_high * 100.0 >= -?
        ORDER BY gap_pct DESC
        LIMIT ?
        """,
        (ytd_start, threshold_pct, limit),
    ).fetchall()

    return [dict(r) for r in rows]
