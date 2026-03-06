"""GET /api/prices/{code}"""
from typing import Optional
from sqlite3 import Connection

from fastapi import APIRouter, Depends, HTTPException, Query

from src.api.storage import get_connection

router = APIRouter()


@router.get("/prices/{code}")
def get_prices(
    code: str,
    from_: Optional[str] = Query(None, alias="from"),
    to: Optional[str] = None,
    conn: Connection = Depends(get_connection),
):
    """指定銘柄の時系列 OHLCV データを返す。"""
    query = """
        SELECT date, open, high, low, close, volume,
               return_rate, price_range, range_pct, relative_strength
        FROM daily_prices
        WHERE code = ?
    """
    params: list = [code]

    if from_:
        query += " AND date >= ?"
        params.append(from_)
    if to:
        query += " AND date <= ?"
        params.append(to)

    query += " ORDER BY date"

    rows = conn.execute(query, params).fetchall()
    if not rows:
        raise HTTPException(status_code=404, detail=f"銘柄 {code} のデータが見つかりません")

    return [dict(row) for row in rows]
