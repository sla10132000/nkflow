"""GET /api/forex — 為替レートデータ (Phase 13)"""
from typing import Optional
from sqlite3 import Connection

from fastapi import APIRouter, Depends, Query

from src.api.storage import get_connection

router = APIRouter()


@router.get("/forex")
def get_forex(
    pair: str = "USDJPY",
    days: int = Query(default=60, ge=1, le=365),
    conn: Connection = Depends(get_connection),
):
    """
    為替レートの時系列データを返す。

    Args:
        pair: 通貨ペア (例: USDJPY, EURUSD)
        days: 取得日数 (デフォルト 60)
    """
    rows = conn.execute(
        """
        SELECT date, pair, open, high, low, close, change_rate, ma20
        FROM exchange_rates
        WHERE pair = ?
        ORDER BY date DESC
        LIMIT ?
        """,
        (pair.upper(), days),
    ).fetchall()

    return [dict(row) for row in reversed(rows)]


@router.get("/forex/latest")
def get_forex_latest(conn: Connection = Depends(get_connection)):
    """
    全通貨ペアの最新レートを返す。
    フロントエンドのヘッダー表示などに使用。
    """
    rows = conn.execute(
        """
        SELECT er.date, er.pair, er.close, er.change_rate
        FROM exchange_rates er
        INNER JOIN (
            SELECT pair, MAX(date) AS max_date
            FROM exchange_rates
            GROUP BY pair
        ) latest ON er.pair = latest.pair AND er.date = latest.max_date
        ORDER BY er.pair
        """,
    ).fetchall()

    return [dict(row) for row in rows]
