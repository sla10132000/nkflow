"""GET /api/summary"""
import json
from typing import Optional

from fastapi import APIRouter, Depends
from sqlite3 import Connection

from src.api.storage import get_connection

router = APIRouter()


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
            if item[col]:
                try:
                    item[col] = json.loads(item[col])
                except (json.JSONDecodeError, TypeError):
                    pass
        result.append(item)

    return result
