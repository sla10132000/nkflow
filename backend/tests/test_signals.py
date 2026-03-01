"""signals.py のテスト"""
import json
import os
import sqlite3
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scripts.init_sqlite import init_sqlite

TARGET_DATE = "2025-01-06"
PREV_DATE   = "2025-01-05"

STOCKS = [
    ("7203", "トヨタ自動車", "輸送用機器"),
    ("6758", "ソニーグループ", "電気機器"),
    ("6902", "デンソー",      "輸送用機器"),
    ("9984", "ソフトバンク",  "情報・通信"),
]


# ─────────────────────────────────────────────────────────────────────────────
# ヘルパー
# ─────────────────────────────────────────────────────────────────────────────

def _make_db(tmp_path, extra_setup=None) -> tuple[str, sqlite3.Connection]:
    """スキーマ初期化済み DB を作り、接続を返す"""
    path = str(tmp_path / "test.db")
    init_sqlite(path)
    conn = sqlite3.connect(path)
    conn.executemany("INSERT INTO stocks VALUES (?,?,?)", STOCKS)
    if extra_setup:
        extra_setup(conn)
    conn.commit()
    return path, conn


def _insert_price(conn, code, date_, return_rate, relative_strength=None):
    conn.execute(
        "INSERT OR REPLACE INTO daily_prices "
        "(code,date,open,high,low,close,volume,return_rate,price_range,range_pct,relative_strength) "
        "VALUES (?,?,1000,1010,990,1000,1000000,?,20,0.02,?)",
        (code, date_, return_rate, relative_strength),
    )


def _fetch_signals(conn, signal_type=None, date_=TARGET_DATE):
    q = "SELECT signal_type, code, direction, confidence, reasoning FROM signals WHERE date=?"
    params = [date_]
    if signal_type:
        q += " AND signal_type=?"
        params.append(signal_type)
    return conn.execute(q, params).fetchall()


# ─────────────────────────────────────────────────────────────────────────────
# generate_causality_chain_signals
# ─────────────────────────────────────────────────────────────────────────────

class TestCausalityChain:
    def _setup(self, tmp_path):
        path, conn = _make_db(tmp_path)
        # トリガー銘柄 (|return_rate| > 0.02)
        _insert_price(conn, "7203", TARGET_DATE, 0.035)
        _insert_price(conn, "6758", TARGET_DATE, 0.005)
        _insert_price(conn, "6902", TARGET_DATE, 0.008)

        # graph_causality (7203 → 6758)
        conn.execute(
            "INSERT INTO graph_causality (source,target,lag_days,p_value,f_stat,period,calc_date) "
            "VALUES ('7203','6758',2,0.02,7.5,'60d',?)", (TARGET_DATE,)
        )
        conn.commit()
        return path, conn

    def test_generates_signal_for_follower(self, tmp_path):
        from src.batch.signals import generate_causality_chain_signals
        path, conn = self._setup(tmp_path)

        chains = [{"leader": "7203", "follower": "6758", "lag_total": 2, "hops": 1}]
        n = generate_causality_chain_signals(conn, TARGET_DATE, chains)

        assert n == 1
        rows = _fetch_signals(conn, "causality_chain")
        assert len(rows) == 1
        assert rows[0][1] == "6758"
        assert rows[0][2] == "bullish"

    def test_direction_bearish_when_trigger_falls(self, tmp_path):
        path, conn = _make_db(tmp_path)
        _insert_price(conn, "7203", TARGET_DATE, -0.03)
        _insert_price(conn, "6758", TARGET_DATE, -0.005)
        conn.execute(
            "INSERT INTO graph_causality (source,target,lag_days,p_value,f_stat,period,calc_date) "
            "VALUES ('7203','6758',1,0.01,9.0,'60d',?)", (TARGET_DATE,)
        )
        conn.commit()

        from src.batch.signals import generate_causality_chain_signals
        chains = [{"leader": "7203", "follower": "6758", "lag_total": 1, "hops": 1}]
        generate_causality_chain_signals(conn, TARGET_DATE, chains)

        rows = _fetch_signals(conn, "causality_chain")
        assert rows[0][2] == "bearish"

    def test_confidence_is_1_minus_pvalue(self, tmp_path):
        path, conn = self._setup(tmp_path)
        from src.batch.signals import generate_causality_chain_signals
        chains = [{"leader": "7203", "follower": "6758", "lag_total": 2, "hops": 1}]
        generate_causality_chain_signals(conn, TARGET_DATE, chains)

        rows = _fetch_signals(conn, "causality_chain")
        assert abs(rows[0][3] - (1.0 - 0.02)) < 1e-4  # confidence = 1 - p_value

    def test_non_trigger_leader_skipped(self, tmp_path):
        """|return_rate| <= 0.02 のトリガーはスキップ"""
        path, conn = _make_db(tmp_path)
        _insert_price(conn, "7203", TARGET_DATE, 0.01)  # 閾値未満
        _insert_price(conn, "6758", TARGET_DATE, 0.005)
        conn.commit()

        from src.batch.signals import generate_causality_chain_signals
        chains = [{"leader": "7203", "follower": "6758", "lag_total": 1, "hops": 1}]
        n = generate_causality_chain_signals(conn, TARGET_DATE, chains)
        assert n == 0

    def test_empty_chains_returns_zero(self, tmp_path):
        path, conn = _make_db(tmp_path)
        from src.batch.signals import generate_causality_chain_signals
        assert generate_causality_chain_signals(conn, TARGET_DATE, []) == 0

    def test_reasoning_contains_chain_info(self, tmp_path):
        path, conn = self._setup(tmp_path)
        from src.batch.signals import generate_causality_chain_signals
        chains = [{"leader": "7203", "follower": "6758", "lag_total": 2, "hops": 1}]
        generate_causality_chain_signals(conn, TARGET_DATE, chains)

        rows = _fetch_signals(conn, "causality_chain")
        r = json.loads(rows[0][4])
        assert r["trigger"]["code"] == "7203"
        assert "6758" in r["chain"]
        assert r["lag_days"] == 2


# ─────────────────────────────────────────────────────────────────────────────
# generate_fund_flow_signals
# ─────────────────────────────────────────────────────────────────────────────

class TestFundFlow:
    def _setup(self, tmp_path):
        path, conn = _make_db(tmp_path)
        conn.execute(
            "INSERT INTO graph_fund_flows (sector_from,sector_to,volume_delta,return_spread,date) "
            "VALUES ('輸送用機器','電気機器',-0.15,0.025,?)", (TARGET_DATE,)
        )
        conn.commit()
        return path, conn

    def test_generates_bullish_signals_for_inflow_sector(self, tmp_path):
        from src.batch.signals import generate_fund_flow_signals
        path, conn = self._setup(tmp_path)

        n = generate_fund_flow_signals(conn, TARGET_DATE)

        # 電気機器は 6758 のみ
        assert n == 1
        rows = _fetch_signals(conn, "fund_flow")
        assert rows[0][1] == "6758"
        assert rows[0][2] == "bullish"

    def test_sector_column_set_correctly(self, tmp_path):
        from src.batch.signals import generate_fund_flow_signals
        path, conn = self._setup(tmp_path)
        generate_fund_flow_signals(conn, TARGET_DATE)

        row = conn.execute(
            "SELECT sector FROM signals WHERE signal_type='fund_flow'"
        ).fetchone()
        assert row[0] == "電気機器"

    def test_confidence_increases_with_past_occurrences(self, tmp_path):
        from src.batch.signals import generate_fund_flow_signals
        path, conn = self._setup(tmp_path)

        # 過去に同パターンが 30 回発生した状況
        for i in range(1, 31):
            d = f"2024-{12 if i <= 31 else 11}-{i:02d}" if i <= 31 else f"2024-11-{i:02d}"
            d = f"2024-12-{i:02d}"
            conn.execute(
                "INSERT OR IGNORE INTO graph_fund_flows "
                "(sector_from,sector_to,volume_delta,return_spread,date) "
                "VALUES ('輸送用機器','電気機器',-0.12,0.02,?)", (d,)
            )
        conn.commit()
        generate_fund_flow_signals(conn, TARGET_DATE)

        row = conn.execute(
            "SELECT confidence FROM signals WHERE signal_type='fund_flow'"
        ).fetchone()
        # 過去30回 → (30+1)/90 ≈ 0.344
        assert row[0] > 1 / 90

    def test_no_fund_flow_returns_zero(self, tmp_path):
        from src.batch.signals import generate_fund_flow_signals
        path, conn = _make_db(tmp_path)
        assert generate_fund_flow_signals(conn, TARGET_DATE) == 0

    def test_reasoning_contains_sector_info(self, tmp_path):
        from src.batch.signals import generate_fund_flow_signals
        path, conn = self._setup(tmp_path)
        generate_fund_flow_signals(conn, TARGET_DATE)

        row = conn.execute("SELECT reasoning FROM signals WHERE signal_type='fund_flow'").fetchone()
        r = json.loads(row[0])
        assert r["sector_from"] == "輸送用機器"
        assert r["sector_to"] == "電気機器"


# ─────────────────────────────────────────────────────────────────────────────
# generate_regime_shift_signals
# ─────────────────────────────────────────────────────────────────────────────

class TestRegimeShift:
    def _setup(self, tmp_path, today_regime="risk_on", prev_regime="risk_off"):
        path, conn = _make_db(tmp_path)
        conn.execute(
            "INSERT INTO daily_summary (date, regime) VALUES (?,?)", (TARGET_DATE, today_regime)
        )
        conn.execute(
            "INSERT INTO daily_summary (date, regime) VALUES (?,?)", (PREV_DATE, prev_regime)
        )
        conn.commit()
        return path, conn

    def test_generates_signal_on_regime_change(self, tmp_path):
        from src.batch.signals import generate_regime_shift_signals
        path, conn = self._setup(tmp_path, "risk_on", "risk_off")

        regime_perf = {
            "risk_on": [{"code": "7203", "avg_rs": 0.03}, {"code": "6902", "avg_rs": 0.02}]
        }
        n = generate_regime_shift_signals(conn, TARGET_DATE, regime_perf)

        assert n == 2
        rows = _fetch_signals(conn, "regime_shift")
        codes = {r[1] for r in rows}
        assert "7203" in codes
        assert all(r[2] == "bullish" for r in rows)

    def test_no_signal_when_regime_unchanged(self, tmp_path):
        from src.batch.signals import generate_regime_shift_signals
        path, conn = self._setup(tmp_path, "risk_on", "risk_on")  # 同じレジーム

        n = generate_regime_shift_signals(
            conn, TARGET_DATE, {"risk_on": [{"code": "7203", "avg_rs": 0.03}]}
        )
        assert n == 0

    def test_bearish_direction_for_risk_off(self, tmp_path):
        from src.batch.signals import generate_regime_shift_signals
        path, conn = self._setup(tmp_path, "risk_off", "neutral")

        n = generate_regime_shift_signals(
            conn, TARGET_DATE,
            {"risk_off": [{"code": "6758", "avg_rs": -0.02}]}
        )
        assert n == 1
        rows = _fetch_signals(conn, "regime_shift")
        assert rows[0][2] == "bearish"

    def test_confidence_formula(self, tmp_path):
        from src.batch.signals import generate_regime_shift_signals
        path, conn = self._setup(tmp_path, "risk_on", "neutral")

        avg_rs = 0.04
        generate_regime_shift_signals(
            conn, TARGET_DATE,
            {"risk_on": [{"code": "7203", "avg_rs": avg_rs}]}
        )
        row = conn.execute(
            "SELECT confidence FROM signals WHERE signal_type='regime_shift'"
        ).fetchone()
        expected = min(1.0, 0.5 + abs(avg_rs) * 10)
        assert abs(row[0] - expected) < 1e-4

    def test_no_daily_summary_returns_zero(self, tmp_path):
        from src.batch.signals import generate_regime_shift_signals
        path, conn = _make_db(tmp_path)
        n = generate_regime_shift_signals(conn, TARGET_DATE, {"risk_on": []})
        assert n == 0


# ─────────────────────────────────────────────────────────────────────────────
# generate_cluster_breakout_signals
# ─────────────────────────────────────────────────────────────────────────────

class TestClusterBreakout:
    def _setup(self, tmp_path):
        """
        コミュニティ 0: 7203(+3%), 6758(+2.5%), 6902(-2%)
          → avg = +1.17%  6902 が逆方向 → bullish
        """
        path, conn = _make_db(tmp_path)
        # daily_prices
        _insert_price(conn, "7203", TARGET_DATE, 0.030)
        _insert_price(conn, "6758", TARGET_DATE, 0.025)
        _insert_price(conn, "6902", TARGET_DATE, -0.020)
        # graph_communities
        conn.executemany(
            "INSERT INTO graph_communities (code,community_id,calc_date) VALUES (?,?,?)",
            [("7203", 0, TARGET_DATE), ("6758", 0, TARGET_DATE), ("6902", 0, TARGET_DATE)],
        )
        conn.commit()
        return path, conn

    def test_detects_outlier_in_bullish_community(self, tmp_path):
        from src.batch.signals import generate_cluster_breakout_signals
        path, conn = self._setup(tmp_path)

        n = generate_cluster_breakout_signals(conn, TARGET_DATE)

        assert n >= 1
        rows = _fetch_signals(conn, "cluster_breakout")
        codes = {r[1] for r in rows}
        assert "6902" in codes

    def test_outlier_is_bullish(self, tmp_path):
        """下落した 6902 はコミュニティ平均>0 なので bullish"""
        from src.batch.signals import generate_cluster_breakout_signals
        path, conn = self._setup(tmp_path)
        generate_cluster_breakout_signals(conn, TARGET_DATE)

        row = conn.execute(
            "SELECT direction FROM signals WHERE signal_type='cluster_breakout' AND code='6902'"
        ).fetchone()
        assert row is not None
        assert row[0] == "bullish"

    def test_bearish_signal_in_declining_community(self, tmp_path):
        """
        コミュニティ平均 < 0 なのに上昇した銘柄 → bearish (反落期待)
        """
        path, conn = _make_db(tmp_path)
        _insert_price(conn, "7203", TARGET_DATE, -0.030)
        _insert_price(conn, "6758", TARGET_DATE, -0.025)
        _insert_price(conn, "6902", TARGET_DATE,  0.020)  # 逆方向上昇
        conn.executemany(
            "INSERT INTO graph_communities (code,community_id,calc_date) VALUES (?,?,?)",
            [("7203", 0, TARGET_DATE), ("6758", 0, TARGET_DATE), ("6902", 0, TARGET_DATE)],
        )
        conn.commit()

        from src.batch.signals import generate_cluster_breakout_signals
        generate_cluster_breakout_signals(conn, TARGET_DATE)

        row = conn.execute(
            "SELECT direction FROM signals WHERE signal_type='cluster_breakout' AND code='6902'"
        ).fetchone()
        assert row[0] == "bearish"

    def test_no_signal_when_deviation_too_small(self, tmp_path):
        """乖離が閾値未満のときはシグナルなし"""
        path, conn = _make_db(tmp_path)
        _insert_price(conn, "7203", TARGET_DATE, 0.010)
        _insert_price(conn, "6758", TARGET_DATE, 0.009)  # 差が < 0.01
        conn.executemany(
            "INSERT INTO graph_communities (code,community_id,calc_date) VALUES (?,?,?)",
            [("7203", 0, TARGET_DATE), ("6758", 0, TARGET_DATE)],
        )
        conn.commit()

        from src.batch.signals import generate_cluster_breakout_signals
        n = generate_cluster_breakout_signals(conn, TARGET_DATE)
        assert n == 0

    def test_reasoning_contains_community_info(self, tmp_path):
        from src.batch.signals import generate_cluster_breakout_signals
        path, conn = self._setup(tmp_path)
        generate_cluster_breakout_signals(conn, TARGET_DATE)

        row = conn.execute(
            "SELECT reasoning FROM signals WHERE signal_type='cluster_breakout' AND code='6902'"
        ).fetchone()
        r = json.loads(row[0])
        assert "community_id" in r
        assert "deviation" in r
        assert r["deviation"] < 0  # 6902 はコミュニティ平均より下


# ─────────────────────────────────────────────────────────────────────────────
# update_daily_summary
# ─────────────────────────────────────────────────────────────────────────────

class TestUpdateDailySummary:
    def _setup(self, tmp_path):
        path, conn = _make_db(tmp_path)
        _insert_price(conn, "7203", TARGET_DATE,  0.030)
        _insert_price(conn, "6758", TARGET_DATE, -0.020)
        _insert_price(conn, "6902", TARGET_DATE,  0.015)
        # シグナルを数件挿入
        conn.executemany(
            "INSERT INTO signals (date,signal_type,code,sector,direction,confidence,reasoning) "
            "VALUES (?,?,?,?,?,?,?)",
            [
                (TARGET_DATE, "causality_chain", "6758", None, "bullish", 0.8, "{}"),
                (TARGET_DATE, "fund_flow",       "6902", "輸送用機器", "bullish", 0.5, "{}"),
            ],
        )
        conn.commit()
        return path, conn

    def test_active_signals_count(self, tmp_path):
        from src.batch.signals import update_daily_summary
        path, conn = self._setup(tmp_path)
        update_daily_summary(conn, TARGET_DATE)

        row = conn.execute(
            "SELECT active_signals FROM daily_summary WHERE date=?", (TARGET_DATE,)
        ).fetchone()
        assert row[0] == 2

    def test_top_gainers_json(self, tmp_path):
        from src.batch.signals import update_daily_summary
        path, conn = self._setup(tmp_path)
        update_daily_summary(conn, TARGET_DATE)

        row = conn.execute(
            "SELECT top_gainers FROM daily_summary WHERE date=?", (TARGET_DATE,)
        ).fetchone()
        gainers = json.loads(row[0])
        assert isinstance(gainers, list)
        assert gainers[0]["code"] == "7203"  # 最大騰落率

    def test_top_losers_json(self, tmp_path):
        from src.batch.signals import update_daily_summary
        path, conn = self._setup(tmp_path)
        update_daily_summary(conn, TARGET_DATE)

        row = conn.execute(
            "SELECT top_losers FROM daily_summary WHERE date=?", (TARGET_DATE,)
        ).fetchone()
        losers = json.loads(row[0])
        assert losers[0]["code"] == "6758"  # 最小騰落率

    def test_upsert_on_existing_row(self, tmp_path):
        """既存行への ON CONFLICT UPDATE が正しく動作する"""
        from src.batch.signals import update_daily_summary
        path, conn = self._setup(tmp_path)
        # 既存行を作成
        conn.execute(
            "INSERT INTO daily_summary (date, regime) VALUES (?,?)", (TARGET_DATE, "risk_on")
        )
        conn.commit()

        update_daily_summary(conn, TARGET_DATE)

        rows = conn.execute(
            "SELECT * FROM daily_summary WHERE date=?", (TARGET_DATE,)
        ).fetchall()
        assert len(rows) == 1  # 重複なし


# ─────────────────────────────────────────────────────────────────────────────
# generate (統合)
# ─────────────────────────────────────────────────────────────────────────────

class TestGenerate:
    def test_runs_all_signal_types(self, tmp_path):
        """generate() が全シグナル種別を実行して daily_summary を更新する"""
        path, conn = _make_db(tmp_path)

        # 各シグナルが発火するデータをセット
        # causality_chain 用
        _insert_price(conn, "7203", TARGET_DATE,  0.035)
        _insert_price(conn, "6758", TARGET_DATE,  0.010)
        _insert_price(conn, "6902", TARGET_DATE, -0.020)
        conn.execute(
            "INSERT INTO graph_causality (source,target,lag_days,p_value,f_stat,period,calc_date) "
            "VALUES ('7203','6758',2,0.02,7.5,'60d',?)", (TARGET_DATE,)
        )
        # fund_flow 用
        conn.execute(
            "INSERT INTO graph_fund_flows (sector_from,sector_to,volume_delta,return_spread,date) "
            "VALUES ('輸送用機器','電気機器',-0.15,0.025,?)", (TARGET_DATE,)
        )
        # regime_shift 用
        conn.execute(
            "INSERT INTO daily_summary (date,regime) VALUES (?,?)", (TARGET_DATE, "risk_on")
        )
        conn.execute(
            "INSERT INTO daily_summary (date,regime) VALUES (?,?)", (PREV_DATE, "risk_off")
        )
        # cluster_breakout 用
        conn.executemany(
            "INSERT INTO graph_communities (code,community_id,calc_date) VALUES (?,?,?)",
            [("7203", 0, TARGET_DATE), ("6758", 0, TARGET_DATE), ("6902", 0, TARGET_DATE)],
        )
        conn.commit()
        conn.close()

        from src.batch.signals import generate
        chains = [{"leader": "7203", "follower": "6758", "lag_total": 2, "hops": 1}]
        regime_perf = {
            "risk_on": [{"code": "7203", "avg_rs": 0.03}]
        }
        total = generate(path, TARGET_DATE, {"chains": chains, "regime_perf": regime_perf})

        assert total > 0

        conn = sqlite3.connect(path)
        types = {r[0] for r in conn.execute(
            "SELECT DISTINCT signal_type FROM signals WHERE date=?", (TARGET_DATE,)
        ).fetchall()}
        # 少なくとも causality_chain と fund_flow は存在する
        assert "causality_chain" in types
        assert "fund_flow" in types

        # daily_summary が更新されている
        row = conn.execute(
            "SELECT active_signals FROM daily_summary WHERE date=?", (TARGET_DATE,)
        ).fetchone()
        assert row is not None
        assert row[0] == total
        conn.close()

    def test_generate_with_no_graph_results(self, tmp_path):
        """graph_results=None でもエラーにならない"""
        from src.batch.signals import generate
        path, conn = _make_db(tmp_path)
        conn.close()
        result = generate(path, TARGET_DATE, graph_results=None)
        assert isinstance(result, int)
