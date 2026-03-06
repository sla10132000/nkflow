"""KùzuDB グラフ構築・探索モジュール"""
import logging
import os
import sqlite3
from datetime import date, timedelta
from typing import Any, Optional

import kuzu
import networkx as nx
import pandas as pd

from src.config import COMMUNITY_RESOLUTION, GRANGER_P_THRESHOLD

logger = logging.getLogger(__name__)

# 古いエッジを保持する最大日数
EDGE_RETENTION_DAYS = 90


# ─────────────────────────────────────────────────────────────────────────────
# 接続管理
# ─────────────────────────────────────────────────────────────────────────────

def open_kuzu(kuzu_path: str) -> tuple[kuzu.Database, kuzu.Connection]:
    """
    KùzuDB を開いてスキーマを初期化する。

    kuzu_path が存在しない場合はディレクトリと共に新規作成する。
    既存の場合はそのまま開く (スキーマの CREATE ... IF NOT EXISTS は冪等)。
    """
    os.makedirs(os.path.dirname(kuzu_path) if os.path.dirname(kuzu_path) else ".", exist_ok=True)

    db = kuzu.Database(kuzu_path)
    conn = kuzu.Connection(db)
    _ensure_schema(conn)
    return db, conn


def _ensure_schema(conn: kuzu.Connection) -> None:
    """テーブルが存在しない場合のみ CREATE する (冪等)"""
    ddls = [
        # ノード
        "CREATE NODE TABLE IF NOT EXISTS Stock(code STRING, name STRING, sector STRING, market_cap_tier STRING, community_id INT64, PRIMARY KEY(code))",
        "CREATE NODE TABLE IF NOT EXISTS Sector(name STRING, PRIMARY KEY(name))",
        "CREATE NODE TABLE IF NOT EXISTS TradingDay(date DATE, nikkei_close DOUBLE, nikkei_return DOUBLE, regime STRING, PRIMARY KEY(date))",
        # エッジ
        "CREATE REL TABLE IF NOT EXISTS BELONGS_TO(FROM Stock TO Sector)",
        "CREATE REL TABLE IF NOT EXISTS CORRELATED(FROM Stock TO Stock, coefficient DOUBLE, period STRING, calc_date DATE)",
        "CREATE REL TABLE IF NOT EXISTS GRANGER_CAUSES(FROM Stock TO Stock, lag_days INT64, p_value DOUBLE, f_stat DOUBLE, period STRING, calc_date DATE)",
        "CREATE REL TABLE IF NOT EXISTS LEADS(FROM Stock TO Stock, lag_days INT64, cross_corr DOUBLE, period STRING, calc_date DATE)",
        "CREATE REL TABLE IF NOT EXISTS FUND_FLOW(FROM Sector TO Sector, direction STRING, volume_delta DOUBLE, return_spread DOUBLE, date DATE)",
        "CREATE REL TABLE IF NOT EXISTS TRADED_ON(FROM Stock TO TradingDay, return_rate DOUBLE, price_range DOUBLE, volume INT64, relative_strength DOUBLE)",
    ]
    for ddl in ddls:
        conn.execute(ddl)


# ─────────────────────────────────────────────────────────────────────────────
# グラフ更新
# ─────────────────────────────────────────────────────────────────────────────

def load_nodes(conn: kuzu.Connection, conn_sqlite: sqlite3.Connection) -> None:
    """
    SQLite の stocks / daily_summary → KùzuDB ノードを MERGE で更新する。
    - Stock ノード
    - Sector ノード
    - TradingDay ノード
    - BELONGS_TO エッジ (全削除+再作成で冪等)
    """
    stocks_df = pd.read_sql("SELECT code, name, sector FROM stocks", conn_sqlite)

    for row in stocks_df.itertuples(index=False):
        conn.execute(
            "MERGE (s:Stock {code: $code}) "
            "SET s.name=$name, s.sector=$sector, s.market_cap_tier='large', s.community_id=-1",
            {"code": row.code, "name": row.name, "sector": row.sector},
        )

    sectors = stocks_df["sector"].dropna().unique().tolist()
    for sector in sectors:
        conn.execute("MERGE (sec:Sector {name: $name})", {"name": sector})

    # BELONGS_TO: 全削除して再作成 (冪等)
    conn.execute("MATCH ()-[r:BELONGS_TO]->() DELETE r")
    for row in stocks_df.itertuples(index=False):
        if row.sector:
            conn.execute(
                "MATCH (s:Stock {code: $code}), (sec:Sector {name: $sector}) "
                "CREATE (s)-[:BELONGS_TO]->(sec)",
                {"code": row.code, "sector": row.sector},
            )

    # TradingDay
    summary_df = pd.read_sql(
        "SELECT date, nikkei_close, nikkei_return, regime FROM daily_summary",
        conn_sqlite,
    )
    for row in summary_df.itertuples(index=False):
        conn.execute(
            "MERGE (t:TradingDay {date: date($date)}) "
            "SET t.nikkei_return=$nr, t.regime=$regime",
            {
                "date": row.date,
                "nr": float(row.nikkei_return) if row.nikkei_return is not None else 0.0,
                "regime": row.regime if row.regime else "neutral",
            },
        )

    logger.info(f"ノード更新: {len(stocks_df)} 銘柄, {len(sectors)} セクター")


def load_edges(
    conn: kuzu.Connection,
    conn_sqlite: sqlite3.Connection,
    calc_date: str,
) -> dict[str, int]:
    """
    SQLite の graph_* テーブル → KùzuDB エッジを更新する。

    - 保持期限 (EDGE_RETENTION_DAYS) を超えた古いエッジを削除
    - 当日分のエッジを新規 CREATE

    Returns:
        {"granger": n, "correlated": n, "leads": n, "fund_flow": n, "traded_on": n}
    """
    cutoff = (
        date.fromisoformat(calc_date) - timedelta(days=EDGE_RETENTION_DAYS)
    ).isoformat()

    counts: dict[str, int] = {}

    # ── GRANGER_CAUSES ────────────────────────────────────────────
    conn.execute(
        f"MATCH ()-[r:GRANGER_CAUSES]->() WHERE r.calc_date < date('{cutoff}') DELETE r"
    )
    gc_df = pd.read_sql(
        f"SELECT source, target, lag_days, p_value, f_stat, period, calc_date "
        f"FROM graph_causality WHERE calc_date = '{calc_date}'",
        conn_sqlite,
    )
    for row in gc_df.itertuples(index=False):
        conn.execute(
            "MATCH (a:Stock {code: $src}), (b:Stock {code: $tgt}) "
            "CREATE (a)-[:GRANGER_CAUSES {"
            "lag_days: $lag, p_value: $pv, f_stat: $fs, period: $period, calc_date: date($cd)"
            "}]->(b)",
            {"src": row.source, "tgt": row.target, "lag": int(row.lag_days),
             "pv": float(row.p_value), "fs": float(row.f_stat),
             "period": row.period, "cd": row.calc_date},
        )
    counts["granger"] = len(gc_df)

    # ── CORRELATED ────────────────────────────────────────────────
    conn.execute(
        f"MATCH ()-[r:CORRELATED]->() WHERE r.calc_date < date('{cutoff}') DELETE r"
    )
    corr_df = pd.read_sql(
        f"SELECT stock_a, stock_b, coefficient, period, calc_date "
        f"FROM graph_correlations WHERE calc_date = '{calc_date}'",
        conn_sqlite,
    )
    for row in corr_df.itertuples(index=False):
        conn.execute(
            "MATCH (a:Stock {code: $a}), (b:Stock {code: $b}) "
            "CREATE (a)-[:CORRELATED {coefficient: $coef, period: $period, calc_date: date($cd)}]->(b)",
            {"a": row.stock_a, "b": row.stock_b,
             "coef": float(row.coefficient), "period": row.period, "cd": row.calc_date},
        )
    counts["correlated"] = len(corr_df)

    # ── FUND_FLOW ─────────────────────────────────────────────────
    conn.execute(
        f"MATCH ()-[r:FUND_FLOW]->() WHERE r.date < date('{cutoff}') DELETE r"
    )
    ff_df = pd.read_sql(
        f"SELECT sector_from, sector_to, volume_delta, return_spread, date "
        f"FROM graph_fund_flows WHERE date = '{calc_date}'",
        conn_sqlite,
    )
    for row in ff_df.itertuples(index=False):
        conn.execute(
            "MATCH (a:Sector {name: $src}), (b:Sector {name: $tgt}) "
            "CREATE (a)-[:FUND_FLOW {direction: 'outflow_to_inflow', "
            "volume_delta: $vd, return_spread: $rs, date: date($date)}]->(b)",
            {"src": row.sector_from, "tgt": row.sector_to,
             "vd": float(row.volume_delta or 0), "rs": float(row.return_spread or 0),
             "date": row.date},
        )
    counts["fund_flow"] = len(ff_df)

    # ── TRADED_ON ─────────────────────────────────────────────────
    traded_df = pd.read_sql(
        f"SELECT code, date, return_rate, price_range, volume, relative_strength "
        f"FROM daily_prices WHERE date = '{calc_date}' AND return_rate IS NOT NULL",
        conn_sqlite,
    )
    for row in traded_df.itertuples(index=False):
        conn.execute(
            "MATCH (s:Stock {code: $code}), (t:TradingDay {date: date($date)}) "
            "CREATE (s)-[:TRADED_ON {return_rate: $rr, price_range: $pr, "
            "volume: $vol, relative_strength: $rs}]->(t)",
            {"code": row.code, "date": row.date,
             "rr": float(row.return_rate or 0),
             "pr": float(row.price_range or 0),
             "vol": int(row.volume or 0),
             "rs": float(row.relative_strength or 0)},
        )
    counts["traded_on"] = len(traded_df)

    logger.info(f"エッジ更新: {counts}")
    return counts


# ─────────────────────────────────────────────────────────────────────────────
# グラフ探索
# ─────────────────────────────────────────────────────────────────────────────

def query_causality_chains(
    conn: kuzu.Connection,
    calc_date: str,
    max_hops: int = 3,
) -> list[dict[str, Any]]:
    """
    グレンジャー因果の連鎖を探索する。

    MATCH path = (leader)-[:GRANGER_CAUSES*1..3]->(follower)
    WHERE 全エッジの p_value < threshold

    より確実に動作するよう 1-hop, 2-hop, 3-hop を個別クエリで実行する。

    Returns:
        [{"leader": code, "follower": code, "hops": n, "lag_total": n}, ...]
    """
    chains = []

    # 1-hop
    r = conn.execute(
        "MATCH (a:Stock)-[r:GRANGER_CAUSES]->(b:Stock) "
        f"WHERE r.p_value < {GRANGER_P_THRESHOLD} AND r.calc_date = date('{calc_date}') "
        "RETURN a.code AS leader, b.code AS follower, r.lag_days AS lag_total, 1 AS hops"
    )
    chains.extend(r.get_as_df().to_dict("records"))

    # 2-hop
    r = conn.execute(
        "MATCH (a:Stock)-[r1:GRANGER_CAUSES]->(m:Stock)-[r2:GRANGER_CAUSES]->(b:Stock) "
        f"WHERE r1.p_value < {GRANGER_P_THRESHOLD} AND r2.p_value < {GRANGER_P_THRESHOLD} "
        f"AND r1.calc_date = date('{calc_date}') AND r2.calc_date = date('{calc_date}') "
        "AND a.code <> b.code AND a.code <> m.code "
        "RETURN a.code AS leader, b.code AS follower, "
        "r1.lag_days + r2.lag_days AS lag_total, 2 AS hops"
    )
    chains.extend(r.get_as_df().to_dict("records"))

    if max_hops >= 3:
        r = conn.execute(
            "MATCH (a:Stock)-[r1:GRANGER_CAUSES]->(m1:Stock)-[r2:GRANGER_CAUSES]->(m2:Stock)"
            "-[r3:GRANGER_CAUSES]->(b:Stock) "
            f"WHERE r1.p_value < {GRANGER_P_THRESHOLD} AND r2.p_value < {GRANGER_P_THRESHOLD} "
            f"AND r3.p_value < {GRANGER_P_THRESHOLD} "
            f"AND r1.calc_date = date('{calc_date}') "
            "AND a.code <> b.code AND a.code <> m1.code AND m1.code <> m2.code "
            "RETURN a.code AS leader, b.code AS follower, "
            "r1.lag_days + r2.lag_days + r3.lag_days AS lag_total, 3 AS hops"
        )
        chains.extend(r.get_as_df().to_dict("records"))

    logger.info(f"因果連鎖: {len(chains)} 件")
    return chains


def query_fund_flow_paths(conn: kuzu.Connection, target_date: str) -> list[dict[str, Any]]:
    """
    セクター間の資金フロー経路を探索する (1〜2ホップ)。

    Returns:
        [{"from": sector, "to": sector, "hops": n, "volume_delta": f}, ...]
    """
    paths = []

    r = conn.execute(
        f"MATCH (a:Sector)-[f:FUND_FLOW]->(b:Sector) "
        f"WHERE f.date = date('{target_date}') "
        "RETURN a.name AS src, b.name AS dst, f.volume_delta AS vd, 1 AS hops"
    )
    paths.extend(r.get_as_df().to_dict("records"))

    r = conn.execute(
        f"MATCH (a:Sector)-[f1:FUND_FLOW]->(m:Sector)-[f2:FUND_FLOW]->(b:Sector) "
        f"WHERE f1.date = date('{target_date}') AND f2.date = date('{target_date}') "
        "AND a.name <> b.name "
        "RETURN a.name AS src, b.name AS dst, f1.volume_delta + f2.volume_delta AS vd, 2 AS hops"
    )
    paths.extend(r.get_as_df().to_dict("records"))

    logger.info(f"資金フロー経路: {len(paths)} 件")
    return paths


def detect_communities(
    conn: kuzu.Connection,
    conn_sqlite: sqlite3.Connection,
    calc_date: str,
) -> int:
    """
    CORRELATED エッジから networkx グラフを構築して Louvain コミュニティ検出を実行する。
    結果を KùzuDB Stock.community_id と SQLite graph_communities に書き戻す。

    Returns:
        コミュニティに割り当てた銘柄数
    """
    r = conn.execute(
        f"MATCH (a:Stock)-[r:CORRELATED]->(b:Stock) "
        f"WHERE r.calc_date = date('{calc_date}') "
        "RETURN a.code AS a, b.code AS b, r.coefficient AS coef"
    )
    df = r.get_as_df()

    if df.empty:
        logger.info("コミュニティ検出: CORRELATEDエッジなし")
        return 0

    G = nx.Graph()
    for row in df.itertuples(index=False):
        G.add_edge(row.a, row.b, weight=abs(row.coef))

    communities = list(
        nx.community.louvain_communities(G, seed=42, resolution=COMMUNITY_RESOLUTION)
    )

    node_to_community: dict[str, int] = {}
    for i, community in enumerate(communities):
        for code in community:
            node_to_community[code] = i

    # KùzuDB に書き戻し
    for code, community_id in node_to_community.items():
        conn.execute(
            "MATCH (s:Stock {code: $code}) SET s.community_id = $cid",
            {"code": code, "cid": community_id},
        )

    # SQLite に書き戻し
    rows = [
        (code, comm_id, calc_date)
        for code, comm_id in node_to_community.items()
    ]
    conn_sqlite.executemany(
        "INSERT OR REPLACE INTO graph_communities (code, community_id, calc_date) VALUES (?, ?, ?)",
        rows,
    )
    conn_sqlite.commit()

    logger.info(f"コミュニティ検出: {len(communities)} クラスター, {len(node_to_community)} 銘柄")
    return len(node_to_community)


def query_regime_performance(
    conn: kuzu.Connection,
    conn_sqlite: sqlite3.Connection,
    target_date: str,
    top_n: int = 20,
) -> dict[str, list[dict]]:
    """
    マーケットレジーム別にアウトパフォームした銘柄を集計して返す。

    Returns:
        {"risk_on": [...], "risk_off": [...]}  各リストは [{code, avg_rs}, ...]
    """
    result = {}
    for regime in ("risk_on", "risk_off"):
        r = conn.execute(
            "MATCH (s:Stock)-[tr:TRADED_ON]->(td:TradingDay) "
            f"WHERE td.regime = '{regime}' "
            "RETURN s.code AS code, AVG(tr.relative_strength) AS avg_rs "
            "ORDER BY avg_rs DESC "
            f"LIMIT {top_n}"
        )
        result[regime] = r.get_as_df().to_dict("records")

    logger.info(f"レジーム別パフォーマンス: risk_on={len(result.get('risk_on',[]))}, "
                f"risk_off={len(result.get('risk_off',[]))}")
    return result


# ─────────────────────────────────────────────────────────────────────────────
# エントリポイント
# ─────────────────────────────────────────────────────────────────────────────

def update_and_query(
    kuzu_path: str,
    db_path: str,
    target_date: Optional[str] = None,
) -> dict[str, Any]:
    """
    グラフ更新・探索の全処理を実行する。

    実行順序:
      1. ノード更新 (Stock, Sector, TradingDay)
      2. エッジ更新 (GRANGER_CAUSES, CORRELATED, FUND_FLOW, TRADED_ON)
      3. コミュニティ検出 → SQLite/KùzuDB 書き戻し
      4. 因果連鎖探索
      5. 資金フロー経路探索
      6. レジーム別パフォーマンス集計

    Returns:
        {"chains": [...], "fund_flow_paths": [...], "regime_perf": {...}}
    """
    if target_date is None:
        target_date = date.today().isoformat()

    logger.info(f"=== update_and_query 開始: {target_date} ===")

    _, conn = open_kuzu(kuzu_path)
    conn_sqlite = sqlite3.connect(db_path)

    try:
        load_nodes(conn, conn_sqlite)
        edge_counts = load_edges(conn, conn_sqlite, target_date)
        logger.info(f"エッジ: {edge_counts}")

        n_comm = detect_communities(conn, conn_sqlite, target_date)
        logger.info(f"コミュニティ: {n_comm} 銘柄")

        chains = query_causality_chains(conn, target_date)
        ff_paths = query_fund_flow_paths(conn, target_date)
        regime_perf = query_regime_performance(conn, conn_sqlite, target_date)
    finally:
        conn_sqlite.close()

    logger.info("=== update_and_query 完了 ===")
    return {
        "chains": chains,
        "fund_flow_paths": ff_paths,
        "regime_perf": regime_perf,
    }
