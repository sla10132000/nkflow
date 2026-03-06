"""graph.py のテスト"""
import os
import sqlite3
import sys
from datetime import date

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scripts.init_sqlite import init_sqlite

CALC_DATE = "2025-01-06"
STOCKS = [
    ("7203", "トヨタ自動車", "輸送用機器"),
    ("6758", "ソニーグループ", "電気機器"),
    ("6902", "デンソー", "輸送用機器"),
]


# ─────────────────────────────────────────────────────────────────────────────
# フィクスチャ
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def db_path(tmp_path):
    """スキーマ+基本データ挿入済みの SQLite パス"""
    path = str(tmp_path / "test.db")
    init_sqlite(path)

    conn = sqlite3.connect(path)
    conn.executemany("INSERT INTO stocks VALUES (?,?,?)", STOCKS)

    # daily_summary (TradingDay ノード用)
    conn.execute(
        "INSERT INTO daily_summary (date, nikkei_close, nikkei_return, regime) "
        "VALUES (?, ?, ?, ?)",
        (CALC_DATE, 39000.0, 0.01, "risk_on"),
    )

    # daily_prices (TRADED_ON エッジ用)
    prices = [
        ("7203", CALC_DATE, 3000, 3050, 2980, 3020, 5000000, 0.03, 70, 0.023, 0.02),
        ("6758", CALC_DATE, 2500, 2540, 2480, 2510, 3000000, -0.01, 60, 0.024, -0.02),
        ("6902", CALC_DATE, 1800, 1830, 1790, 1810, 2000000, 0.015, 40, 0.022, 0.005),
    ]
    conn.executemany(
        "INSERT INTO daily_prices "
        "(code,date,open,high,low,close,volume,return_rate,price_range,range_pct,relative_strength) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        prices,
    )

    # graph_causality (GRANGER_CAUSES エッジ用)
    conn.executemany(
        "INSERT INTO graph_causality "
        "(source,target,lag_days,p_value,f_stat,period,calc_date) VALUES (?,?,?,?,?,?,?)",
        [
            ("7203", "6758", 2, 0.01, 8.5, "60d", CALC_DATE),
            ("6758", "6902", 1, 0.03, 5.2, "60d", CALC_DATE),
        ],
    )

    # graph_correlations (CORRELATED エッジ用)
    conn.executemany(
        "INSERT INTO graph_correlations "
        "(stock_a,stock_b,coefficient,period,calc_date) VALUES (?,?,?,?,?)",
        [
            ("6758", "7203", 0.85, "20d", CALC_DATE),
            ("6902", "7203", 0.72, "20d", CALC_DATE),
            ("6758", "6902", 0.65, "20d", CALC_DATE),
        ],
    )

    # graph_fund_flows (FUND_FLOW エッジ用)
    conn.execute(
        "INSERT INTO graph_fund_flows "
        "(sector_from,sector_to,volume_delta,return_spread,date) VALUES (?,?,?,?,?)",
        ("輸送用機器", "電気機器", -0.15, 0.03, CALC_DATE),
    )

    conn.commit()
    conn.close()
    return path


@pytest.fixture
def kuzu_path(tmp_path):
    """KùzuDB の新規パス (存在しない)"""
    return str(tmp_path / "kuzu_db")


# ─────────────────────────────────────────────────────────────────────────────
# open_kuzu / _ensure_schema
# ─────────────────────────────────────────────────────────────────────────────

class TestOpenKuzu:
    def test_creates_new_db(self, kuzu_path):
        from src.graph.kuzu import open_kuzu
        db, conn = open_kuzu(kuzu_path)
        assert os.path.exists(kuzu_path)

    def test_opens_existing_db(self, kuzu_path):
        from src.graph.kuzu import open_kuzu
        open_kuzu(kuzu_path)     # 1回目 (作成)
        db2, conn2 = open_kuzu(kuzu_path)  # 2回目 (再オープン) でエラーにならない
        # ノードが追加できれば正常
        conn2.execute("MERGE (s:Stock {code: 'TEST'}) SET s.name='T', s.sector='X', s.market_cap_tier='large', s.community_id=-1")


# ─────────────────────────────────────────────────────────────────────────────
# load_nodes
# ─────────────────────────────────────────────────────────────────────────────

class TestLoadNodes:
    def test_loads_stock_nodes(self, db_path, kuzu_path):
        from src.graph.kuzu import open_kuzu, load_nodes

        _, conn = open_kuzu(kuzu_path)
        conn_sqlite = sqlite3.connect(db_path)
        load_nodes(conn, conn_sqlite)
        conn_sqlite.close()

        r = conn.execute("MATCH (s:Stock) RETURN s.code ORDER BY s.code")
        codes = set(r.get_as_df()["s.code"].tolist())
        assert codes == {"7203", "6758", "6902"}

    def test_loads_sector_nodes(self, db_path, kuzu_path):
        from src.graph.kuzu import open_kuzu, load_nodes

        _, conn = open_kuzu(kuzu_path)
        conn_sqlite = sqlite3.connect(db_path)
        load_nodes(conn, conn_sqlite)
        conn_sqlite.close()

        r = conn.execute("MATCH (sec:Sector) RETURN sec.name")
        names = set(r.get_as_df()["sec.name"].tolist())
        assert "輸送用機器" in names
        assert "電気機器" in names

    def test_loads_belongs_to_edges(self, db_path, kuzu_path):
        from src.graph.kuzu import open_kuzu, load_nodes

        _, conn = open_kuzu(kuzu_path)
        conn_sqlite = sqlite3.connect(db_path)
        load_nodes(conn, conn_sqlite)
        conn_sqlite.close()

        r = conn.execute("MATCH ()-[r:BELONGS_TO]->() RETURN count(r) AS n")
        assert r.get_as_df()["n"].iloc[0] == 3

    def test_load_nodes_idempotent(self, db_path, kuzu_path):
        """2回実行しても BELONGS_TO エッジが重複しない"""
        from src.graph.kuzu import open_kuzu, load_nodes

        _, conn = open_kuzu(kuzu_path)
        conn_sqlite = sqlite3.connect(db_path)
        load_nodes(conn, conn_sqlite)
        load_nodes(conn, conn_sqlite)
        conn_sqlite.close()

        r = conn.execute("MATCH ()-[r:BELONGS_TO]->() RETURN count(r) AS n")
        assert r.get_as_df()["n"].iloc[0] == 3


# ─────────────────────────────────────────────────────────────────────────────
# load_edges
# ─────────────────────────────────────────────────────────────────────────────

class TestLoadEdges:
    def _setup(self, db_path, kuzu_path):
        from src.graph.kuzu import open_kuzu, load_nodes
        _, conn = open_kuzu(kuzu_path)
        conn_sqlite = sqlite3.connect(db_path)
        load_nodes(conn, conn_sqlite)
        return conn, conn_sqlite

    def test_loads_granger_causes(self, db_path, kuzu_path):
        from src.graph.kuzu import load_edges
        conn, conn_sqlite = self._setup(db_path, kuzu_path)
        counts = load_edges(conn, conn_sqlite, CALC_DATE)
        conn_sqlite.close()

        assert counts["granger"] == 2
        r = conn.execute("MATCH ()-[r:GRANGER_CAUSES]->() RETURN count(r) AS n")
        assert r.get_as_df()["n"].iloc[0] == 2

    def test_loads_correlated(self, db_path, kuzu_path):
        from src.graph.kuzu import load_edges
        conn, conn_sqlite = self._setup(db_path, kuzu_path)
        load_edges(conn, conn_sqlite, CALC_DATE)
        conn_sqlite.close()

        r = conn.execute("MATCH ()-[r:CORRELATED]->() RETURN count(r) AS n")
        assert r.get_as_df()["n"].iloc[0] == 3

    def test_loads_fund_flow(self, db_path, kuzu_path):
        from src.graph.kuzu import load_edges
        conn, conn_sqlite = self._setup(db_path, kuzu_path)
        load_edges(conn, conn_sqlite, CALC_DATE)
        conn_sqlite.close()

        r = conn.execute("MATCH ()-[r:FUND_FLOW]->() RETURN count(r) AS n")
        assert r.get_as_df()["n"].iloc[0] == 1

    def test_loads_traded_on(self, db_path, kuzu_path):
        from src.graph.kuzu import load_edges
        conn, conn_sqlite = self._setup(db_path, kuzu_path)
        load_edges(conn, conn_sqlite, CALC_DATE)
        conn_sqlite.close()

        r = conn.execute("MATCH ()-[r:TRADED_ON]->() RETURN count(r) AS n")
        assert r.get_as_df()["n"].iloc[0] == 3


# ─────────────────────────────────────────────────────────────────────────────
# query_causality_chains
# ─────────────────────────────────────────────────────────────────────────────

class TestQueryCausalityChains:
    def _setup(self, db_path, kuzu_path):
        from src.graph.kuzu import open_kuzu, load_nodes, load_edges
        _, conn = open_kuzu(kuzu_path)
        conn_sqlite = sqlite3.connect(db_path)
        load_nodes(conn, conn_sqlite)
        load_edges(conn, conn_sqlite, CALC_DATE)
        conn_sqlite.close()
        return conn

    def test_detects_1hop_chain(self, db_path, kuzu_path):
        from src.graph.kuzu import query_causality_chains
        conn = self._setup(db_path, kuzu_path)

        chains = query_causality_chains(conn, CALC_DATE)

        leaders = [c["leader"] for c in chains]
        assert "7203" in leaders

    def test_detects_2hop_chain(self, db_path, kuzu_path):
        """7203 → 6758 → 6902 の 2ホップ連鎖を検出"""
        from src.graph.kuzu import query_causality_chains
        conn = self._setup(db_path, kuzu_path)

        chains = query_causality_chains(conn, CALC_DATE)
        two_hop = [c for c in chains if c["hops"] == 2]

        assert any(c["leader"] == "7203" and c["follower"] == "6902" for c in two_hop)

    def test_returns_lag_total(self, db_path, kuzu_path):
        """2ホップチェーンの lag_total は各ラグの合計"""
        from src.graph.kuzu import query_causality_chains
        conn = self._setup(db_path, kuzu_path)

        chains = query_causality_chains(conn, CALC_DATE)
        two_hop = next((c for c in chains if c["hops"] == 2 and c["leader"] == "7203"), None)

        assert two_hop is not None
        assert two_hop["lag_total"] == 3  # lag=2 + lag=1


# ─────────────────────────────────────────────────────────────────────────────
# detect_communities
# ─────────────────────────────────────────────────────────────────────────────

class TestDetectCommunities:
    def _setup(self, db_path, kuzu_path):
        from src.graph.kuzu import open_kuzu, load_nodes, load_edges
        _, conn = open_kuzu(kuzu_path)
        conn_sqlite = sqlite3.connect(db_path)
        load_nodes(conn, conn_sqlite)
        load_edges(conn, conn_sqlite, CALC_DATE)
        return conn, conn_sqlite

    def test_assigns_community_ids(self, db_path, kuzu_path):
        from src.graph.kuzu import detect_communities
        conn, conn_sqlite = self._setup(db_path, kuzu_path)

        n = detect_communities(conn, conn_sqlite, CALC_DATE)
        conn_sqlite.close()

        assert n == 3  # 3銘柄が割り当て済み

    def test_writes_to_sqlite(self, db_path, kuzu_path):
        from src.graph.kuzu import detect_communities
        conn, conn_sqlite = self._setup(db_path, kuzu_path)
        detect_communities(conn, conn_sqlite, CALC_DATE)

        rows = conn_sqlite.execute(
            "SELECT code, community_id FROM graph_communities WHERE calc_date = ?",
            (CALC_DATE,),
        ).fetchall()
        conn_sqlite.close()

        assert len(rows) == 3
        assert all(r[1] >= 0 for r in rows)

    def test_writes_to_kuzu(self, db_path, kuzu_path):
        from src.graph.kuzu import detect_communities
        conn, conn_sqlite = self._setup(db_path, kuzu_path)
        detect_communities(conn, conn_sqlite, CALC_DATE)
        conn_sqlite.close()

        r = conn.execute(
            "MATCH (s:Stock) WHERE s.community_id >= 0 RETURN count(s) AS n"
        )
        assert r.get_as_df()["n"].iloc[0] == 3

    def test_no_correlated_edges_returns_zero(self, kuzu_path, tmp_path):
        from src.graph.kuzu import open_kuzu, detect_communities

        db_path_empty = str(tmp_path / "empty.db")
        init_sqlite(db_path_empty)

        _, conn = open_kuzu(kuzu_path)
        conn_sqlite = sqlite3.connect(db_path_empty)

        result = detect_communities(conn, conn_sqlite, CALC_DATE)
        conn_sqlite.close()

        assert result == 0


# ─────────────────────────────────────────────────────────────────────────────
# query_fund_flow_paths
# ─────────────────────────────────────────────────────────────────────────────

class TestQueryFundFlowPaths:
    def test_returns_fund_flow_path(self, db_path, kuzu_path):
        from src.graph.kuzu import open_kuzu, load_nodes, load_edges, query_fund_flow_paths

        _, conn = open_kuzu(kuzu_path)
        conn_sqlite = sqlite3.connect(db_path)
        load_nodes(conn, conn_sqlite)
        load_edges(conn, conn_sqlite, CALC_DATE)
        conn_sqlite.close()

        paths = query_fund_flow_paths(conn, CALC_DATE)

        assert len(paths) >= 1
        assert any(p["src"] == "輸送用機器" and p["dst"] == "電気機器" for p in paths)


# ─────────────────────────────────────────────────────────────────────────────
# update_and_query (統合)
# ─────────────────────────────────────────────────────────────────────────────

class TestUpdateAndQuery:
    def test_returns_all_keys(self, db_path, kuzu_path):
        from src.graph.kuzu import update_and_query

        result = update_and_query(kuzu_path, db_path, CALC_DATE)

        assert "chains" in result
        assert "fund_flow_paths" in result
        assert "regime_perf" in result

    def test_chains_detected(self, db_path, kuzu_path):
        from src.graph.kuzu import update_and_query

        result = update_and_query(kuzu_path, db_path, CALC_DATE)
        assert len(result["chains"]) > 0

    def test_communities_saved_to_sqlite(self, db_path, kuzu_path):
        from src.graph.kuzu import update_and_query

        update_and_query(kuzu_path, db_path, CALC_DATE)

        conn = sqlite3.connect(db_path)
        rows = conn.execute(
            "SELECT COUNT(*) FROM graph_communities WHERE calc_date = ?", (CALC_DATE,)
        ).fetchone()
        conn.close()
        assert rows[0] == 3
