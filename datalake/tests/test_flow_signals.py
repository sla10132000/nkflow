"""generate_investor_flow_signals のユニットテスト"""
import json
import sqlite3
import sys
import os

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scripts.init_sqlite import init_sqlite
from src.signals.generator import generate_investor_flow_signals


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def db_path(tmp_path):
    path = str(tmp_path / "test.db")
    init_sqlite(path)
    return path


def _insert_indicator(
    db_path: str,
    week_end: str,
    foreigners_net: float = 1_000_000.0,
    individuals_net: float = -500_000.0,
    foreigners_4w_ma: float = 1_000_000.0,
    individuals_4w_ma: float = -500_000.0,
    foreigners_momentum: float = 200_000.0,
    individuals_momentum: float = -100_000.0,
    divergence_score: float = 0.2,
    nikkei_return_4w: float = 0.03,
    flow_regime: str = "bull",
) -> None:
    """investor_flow_indicators にテストデータを投入するヘルパー。"""
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        INSERT OR REPLACE INTO investor_flow_indicators
            (week_end, foreigners_net, individuals_net,
             foreigners_4w_ma, individuals_4w_ma,
             foreigners_momentum, individuals_momentum,
             divergence_score, nikkei_return_4w, flow_regime)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (week_end, foreigners_net, individuals_net,
         foreigners_4w_ma, individuals_4w_ma,
         foreigners_momentum, individuals_momentum,
         divergence_score, nikkei_return_4w, flow_regime),
    )
    conn.commit()
    conn.close()


def _get_signals(db_path: str, date: str) -> list[dict]:
    """テスト用: 指定日のシグナルを取得する。"""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM signals WHERE date = ? AND signal_type LIKE 'investor_flow_%'",
        (date,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── データなし ────────────────────────────────────────────────────────────────

class TestNoData:
    def test_no_indicator_returns_zero(self, db_path):
        """指標データがない場合は 0 を返すこと"""
        result = generate_investor_flow_signals(db_path, "2026-01-31")
        assert result == 0


# ── topping シグナル ─────────────────────────────────────────────────────────

class TestToppingSignal:
    """
    topping (bearish) 条件:
      divergence_score >= 0.5 AND foreigners_momentum < 0 AND nikkei_return_4w > 0
    """

    def test_topping_signal_generated(self, db_path):
        """topping 条件を満たす場合にシグナルが生成されること"""
        _insert_indicator(
            db_path, "2026-01-07",
            divergence_score=0.6,      # >= 0.5 ✓
            foreigners_momentum=-300_000.0,  # < 0 ✓
            nikkei_return_4w=0.02,     # > 0 ✓
        )

        result = generate_investor_flow_signals(db_path, "2026-01-07")
        assert result >= 1

        signals = _get_signals(db_path, "2026-01-07")
        types = {s["signal_type"] for s in signals}
        assert "investor_flow_topping" in types

    def test_topping_is_bearish(self, db_path):
        """topping シグナルは bearish であること"""
        _insert_indicator(
            db_path, "2026-01-07",
            divergence_score=0.7,
            foreigners_momentum=-500_000.0,
            nikkei_return_4w=0.05,
        )
        generate_investor_flow_signals(db_path, "2026-01-07")

        signals = _get_signals(db_path, "2026-01-07")
        topping = next(s for s in signals if s["signal_type"] == "investor_flow_topping")
        assert topping["direction"] == "bearish"

    def test_topping_not_generated_when_nikkei_negative(self, db_path):
        """nikkei_return_4w が負の場合は topping が生成されないこと"""
        _insert_indicator(
            db_path, "2026-01-07",
            divergence_score=0.6,
            foreigners_momentum=-300_000.0,
            nikkei_return_4w=-0.02,    # < 0 → topping 条件不成立
        )
        generate_investor_flow_signals(db_path, "2026-01-07")

        signals = _get_signals(db_path, "2026-01-07")
        types = {s["signal_type"] for s in signals}
        assert "investor_flow_topping" not in types


# ── bottoming シグナル ───────────────────────────────────────────────────────

class TestBottomingSignal:
    """
    bottoming (bullish) 条件:
      divergence_score <= -0.5 AND foreigners_momentum > 0 AND nikkei_return_4w < 0
    """

    def test_bottoming_signal_generated(self, db_path):
        """bottoming 条件を満たす場合にシグナルが生成されること"""
        _insert_indicator(
            db_path, "2026-01-07",
            divergence_score=-0.6,       # <= -0.5 ✓
            foreigners_momentum=300_000.0,  # > 0 ✓
            nikkei_return_4w=-0.02,      # < 0 ✓
        )

        result = generate_investor_flow_signals(db_path, "2026-01-07")
        assert result >= 1

        signals = _get_signals(db_path, "2026-01-07")
        types = {s["signal_type"] for s in signals}
        assert "investor_flow_bottoming" in types

    def test_bottoming_is_bullish(self, db_path):
        """bottoming シグナルは bullish であること"""
        _insert_indicator(
            db_path, "2026-01-07",
            divergence_score=-0.7,
            foreigners_momentum=500_000.0,
            nikkei_return_4w=-0.05,
        )
        generate_investor_flow_signals(db_path, "2026-01-07")

        signals = _get_signals(db_path, "2026-01-07")
        bottoming = next(s for s in signals if s["signal_type"] == "investor_flow_bottoming")
        assert bottoming["direction"] == "bullish"

    def test_bottoming_not_generated_when_nikkei_positive(self, db_path):
        """nikkei_return_4w が正の場合は bottoming が生成されないこと"""
        _insert_indicator(
            db_path, "2026-01-07",
            divergence_score=-0.6,
            foreigners_momentum=300_000.0,
            nikkei_return_4w=0.02,   # > 0 → bottoming 条件不成立
        )
        generate_investor_flow_signals(db_path, "2026-01-07")

        signals = _get_signals(db_path, "2026-01-07")
        types = {s["signal_type"] for s in signals}
        assert "investor_flow_bottoming" not in types


# ── divergence シグナル ──────────────────────────────────────────────────────

class TestDivergenceSignal:
    """
    divergence 条件: abs(divergence_score) >= 0.3
      かつ topping / bottoming が生成されない場合のみ
    """

    def test_bearish_divergence_when_positive_score(self, db_path):
        """divergence_score > 0 (>= 0.3) の場合は bearish divergence シグナル"""
        _insert_indicator(
            db_path, "2026-01-07",
            divergence_score=0.4,       # 0.3 以上、0.5 未満
            foreigners_momentum=100_000.0,  # 正なのでtopping不成立
            nikkei_return_4w=0.01,
        )
        result = generate_investor_flow_signals(db_path, "2026-01-07")
        assert result >= 1

        signals = _get_signals(db_path, "2026-01-07")
        div_signal = next(
            (s for s in signals if s["signal_type"] == "investor_flow_divergence"), None
        )
        assert div_signal is not None
        assert div_signal["direction"] == "bearish"

    def test_bullish_divergence_when_negative_score(self, db_path):
        """divergence_score < 0 (<= -0.3) の場合は bullish divergence シグナル"""
        _insert_indicator(
            db_path, "2026-01-07",
            divergence_score=-0.4,
            foreigners_momentum=-100_000.0,  # 負なのでbottoming不成立
            nikkei_return_4w=-0.01,
        )
        generate_investor_flow_signals(db_path, "2026-01-07")

        signals = _get_signals(db_path, "2026-01-07")
        div_signal = next(
            (s for s in signals if s["signal_type"] == "investor_flow_divergence"), None
        )
        assert div_signal is not None
        assert div_signal["direction"] == "bullish"

    def test_no_signal_when_divergence_below_threshold(self, db_path):
        """divergence_score が 0.3 未満の場合はシグナルが生成されないこと"""
        _insert_indicator(
            db_path, "2026-01-07",
            divergence_score=0.2,   # < 0.3 → 条件不成立
            foreigners_momentum=100_000.0,
            nikkei_return_4w=0.01,
        )
        result = generate_investor_flow_signals(db_path, "2026-01-07")
        assert result == 0

    def test_divergence_not_generated_when_topping_exists(self, db_path):
        """topping シグナルが生成される場合は divergence は生成されないこと"""
        _insert_indicator(
            db_path, "2026-01-07",
            divergence_score=0.6,           # topping 条件 (>= 0.5) を満たす
            foreigners_momentum=-300_000.0,
            nikkei_return_4w=0.02,
        )
        generate_investor_flow_signals(db_path, "2026-01-07")

        signals = _get_signals(db_path, "2026-01-07")
        types = {s["signal_type"] for s in signals}
        assert "investor_flow_topping" in types
        assert "investor_flow_divergence" not in types


# ── confidence テスト ──────────────────────────────────────────────────────

class TestConfidence:
    def test_confidence_equals_abs_divergence_score(self, db_path):
        """confidence = min(abs(divergence_score), 1.0) であること"""
        _insert_indicator(
            db_path, "2026-01-07",
            divergence_score=0.75,
            foreigners_momentum=-200_000.0,
            nikkei_return_4w=0.03,
        )
        generate_investor_flow_signals(db_path, "2026-01-07")

        signals = _get_signals(db_path, "2026-01-07")
        assert len(signals) >= 1
        for sig in signals:
            assert sig["confidence"] == pytest.approx(0.75, abs=1e-4)

    def test_confidence_capped_at_one(self, db_path):
        """divergence_score が 1.0 を超えても confidence は 1.0 にキャップされること"""
        # divergence_score は計算上 -1.0〜1.0 にクリップされているが念のため確認
        _insert_indicator(
            db_path, "2026-01-07",
            divergence_score=0.9,
            foreigners_momentum=-100_000.0,
            nikkei_return_4w=0.01,
        )
        generate_investor_flow_signals(db_path, "2026-01-07")

        signals = _get_signals(db_path, "2026-01-07")
        for sig in signals:
            assert sig["confidence"] <= 1.0


# ── reasoning JSON テスト ────────────────────────────────────────────────────

class TestReasoning:
    def test_reasoning_contains_required_keys(self, db_path):
        """reasoning JSON に必須フィールドが含まれること"""
        _insert_indicator(
            db_path, "2026-01-07",
            divergence_score=0.55,
            foreigners_momentum=-100_000.0,
            nikkei_return_4w=0.02,
            flow_regime="topping",
        )
        generate_investor_flow_signals(db_path, "2026-01-07")

        signals = _get_signals(db_path, "2026-01-07")
        assert len(signals) >= 1
        reasoning = json.loads(signals[0]["reasoning"])
        assert "foreigners_net" in reasoning
        assert "individuals_net" in reasoning
        assert "divergence_score" in reasoning
        assert "nikkei_return_4w" in reasoning
        assert "flow_regime" in reasoning

    def test_signals_code_is_null(self, db_path):
        """市場全体シグナルなので code は NULL であること"""
        _insert_indicator(
            db_path, "2026-01-07",
            divergence_score=0.4,
            foreigners_momentum=100_000.0,
            nikkei_return_4w=0.01,
        )
        generate_investor_flow_signals(db_path, "2026-01-07")

        signals = _get_signals(db_path, "2026-01-07")
        assert len(signals) >= 1
        for sig in signals:
            assert sig["code"] is None
            assert sig["sector"] is None


# ── 重複排除テスト ─────────────────────────────────────────────────────────

class TestDeduplication:
    def test_duplicate_signal_not_inserted(self, db_path):
        """同じ date + signal_type が存在する場合は INSERT しないこと"""
        _insert_indicator(
            db_path, "2026-01-07",
            divergence_score=0.4,
            foreigners_momentum=100_000.0,
            nikkei_return_4w=0.01,
        )

        # 1回目
        count1 = generate_investor_flow_signals(db_path, "2026-01-07")
        assert count1 >= 1

        # 2回目: 重複回避
        count2 = generate_investor_flow_signals(db_path, "2026-01-07")
        assert count2 == 0

        # DB 上のシグナル数が増えていないこと
        conn = sqlite3.connect(db_path)
        total = conn.execute(
            "SELECT COUNT(*) FROM signals WHERE date = '2026-01-07' AND signal_type LIKE 'investor_flow_%'"
        ).fetchone()[0]
        conn.close()
        assert total == count1
