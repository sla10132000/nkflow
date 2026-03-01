"""GET /api/signals/accuracy — シグナル的中率レポート (Phase 11)"""
from typing import Optional
from sqlite3 import Connection

from fastapi import APIRouter, Depends

from src.api.storage import get_connection

router = APIRouter()


@router.get("/signals/accuracy")
def get_accuracy(
    signal_type: Optional[str] = None,
    horizon_days: Optional[int] = None,
    conn: Connection = Depends(get_connection),
):
    """
    シグナルタイプ × ホライズン別の最新的中率を返す。

    最新の calc_date の集計行のみ返す (各 (signal_type, horizon_days) の最新レコード)。

    Query params:
      signal_type  : 絞り込み (省略時: 全タイプ)
      horizon_days : 絞り込み (省略時: 全ホライズン)
    """
    query = """
        SELECT
            sa.signal_type,
            sa.horizon_days,
            sa.calc_date,
            sa.total_signals,
            sa.hits,
            sa.hit_rate,
            sa.avg_return
        FROM signal_accuracy sa
        INNER JOIN (
            SELECT signal_type, horizon_days, MAX(calc_date) AS latest
            FROM signal_accuracy
            GROUP BY signal_type, horizon_days
        ) latest ON sa.signal_type = latest.signal_type
               AND sa.horizon_days = latest.horizon_days
               AND sa.calc_date    = latest.latest
        WHERE 1=1
    """
    params: list = []

    if signal_type:
        query += " AND sa.signal_type = ?"
        params.append(signal_type)
    if horizon_days is not None:
        query += " AND sa.horizon_days = ?"
        params.append(horizon_days)

    query += " ORDER BY sa.signal_type, sa.horizon_days"

    rows = conn.execute(query, params).fetchall()
    return [dict(row) for row in rows]


@router.get("/signals/accuracy/history")
def get_accuracy_history(
    signal_type: str,
    horizon_days: int = 5,
    limit: int = 30,
    conn: Connection = Depends(get_connection),
):
    """
    特定タイプの的中率推移 (時系列) を返す。

    Query params:
      signal_type  : 必須
      horizon_days : 5 / 10 / 20 (デフォルト 5)
      limit        : 取得日数 (デフォルト 30)
    """
    rows = conn.execute(
        """
        SELECT calc_date, total_signals, hits, hit_rate, avg_return
        FROM signal_accuracy
        WHERE signal_type = ? AND horizon_days = ?
        ORDER BY calc_date DESC
        LIMIT ?
        """,
        (signal_type, horizon_days, limit),
    ).fetchall()
    return [dict(row) for row in rows]
