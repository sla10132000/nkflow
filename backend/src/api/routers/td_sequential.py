"""GET /api/td-sequential/{code} — TD Sequential (Phase 22)"""
from sqlite3 import Connection

from fastapi import APIRouter, Depends, HTTPException, Query

from src.api.storage import get_connection

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
    stock = conn.execute(
        "SELECT code FROM stocks WHERE code = ?", (code,)
    ).fetchone()
    if not stock:
        raise HTTPException(status_code=404, detail=f"銘柄 {code} が見つかりません")

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
    except Exception:
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
    stock = conn.execute(
        "SELECT code FROM stocks WHERE code = ?", (code,)
    ).fetchone()
    if not stock:
        raise HTTPException(status_code=404, detail=f"銘柄 {code} が見つかりません")

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
    except Exception:
        return None

    return dict(row) if row else None
