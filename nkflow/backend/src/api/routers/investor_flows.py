"""GET /api/investor-flows/timeseries, /api/investor-flows/indicators, /api/investor-flows/latest"""
import json
from sqlite3 import Connection
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from src.api.storage import get_connection

router = APIRouter()


@router.get("/investor-flows/timeseries")
def get_investor_flow_timeseries(
    weeks: int = 52,
    investor_type: str = "foreigners",
    conn: Connection = Depends(get_connection),
):
    """
    投資主体別フローの週次時系列を返す。

    Query Parameters:
        weeks: 取得週数 (1〜156, デフォルト: 52)
        investor_type: 投資主体 (foreigners / individuals / investment_trusts /
                       trust_banks / business_cos)

    Response:
        [{ week_start, week_end, sales, purchases, balance, published_date }]
    """
    allowed_types = {
        "foreigners", "individuals", "investment_trusts", "trust_banks", "business_cos"
    }
    if investor_type not in allowed_types:
        raise HTTPException(
            status_code=400,
            detail=f"investor_type は次のいずれかを指定してください: {sorted(allowed_types)}",
        )
    if not (1 <= weeks <= 156):
        raise HTTPException(status_code=400, detail="weeks は 1〜156 の範囲で指定してください")

    rows = conn.execute(
        """
        SELECT week_start, week_end, section, investor_type,
               sales, purchases, balance, published_date
        FROM investor_flow_weekly
        WHERE investor_type = ?
        ORDER BY week_end DESC
        LIMIT ?
        """,
        (investor_type, weeks),
    ).fetchall()

    if not rows:
        return []

    result = [
        {
            "week_start":     r["week_start"],
            "week_end":       r["week_end"],
            "section":        r["section"],
            "investor_type":  r["investor_type"],
            "sales":          r["sales"],
            "purchases":      r["purchases"],
            "balance":        r["balance"],
            "published_date": r["published_date"],
        }
        for r in rows
    ]
    # 古い順に並び替えて返す (フロントエンドでの時系列チャート表示用)
    return list(reversed(result))


@router.get("/investor-flows/indicators")
def get_investor_flow_indicators(
    weeks: int = 26,
    conn: Connection = Depends(get_connection),
):
    """
    計算済みの投資主体別フロー指標の時系列を返す。

    Query Parameters:
        weeks: 取得週数 (1〜104, デフォルト: 26)

    Response:
        [{ week_end, foreigners_net, individuals_net, foreigners_4w_ma,
           individuals_4w_ma, foreigners_momentum, individuals_momentum,
           divergence_score, nikkei_return_4w, flow_regime }]
    """
    if not (1 <= weeks <= 104):
        raise HTTPException(status_code=400, detail="weeks は 1〜104 の範囲で指定してください")

    rows = conn.execute(
        """
        SELECT week_end, foreigners_net, individuals_net,
               foreigners_4w_ma, individuals_4w_ma,
               foreigners_momentum, individuals_momentum,
               divergence_score, nikkei_return_4w, flow_regime
        FROM investor_flow_indicators
        ORDER BY week_end DESC
        LIMIT ?
        """,
        (weeks,),
    ).fetchall()

    if not rows:
        return []

    result = [
        {
            "week_end":              r["week_end"],
            "foreigners_net":        r["foreigners_net"],
            "individuals_net":       r["individuals_net"],
            "foreigners_4w_ma":      r["foreigners_4w_ma"],
            "individuals_4w_ma":     r["individuals_4w_ma"],
            "foreigners_momentum":   r["foreigners_momentum"],
            "individuals_momentum":  r["individuals_momentum"],
            "divergence_score":      r["divergence_score"],
            "nikkei_return_4w":      r["nikkei_return_4w"],
            "flow_regime":           r["flow_regime"],
        }
        for r in rows
    ]
    return list(reversed(result))


@router.get("/investor-flows/latest")
def get_investor_flow_latest(
    conn: Connection = Depends(get_connection),
):
    """
    最新週の投資主体別フロー指標と全投資主体の売買動向サマリーを返す。

    Response:
        {
          "week_end": str,
          "indicators": { ... },
          "flows": { "foreigners": {...}, "individuals": {...}, ... },
          "signals": [ { signal_type, direction, confidence, reasoning } ]
        }
    """
    # 最新指標
    indicator_row = conn.execute(
        """
        SELECT week_end, foreigners_net, individuals_net,
               foreigners_4w_ma, individuals_4w_ma,
               foreigners_momentum, individuals_momentum,
               divergence_score, nikkei_return_4w, flow_regime
        FROM investor_flow_indicators
        ORDER BY week_end DESC
        LIMIT 1
        """
    ).fetchone()

    if indicator_row is None:
        raise HTTPException(status_code=404, detail="投資主体別フロー指標がありません")

    week_end = indicator_row["week_end"]

    # 最新週の全投資主体の売買動向
    flow_rows = conn.execute(
        """
        SELECT investor_type, sales, purchases, balance, published_date
        FROM investor_flow_weekly
        WHERE week_end = ?
        """,
        (week_end,),
    ).fetchall()

    flows: dict = {}
    for r in flow_rows:
        flows[r["investor_type"]] = {
            "sales":          r["sales"],
            "purchases":      r["purchases"],
            "balance":        r["balance"],
            "published_date": r["published_date"],
        }

    # 最新週に対応するシグナル
    signal_rows = conn.execute(
        """
        SELECT signal_type, direction, confidence, reasoning
        FROM signals
        WHERE date = ? AND signal_type LIKE 'investor_flow_%'
        ORDER BY confidence DESC
        """,
        (week_end,),
    ).fetchall()

    signals_list = [
        {
            "signal_type": r["signal_type"],
            "direction":   r["direction"],
            "confidence":  r["confidence"],
            "reasoning":   json.loads(r["reasoning"]) if r["reasoning"] else {},
        }
        for r in signal_rows
    ]

    return {
        "week_end": week_end,
        "indicators": {
            "foreigners_net":        indicator_row["foreigners_net"],
            "individuals_net":       indicator_row["individuals_net"],
            "foreigners_4w_ma":      indicator_row["foreigners_4w_ma"],
            "individuals_4w_ma":     indicator_row["individuals_4w_ma"],
            "foreigners_momentum":   indicator_row["foreigners_momentum"],
            "individuals_momentum":  indicator_row["individuals_momentum"],
            "divergence_score":      indicator_row["divergence_score"],
            "nikkei_return_4w":      indicator_row["nikkei_return_4w"],
            "flow_regime":           indicator_row["flow_regime"],
        },
        "flows":   flows,
        "signals": signals_list,
    }
