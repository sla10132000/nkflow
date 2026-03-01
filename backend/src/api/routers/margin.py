"""GET /api/margin — 信用残高データ (Phase 13)"""
from typing import Optional
from sqlite3 import Connection

from fastapi import APIRouter, Depends, Query

from src.api.storage import get_connection

router = APIRouter()


@router.get("/margin/{code}")
def get_margin_by_code(
    code: str,
    weeks: int = Query(default=26, ge=1, le=104),
    conn: Connection = Depends(get_connection),
):
    """
    指定銘柄の信用残高時系列を返す。

    Args:
        code: 銘柄コード (例: 7203)
        weeks: 取得週数 (デフォルト 26週 = 約半年)
    """
    rows = conn.execute(
        """
        SELECT week_date, margin_buy, margin_sell, margin_ratio, buy_change, sell_change
        FROM margin_balances
        WHERE code = ?
        ORDER BY week_date DESC
        LIMIT ?
        """,
        (code, weeks),
    ).fetchall()

    return [dict(row) for row in reversed(rows)]


@router.get("/margin/risk/high")
def get_high_margin_risk(
    ratio_threshold: float = Query(default=8.0, ge=1.0),
    conn: Connection = Depends(get_connection),
):
    """
    信用倍率が高い銘柄の一覧を返す (追証リスク監視用)。

    直近週の信用倍率が ratio_threshold 以上の銘柄を降順で返す。

    Args:
        ratio_threshold: 信用倍率の下限 (デフォルト 8.0倍)
    """
    rows = conn.execute(
        """
        SELECT mb.code, s.name, s.sector,
               mb.week_date, mb.margin_buy, mb.margin_sell,
               mb.margin_ratio, mb.buy_change, mb.sell_change
        FROM margin_balances mb
        JOIN stocks s ON mb.code = s.code
        INNER JOIN (
            SELECT code, MAX(week_date) AS max_week
            FROM margin_balances
            GROUP BY code
        ) latest ON mb.code = latest.code AND mb.week_date = latest.max_week
        WHERE mb.margin_ratio >= ?
        ORDER BY mb.margin_ratio DESC
        """,
        (ratio_threshold,),
    ).fetchall()

    return [dict(row) for row in rows]
