"""GET /api/stock/{code}"""
import json
from sqlite3 import Connection

from fastapi import APIRouter, Depends, HTTPException

from src.api.storage import get_connection

router = APIRouter()


@router.get("/stocks")
def get_stocks(conn: Connection = Depends(get_connection)):
    """銘柄一覧: code・name・sector を全件返す。"""
    rows = conn.execute(
        "SELECT code, name, sector FROM stocks ORDER BY code"
    ).fetchall()
    return [dict(r) for r in rows]


@router.get("/stock/{code}")
def get_stock(code: str, conn: Connection = Depends(get_connection)):
    """銘柄詳細: 基本情報 + 因果連鎖 + 相関銘柄 + クラスター + 関連シグナル。"""
    stock = conn.execute(
        "SELECT code, name, sector FROM stocks WHERE code = ?", (code,)
    ).fetchone()
    if not stock:
        raise HTTPException(status_code=404, detail=f"銘柄 {code} が見つかりません")

    stock = dict(stock)

    # 直近30日の価格データ
    prices = conn.execute(
        """
        SELECT date, open, high, low, close, volume, return_rate
        FROM daily_prices WHERE code = ?
        ORDER BY date DESC LIMIT 30
        """,
        (code,),
    ).fetchall()
    stock["recent_prices"] = [dict(r) for r in prices]

    # この銘柄が原因となる因果関係 (→ 影響を受ける銘柄)
    causes = conn.execute(
        """
        SELECT gc.target, gc.lag_days, gc.p_value, gc.f_stat, s.name, s.sector
        FROM graph_causality gc
        JOIN stocks s ON gc.target = s.code
        WHERE gc.source = ?
        ORDER BY gc.p_value LIMIT 10
        """,
        (code,),
    ).fetchall()
    stock["causes"] = [dict(r) for r in causes]

    # この銘柄に影響を与える因果関係 (← この銘柄を先導する銘柄)
    caused_by = conn.execute(
        """
        SELECT gc.source, gc.lag_days, gc.p_value, gc.f_stat, s.name, s.sector
        FROM graph_causality gc
        JOIN stocks s ON gc.source = s.code
        WHERE gc.target = ?
        ORDER BY gc.p_value LIMIT 10
        """,
        (code,),
    ).fetchall()
    stock["caused_by"] = [dict(r) for r in caused_by]

    # 相関が高い銘柄
    correlated = conn.execute(
        """
        SELECT
            CASE WHEN gc.stock_a = ? THEN gc.stock_b ELSE gc.stock_a END AS peer_code,
            gc.coefficient,
            s.name, s.sector
        FROM graph_correlations gc
        JOIN stocks s ON s.code = CASE WHEN gc.stock_a = ? THEN gc.stock_b ELSE gc.stock_a END
        WHERE (gc.stock_a = ? OR gc.stock_b = ?) AND ABS(gc.coefficient) >= 0.5
        ORDER BY ABS(gc.coefficient) DESC LIMIT 10
        """,
        (code, code, code, code),
    ).fetchall()
    stock["correlated"] = [dict(r) for r in correlated]

    # 同クラスターの銘柄
    community = conn.execute(
        "SELECT community_id FROM graph_communities WHERE code = ? ORDER BY calc_date DESC LIMIT 1",
        (code,),
    ).fetchone()
    if community:
        cluster_members = conn.execute(
            """
            SELECT gc.code, s.name, s.sector
            FROM graph_communities gc
            JOIN stocks s ON gc.code = s.code
            WHERE gc.community_id = ? AND gc.code != ?
            ORDER BY gc.calc_date DESC LIMIT 20
            """,
            (community["community_id"], code),
        ).fetchall()
        stock["cluster"] = {
            "community_id": community["community_id"],
            "members": [dict(r) for r in cluster_members],
        }
    else:
        stock["cluster"] = None

    # 関連シグナル
    sigs = conn.execute(
        """
        SELECT id, date, signal_type, direction, confidence, reasoning
        FROM signals WHERE code = ?
        ORDER BY date DESC LIMIT 10
        """,
        (code,),
    ).fetchall()
    parsed_sigs = []
    for sig in sigs:
        s = dict(sig)
        if s["reasoning"]:
            try:
                s["reasoning"] = json.loads(s["reasoning"])
            except (json.JSONDecodeError, TypeError):
                pass
        parsed_sigs.append(s)
    stock["signals"] = parsed_sigs

    return stock
