"""GET /api/summary"""
from fastapi import APIRouter, Depends
from sqlite3 import Connection

from src.api.helpers import safe_json_loads
from src.api.storage import get_connection

router = APIRouter()

_TOP_N = 10


def _compute_top_gainers_losers(conn: Connection, date: str):
    """daily_prices の close から騰落率を動的に計算して上昇/下落上位を返す。"""
    rows = conn.execute(
        """
        SELECT dp.code, s.name, s.sector,
               (dp.close - dp2.close) / dp2.close AS return_rate
        FROM daily_prices dp
        JOIN stocks s ON s.code = dp.code
        JOIN daily_prices dp2 ON dp2.code = dp.code
            AND dp2.date = (SELECT MAX(date) FROM daily_prices WHERE date < dp.date)
        WHERE dp.date = ?
          AND dp.close IS NOT NULL AND dp2.close IS NOT NULL
        """,
        (date,),
    ).fetchall()

    if not rows:
        return [], []

    items = [dict(r) for r in rows]
    items.sort(key=lambda x: x["return_rate"], reverse=True)
    gainers = items[:_TOP_N]
    losers = list(reversed(items[-_TOP_N:]))
    return gainers, losers


def _compute_sector_rotation(conn: Connection, date: str):
    """daily_prices の close から動的にセクター別騰落率を計算して返す。"""
    rows = conn.execute(
        """
        SELECT s.sector,
               AVG((dp.close - dp2.close) / dp2.close) AS avg_return,
               SUM(dp.volume) AS total_volume,
               COUNT(*) AS stock_count
        FROM daily_prices dp
        JOIN stocks s ON s.code = dp.code
        JOIN daily_prices dp2 ON dp2.code = dp.code
            AND dp2.date = (SELECT MAX(date) FROM daily_prices WHERE date < dp.date)
        WHERE dp.date = ?
          AND dp.close IS NOT NULL AND dp2.close IS NOT NULL
        GROUP BY s.sector
        ORDER BY avg_return DESC
        """,
        (date,),
    ).fetchall()

    return [dict(r) for r in rows]


@router.get("/summary")
def get_summary(days: int = 30, conn: Connection = Depends(get_connection)):
    """直近 N 日分の日次サマリを返す。"""
    rows = conn.execute(
        """
        SELECT date, nikkei_close, nikkei_return, regime,
               top_gainers, top_losers, active_signals, sector_rotation
        FROM daily_summary
        ORDER BY date DESC
        LIMIT ?
        """,
        (days,),
    ).fetchall()

    result = []
    for row in rows:
        item = dict(row)
        for col in ("top_gainers", "top_losers", "sector_rotation"):
            item[col] = safe_json_loads(item[col])

        # top_gainers/top_losers が空の場合は daily_prices から動的計算
        if not item["top_gainers"] and not item["top_losers"]:
            gainers, losers = _compute_top_gainers_losers(conn, item["date"])
            item["top_gainers"] = gainers
            item["top_losers"] = losers

        # sector_rotation が空の場合は動的計算
        if not item["sector_rotation"]:
            item["sector_rotation"] = _compute_sector_rotation(conn, item["date"])

        result.append(item)

    return result
