"""GET /api/td-sequential/{code} — TD Sequential (Phase 22)"""
import logging
import sqlite3
from sqlite3 import Connection

from fastapi import APIRouter, Depends, Query

from src.api.helpers import require_stock
from src.api.storage import get_connection

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/td-sequential/{code}")
def get_td_sequential(
    code: str,
    days: int = Query(default=120, ge=1, le=500),
    conn: Connection = Depends(get_connection),
):
    """
    指定銘柄の TD Sequential カウントを時系列で返す (昇順)。

    Args:
        code: 銘柄コード (例: 7203)
        days: 取得日数 (デフォルト 120)

    Returns:
        List[{date, setup_bull, setup_bear, countdown_bull, countdown_bear}]
        0 はそのカウントが非アクティブであることを示す。
    """
    require_stock(conn, code)

    try:
        rows = conn.execute(
            """
            SELECT date, setup_bull, setup_bear, countdown_bull, countdown_bear
            FROM td_sequential
            WHERE code = ?
            ORDER BY date DESC
            LIMIT ?
            """,
            (code, days),
        ).fetchall()
    except sqlite3.OperationalError:
        logger.warning("td_sequential テーブルが存在しません (code=%s)", code)
        return []

    result = [dict(r) for r in rows]
    result.reverse()
    return result


@router.get("/td-sequential/{code}/latest")
def get_td_sequential_latest(
    code: str,
    conn: Connection = Depends(get_connection),
):
    """
    指定銘柄の TD Sequential 最新状態を返す (StockView サマリーカード用)。

    Returns:
        {date, setup_bull, setup_bear, countdown_bull, countdown_bear} | null
    """
    require_stock(conn, code)

    try:
        row = conn.execute(
            """
            SELECT date, setup_bull, setup_bear, countdown_bull, countdown_bear
            FROM td_sequential
            WHERE code = ?
            ORDER BY date DESC
            LIMIT 1
            """,
            (code,),
        ).fetchone()
    except sqlite3.OperationalError:
        logger.warning("td_sequential テーブルが存在しません (code=%s)", code)
        return None

    return dict(row) if row else None
