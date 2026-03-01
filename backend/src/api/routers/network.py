"""GET /api/network/{type}"""
from typing import Optional
from sqlite3 import Connection

from fastapi import APIRouter, Depends, HTTPException

from src.api.storage import get_connection

router = APIRouter()


@router.get("/network/{type}")
def get_network(
    type: str,
    period: str = "60d",
    threshold: float = 0.7,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    conn: Connection = Depends(get_connection),
):
    """
    ネットワークデータを vis-network 互換フォーマットで返す。

    type: "correlation" | "causality" | "fund_flow"
    fund_flow の場合: date_from / date_to で期間を絞る (省略時は最新日)
    """
    if type == "correlation":
        return _correlation_network(conn, period, threshold)
    elif type == "causality":
        return _causality_network(conn, period, threshold)
    elif type == "fund_flow":
        return _fund_flow_network(conn, date_from, date_to)
    else:
        raise HTTPException(status_code=400, detail=f"不明なタイプ: {type}")


def _correlation_network(conn: Connection, period: str, threshold: float) -> dict:
    period_days = _parse_period(period)
    rows = conn.execute(
        """
        SELECT gc.stock_a, gc.stock_b, gc.coefficient,
               s1.sector AS sector_a, s2.sector AS sector_b
        FROM graph_correlations gc
        JOIN stocks s1 ON gc.stock_a = s1.code
        JOIN stocks s2 ON gc.stock_b = s2.code
        WHERE gc.period = ? AND ABS(gc.coefficient) >= ?
        ORDER BY gc.calc_date DESC, ABS(gc.coefficient) DESC
        LIMIT 500
        """,
        (f"{period_days}d", threshold),
    ).fetchall()

    return _build_vis_network(rows, edge_value_col="coefficient", directed=False)


def _causality_network(conn: Connection, period: str, threshold: float) -> dict:
    period_days = _parse_period(period)
    rows = conn.execute(
        """
        SELECT gc.source AS stock_a, gc.target AS stock_b, gc.f_stat AS coefficient,
               s1.sector AS sector_a, s2.sector AS sector_b
        FROM graph_causality gc
        JOIN stocks s1 ON gc.source = s1.code
        JOIN stocks s2 ON gc.target = s2.code
        WHERE gc.period = ? AND gc.p_value <= 0.05
        ORDER BY gc.calc_date DESC, gc.f_stat DESC
        LIMIT 500
        """,
        (f"{period_days}d",),
    ).fetchall()

    return _build_vis_network(rows, edge_value_col="coefficient", directed=True)


def _fund_flow_network(
    conn: Connection,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> dict:
    if date_from and date_to:
        # 期間指定: sector ペアごとに平均 return_spread を集計
        rows = conn.execute(
            """
            SELECT sector_from AS stock_a, sector_to AS stock_b,
                   AVG(return_spread) AS coefficient,
                   sector_from AS sector_a, sector_to AS sector_b
            FROM graph_fund_flows
            WHERE date BETWEEN ? AND ?
            GROUP BY sector_from, sector_to
            ORDER BY ABS(AVG(return_spread)) DESC
            """,
            (date_from, date_to),
        ).fetchall()
    else:
        # デフォルト: 最新日のみ
        rows = conn.execute(
            """
            SELECT sector_from AS stock_a, sector_to AS stock_b,
                   return_spread AS coefficient,
                   sector_from AS sector_a, sector_to AS sector_b
            FROM graph_fund_flows
            WHERE date = (SELECT MAX(date) FROM graph_fund_flows)
            ORDER BY ABS(return_spread) DESC
            """,
        ).fetchall()

    return _build_vis_network(rows, edge_value_col="coefficient", directed=True)


def _parse_period(period: str) -> int:
    """'20d' → 20、'60d' → 60 のように変換する。"""
    return int(period.rstrip("d"))


def _build_vis_network(rows, edge_value_col: str, directed: bool) -> dict:
    """vis-network 互換の nodes/edges フォーマットを生成する。"""
    nodes: dict[str, dict] = {}
    edges: list[dict] = []

    for row in rows:
        row = dict(row)
        code_a, code_b = row["stock_a"], row["stock_b"]
        sector_a, sector_b = row.get("sector_a", ""), row.get("sector_b", "")
        value = abs(row.get(edge_value_col, 0) or 0)

        if code_a not in nodes:
            nodes[code_a] = {"id": code_a, "label": code_a, "group": sector_a}
        if code_b not in nodes:
            nodes[code_b] = {"id": code_b, "label": code_b, "group": sector_b}

        edge = {"from": code_a, "to": code_b, "value": round(value, 4)}
        if directed:
            edge["arrows"] = "to"
        edges.append(edge)

    return {"nodes": list(nodes.values()), "edges": edges}
