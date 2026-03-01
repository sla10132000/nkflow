"""GET /api/backtest — バックテスト結果 (Phase 14)"""
from sqlite3 import Connection
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from src.api.storage import get_connection

router = APIRouter()


@router.get("/backtest")
def list_backtest_runs(
    limit: int = Query(default=20, ge=1, le=100),
    conn: Connection = Depends(get_connection),
):
    """
    バックテスト実行一覧を返す (新しい順)。

    Args:
        limit: 取得件数 (デフォルト 20)
    """
    rows = conn.execute(
        """
        SELECT r.id, r.name, r.signal_type, r.from_date, r.to_date,
               r.holding_days, r.direction_filter, r.min_confidence, r.created_at,
               res.total_trades, res.win_rate, res.avg_return,
               res.total_return, res.max_drawdown, res.sharpe_ratio
        FROM backtest_runs r
        LEFT JOIN backtest_results res ON r.id = res.run_id
        ORDER BY r.id DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()

    return [dict(row) for row in rows]


@router.get("/backtest/{run_id}")
def get_backtest_run(run_id: int, conn: Connection = Depends(get_connection)):
    """
    指定バックテストの設定と集計結果を返す。

    Args:
        run_id: バックテスト実行 ID
    """
    run = conn.execute(
        "SELECT * FROM backtest_runs WHERE id = ?", (run_id,)
    ).fetchone()
    if run is None:
        raise HTTPException(status_code=404, detail="backtest run not found")

    result = conn.execute(
        "SELECT * FROM backtest_results WHERE run_id = ?", (run_id,)
    ).fetchone()

    return {
        "run": dict(run),
        "result": dict(result) if result else None,
    }


@router.get("/backtest/{run_id}/trades")
def get_backtest_trades(
    run_id: int,
    code: Optional[str] = None,
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    conn: Connection = Depends(get_connection),
):
    """
    指定バックテストのトレード明細を返す。

    Args:
        run_id: バックテスト実行 ID
        code:   銘柄コードでフィルタ (省略可)
        limit:  取得件数 (最大 1000)
        offset: オフセット (ページング用)
    """
    run = conn.execute(
        "SELECT id FROM backtest_runs WHERE id = ?", (run_id,)
    ).fetchone()
    if run is None:
        raise HTTPException(status_code=404, detail="backtest run not found")

    query = """
        SELECT t.id, t.signal_id, t.code, s.name AS stock_name,
               t.signal_date, t.entry_date, t.exit_date,
               t.entry_price, t.exit_price, t.return_rate, t.direction
        FROM backtest_trades t
        LEFT JOIN stocks s ON t.code = s.code
        WHERE t.run_id = ?
    """
    params: list = [run_id]

    if code:
        query += " AND t.code = ?"
        params.append(code)

    query += " ORDER BY t.signal_date, t.code LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    rows = conn.execute(query, params).fetchall()
    return [dict(row) for row in rows]
