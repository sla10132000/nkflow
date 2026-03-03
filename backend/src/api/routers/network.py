"""GET /api/network/{type}, /api/market-pressure/timeseries"""
import json
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
    include_pressure: bool = False,
    conn: Connection = Depends(get_connection),
):
    """
    ネットワークデータを vis-network 互換フォーマットで返す。

    type: "correlation" | "causality" | "fund_flow"
    fund_flow の場合: date_from / date_to で期間を絞る (省略時は最新日)
    include_pressure=true の場合: 市場圧力ノードを nodes に追加 (後方互換)
    """
    if type == "correlation":
        return _correlation_network(conn, period, threshold)
    elif type == "causality":
        return _causality_network(conn, period, threshold)
    elif type == "fund_flow":
        result = _fund_flow_network(conn, date_from, date_to)
        if include_pressure:
            _inject_pressure_nodes(conn, result)
        return result
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
        # 期間指定: sector ペアごとに出現頻度 + 平均 return_spread を集計
        rows = conn.execute(
            """
            SELECT sector_from AS stock_a, sector_to AS stock_b,
                   COUNT(*) AS edge_count,
                   AVG(return_spread) AS coefficient,
                   sector_from AS sector_a, sector_to AS sector_b
            FROM graph_fund_flows
            WHERE date BETWEEN ? AND ?
            GROUP BY sector_from, sector_to
            ORDER BY edge_count DESC, ABS(AVG(return_spread)) DESC
            """,
            (date_from, date_to),
        ).fetchall()
        return _build_vis_network(
            rows, edge_value_col="edge_count", directed=True, extra_cols=["coefficient"]
        )
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


@router.get("/fund-flow/timeseries")
def get_fund_flow_timeseries(
    granularity: str = "week",
    limit: int = 12,
    conn: Connection = Depends(get_connection),
):
    """
    資金フローの時系列集計を返す。

    granularity: "week" | "month"
    limit: 取得する期間数 (最新 limit 週 / 月)
    """
    if granularity not in ("week", "month"):
        raise HTTPException(status_code=400, detail="granularity は week または month のいずれかです")

    period_expr = (
        "strftime('%Y-W%W', date)" if granularity == "week" else "strftime('%Y-%m', date)"
    )

    rows = conn.execute(
        f"""
        SELECT
            {period_expr} AS period,
            MIN(date) AS period_start,
            sector_from,
            sector_to,
            COUNT(*) AS cnt,
            AVG(return_spread) AS avg_spread
        FROM graph_fund_flows
        GROUP BY period, sector_from, sector_to
        ORDER BY period
        """
    ).fetchall()

    if not rows:
        return {"periods": [], "start_dates": [], "series": []}

    # 全ユニーク期間を昇順取得し、最新 limit 件に絞る
    all_periods = sorted({r["period"] for r in rows})
    periods = all_periods[-limit:]
    period_set = set(periods)

    # セクターペア別に集計
    pair_data: dict = {}
    pair_total: dict = {}
    period_starts: dict = {}
    for r in rows:
        if r["period"] not in period_set:
            continue
        p = r["period"]
        if p not in period_starts:
            period_starts[p] = r["period_start"]
        key = (r["sector_from"], r["sector_to"])
        if key not in pair_data:
            pair_data[key] = {}
            pair_total[key] = 0
        pair_data[key][p] = {
            "count": r["cnt"],
            "avg_spread": round(float(r["avg_spread"] or 0), 4),
        }
        pair_total[key] += r["cnt"]

    # 上位 8 ペアに絞る
    top_pairs = sorted(pair_total.keys(), key=lambda k: pair_total[k], reverse=True)[:8]

    series = []
    for sf, st in top_pairs:
        values = [
            pair_data[(sf, st)].get(p, {"count": 0, "avg_spread": 0.0})
            for p in periods
        ]
        series.append(
            {"label": f"{sf} → {st}", "sector_from": sf, "sector_to": st, "values": values}
        )

    return {
        "periods": periods,
        "start_dates": [period_starts.get(p, "") for p in periods],
        "series": series,
    }


@router.get("/fund-flow/cumulative")
def get_fund_flow_cumulative(
    base_date: str,
    granularity: str = "week",
    conn: Connection = Depends(get_connection),
):
    """
    base_date を基準点（累積 = 0）として、以降の累積 return_spread と
    セクター累積リターンを返す。

    granularity: "week" | "month"
    """
    if granularity not in ("week", "month"):
        raise HTTPException(status_code=400, detail="granularity は week または month のいずれかです")

    period_expr = (
        "strftime('%Y-W%W', date)" if granularity == "week" else "strftime('%Y-%m', date)"
    )

    # 1. base_date 以降のファンドフローを期間 × ペア別に集計
    flow_rows = conn.execute(
        f"""
        SELECT
            {period_expr} AS period,
            MIN(date) AS period_start,
            sector_from,
            sector_to,
            SUM(return_spread) AS period_spread
        FROM graph_fund_flows
        WHERE date >= ?
        GROUP BY period, sector_from, sector_to
        ORDER BY period
        """,
        (base_date,),
    ).fetchall()

    if not flow_rows:
        return {"base_date": base_date, "periods": [], "series": []}

    # ユニーク期間と開始日の収集
    all_periods: list[str] = []
    period_starts: dict[str, str] = {}
    for r in flow_rows:
        p = r["period"]
        if p not in period_starts:
            all_periods.append(p)
            period_starts[p] = r["period_start"]
    all_periods = sorted(set(all_periods))

    # 2. 各期間のレジーム (daily_summary の多数決)
    regime_rows = conn.execute(
        f"""
        SELECT {period_expr} AS period, regime, COUNT(*) AS cnt
        FROM daily_summary
        WHERE date >= ? AND regime IS NOT NULL
        GROUP BY period, regime
        """,
        (base_date,),
    ).fetchall()

    regime_votes: dict[str, dict[str, int]] = {}
    for r in regime_rows:
        p = r["period"]
        if p not in regime_votes:
            regime_votes[p] = {}
        regime_votes[p][r["regime"]] = r["cnt"]

    regime_by_period: dict[str, str] = {
        p: max(votes.keys(), key=lambda k: votes[k])
        for p, votes in regime_votes.items()
    }

    # 3. セクターペア別スプレッド集計
    pair_spreads: dict[tuple, dict[str, float]] = {}
    pair_total: dict[tuple, float] = {}
    for r in flow_rows:
        key = (r["sector_from"], r["sector_to"])
        spread = float(r["period_spread"] or 0)
        if key not in pair_spreads:
            pair_spreads[key] = {}
            pair_total[key] = 0.0
        pair_spreads[key][r["period"]] = spread
        pair_total[key] += abs(spread)

    # 上位 8 ペア
    top_pairs = sorted(pair_total.keys(), key=lambda k: pair_total[k], reverse=True)[:8]

    # 4. 流入先セクターの実績リターン集計
    sector_set = list({st for _, st in top_pairs})
    sector_avg: dict[tuple, float] = {}  # (sector, period) -> avg_return
    if sector_set:
        placeholders = ",".join("?" * len(sector_set))
        sec_rows = conn.execute(
            f"""
            SELECT {period_expr} AS period, s.sector, AVG(dp.return_rate) AS avg_return
            FROM daily_prices dp
            JOIN stocks s ON dp.code = s.code
            WHERE dp.date >= ? AND dp.return_rate IS NOT NULL
              AND s.sector IN ({placeholders})
            GROUP BY period, s.sector
            ORDER BY period
            """,
            (base_date, *sector_set),
        ).fetchall()
        for r in sec_rows:
            sector_avg[(r["sector"], r["period"])] = float(r["avg_return"] or 0)

    # 5. 累積計算してシリーズ組み立て
    series = []
    for sf, st in top_pairs:
        cum_spread = 0.0
        cum_return = 0.0
        spreads: list[float] = []
        returns: list[float] = []
        for p in all_periods:
            cum_spread += pair_spreads[(sf, st)].get(p, 0.0)
            cum_return += sector_avg.get((st, p), 0.0)
            spreads.append(round(cum_spread, 4))
            returns.append(round(cum_return, 4))
        series.append(
            {
                "label": f"{sf} → {st}",
                "sector_from": sf,
                "sector_to": st,
                "cumulative_spread": spreads,
                "sector_cumulative_return": returns,
            }
        )

    periods_out = [
        {
            "key": p,
            "start_date": period_starts.get(p, base_date),
            "regime": regime_by_period.get(p, "neutral"),
        }
        for p in all_periods
    ]

    return {"base_date": base_date, "periods": periods_out, "series": series}


@router.get("/market-pressure/timeseries")
def get_market_pressure_timeseries(
    days: int = 90,
    conn: Connection = Depends(get_connection),
):
    """
    市場圧力指標の時系列を返す (週次)。

    params:
      days: 取得期間日数 (デフォルト 90)。内部的に週次データを返す。

    レスポンス:
      dates, pl_ratio, pl_zone, buy_growth_4w, margin_ratio,
      margin_ratio_trend, signal_flags の配列 (週次)
    """
    rows = conn.execute(
        """
        SELECT mpd.date, mpd.pl_ratio, mpd.pl_zone, mpd.buy_growth_4w,
               mpd.margin_ratio, mpd.margin_ratio_trend, mpd.signal_flags
        FROM market_pressure_daily mpd
        WHERE mpd.date IN (
            SELECT week_date FROM margin_trading_weekly WHERE market_code = 'ALL'
        )
          AND mpd.date >= date('now', ? || ' days')
        ORDER BY mpd.date ASC
        """,
        (f"-{days}",),
    ).fetchall()

    if not rows:
        return {
            "dates": [],
            "pl_ratio": [],
            "pl_zone": [],
            "buy_growth_4w": [],
            "margin_ratio": [],
            "margin_ratio_trend": [],
            "signal_flags": [],
        }

    def _parse_flags(raw: Optional[str]) -> dict:
        if not raw:
            return {"credit_overheating": False}
        try:
            return json.loads(raw)
        except Exception:
            return {"credit_overheating": False}

    return {
        "dates":               [r["date"] for r in rows],
        "pl_ratio":            [r["pl_ratio"] for r in rows],
        "pl_zone":             [r["pl_zone"] or "neutral" for r in rows],
        "buy_growth_4w":       [r["buy_growth_4w"] for r in rows],
        "margin_ratio":        [r["margin_ratio"] for r in rows],
        "margin_ratio_trend":  [r["margin_ratio_trend"] for r in rows],
        "signal_flags":        [_parse_flags(r["signal_flags"]) for r in rows],
    }


def _inject_pressure_nodes(conn: Connection, result: dict) -> None:
    """
    市場圧力ノード (__pressure_bullish__ / __pressure_bearish__) を
    vis-network の nodes リストに追加する。

    最新の market_pressure_daily から pl_zone を取得して判定。
    """
    row = conn.execute(
        "SELECT pl_zone FROM market_pressure_daily ORDER BY date DESC LIMIT 1"
    ).fetchone()

    if not row:
        return

    pl_zone = row["pl_zone"] or "neutral"
    bearish_zones = {"ceiling", "overheat"}

    if pl_zone in bearish_zones:
        result["nodes"].append({
            "id": "__pressure_bearish__",
            "label": f"市場圧力\n({pl_zone})",
            "group": "market_pressure",
        })
    else:
        result["nodes"].append({
            "id": "__pressure_bullish__",
            "label": f"市場圧力\n({pl_zone})",
            "group": "market_pressure",
        })


def _parse_period(period: str) -> int:
    """'20d' → 20、'60d' → 60 のように変換する。"""
    return int(period.rstrip("d"))


def _build_vis_network(
    rows,
    edge_value_col: str,
    directed: bool,
    extra_cols: list[str] | None = None,
) -> dict:
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
        if extra_cols:
            for col in extra_cols:
                v = row.get(col)
                if v is not None:
                    edge[col] = round(v, 4) if isinstance(v, float) else v
        if directed:
            edge["arrows"] = "to"
        edges.append(edge)

    return {"nodes": list(nodes.values()), "edges": edges}
