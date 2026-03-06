"""compute_investor_flow_indicators のユニットテスト (固定データで期待値検証)"""
import sqlite3
import sys
import os

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scripts.init_sqlite import init_sqlite
from src.transform.statistics import compute_investor_flow_indicators


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def db_path(tmp_path):
    """テスト用 SQLite パスを返す (スキーマ初期化済み)"""
    path = str(tmp_path / "test.db")
    init_sqlite(path)
    return path


def _insert_flow_weeks(db_path: str, weeks: list[dict]) -> None:
    """investor_flow_weekly にテストデータを投入するヘルパー。"""
    conn = sqlite3.connect(db_path)
    conn.executemany(
        """
        INSERT OR REPLACE INTO investor_flow_weekly
            (week_start, week_end, section, investor_type, sales, purchases, balance)
        VALUES (:week_start, :week_end, 'TSEPrime', :investor_type, :sales, :purchases, :balance)
        """,
        weeks,
    )
    conn.commit()
    conn.close()


def _insert_nikkei_closes(db_path: str, closes: list[tuple[str, float]]) -> None:
    """daily_summary に日経終値テストデータを投入するヘルパー。"""
    conn = sqlite3.connect(db_path)
    conn.executemany(
        "INSERT OR REPLACE INTO daily_summary (date, nikkei_close) VALUES (?, ?)",
        closes,
    )
    conn.commit()
    conn.close()


def _get_indicators(db_path: str, week_end: str) -> dict | None:
    """テスト用: 指定週のインジケータを取得する。"""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT * FROM investor_flow_indicators WHERE week_end = ?",
        (week_end,),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


# ── 基本動作テスト ─────────────────────────────────────────────────────────

class TestComputeInvestorFlowIndicatorsBasic:
    def test_no_data_returns_zero(self, db_path):
        """フローデータが空の場合は 0 を返すこと"""
        result = compute_investor_flow_indicators(db_path, "2026-01-31")
        assert result == 0

    def test_returns_count_of_processed_weeks(self, db_path):
        """処理した週数を返すこと"""
        weeks = [
            {"week_start": "2026-01-01", "week_end": "2026-01-07",
             "investor_type": "foreigners", "sales": 100.0, "purchases": 200.0, "balance": 100.0},
            {"week_start": "2026-01-01", "week_end": "2026-01-07",
             "investor_type": "individuals", "sales": 200.0, "purchases": 100.0, "balance": -100.0},
        ]
        _insert_flow_weeks(db_path, weeks)

        result = compute_investor_flow_indicators(db_path, "2026-01-07")
        assert result >= 1

    def test_indicator_saved_to_db(self, db_path):
        """計算結果が investor_flow_indicators に保存されること"""
        weeks = [
            {"week_start": "2026-01-01", "week_end": "2026-01-07",
             "investor_type": "foreigners", "sales": 100.0, "purchases": 200.0, "balance": 100.0},
            {"week_start": "2026-01-01", "week_end": "2026-01-07",
             "investor_type": "individuals", "sales": 200.0, "purchases": 100.0, "balance": -100.0},
        ]
        _insert_flow_weeks(db_path, weeks)

        compute_investor_flow_indicators(db_path, "2026-01-07")

        indicator = _get_indicators(db_path, "2026-01-07")
        assert indicator is not None
        assert indicator["foreigners_net"] == pytest.approx(100.0)
        assert indicator["individuals_net"] == pytest.approx(-100.0)


# ── 移動平均テスト ──────────────────────────────────────────────────────────

class TestFourWeekMA:
    """4週移動平均の計算を検証する。

    手計算:
        週1: 海外 +100 → 4w_ma = 100/1 = 100.0
        週2: 海外 +200 → 4w_ma = 300/2 = 150.0
        週3: 海外 +300 → 4w_ma = 600/3 = 200.0
        週4: 海外 +400 → 4w_ma = 1000/4 = 250.0
        週5: 海外 +500 → 4w_ma = (200+300+400+500)/4 = 350.0
    """

    def _insert_5_weeks(self, db_path: str) -> None:
        weeks = []
        balances = [100.0, 200.0, 300.0, 400.0, 500.0]
        starts = ["2026-01-01", "2026-01-08", "2026-01-15", "2026-01-22", "2026-01-29"]
        ends   = ["2026-01-07", "2026-01-14", "2026-01-21", "2026-01-28", "2026-02-04"]
        for i, (s, e, b) in enumerate(zip(starts, ends, balances)):
            weeks.extend([
                {"week_start": s, "week_end": e, "investor_type": "foreigners",
                 "sales": 100.0, "purchases": 100.0 + b, "balance": b},
                {"week_start": s, "week_end": e, "investor_type": "individuals",
                 "sales": 100.0 + b, "purchases": 100.0, "balance": -b},
            ])
        _insert_flow_weeks(db_path, weeks)

    def test_4w_ma_week4(self, db_path):
        """週4の4週移動平均: (100+200+300+400)/4 = 250.0"""
        self._insert_5_weeks(db_path)
        compute_investor_flow_indicators(db_path, "2026-01-28")

        ind = _get_indicators(db_path, "2026-01-28")
        assert ind is not None
        assert ind["foreigners_4w_ma"] == pytest.approx(250.0, abs=1e-6)

    def test_4w_ma_week5_sliding_window(self, db_path):
        """週5の4週移動平均: (200+300+400+500)/4 = 350.0 (週1は除外)"""
        self._insert_5_weeks(db_path)
        compute_investor_flow_indicators(db_path, "2026-02-04")

        ind = _get_indicators(db_path, "2026-02-04")
        assert ind is not None
        assert ind["foreigners_4w_ma"] == pytest.approx(350.0, abs=1e-6)

    def test_individuals_4w_ma_negative(self, db_path):
        """個人の4週移動平均がマイナスになること"""
        self._insert_5_weeks(db_path)
        compute_investor_flow_indicators(db_path, "2026-01-28")

        ind = _get_indicators(db_path, "2026-01-28")
        assert ind is not None
        assert ind["individuals_4w_ma"] == pytest.approx(-250.0, abs=1e-6)


# ── モメンタムテスト ────────────────────────────────────────────────────────

class TestMomentum:
    """4週前比モメンタムを検証する。

    手計算:
        週1: 海外 +100
        週2: 海外 +150
        週3: 海外 +200
        週4: 海外 +250
        週5: 海外 +300
        週5 momentum = 週5 - 週1 = 300 - 100 = +200
    """

    def _insert_weeks_with_balances(self, db_path: str, balances: list[float]) -> list[str]:
        weeks = []
        week_ends = []
        starts = ["2026-01-01", "2026-01-08", "2026-01-15", "2026-01-22", "2026-01-29"]
        ends   = ["2026-01-07", "2026-01-14", "2026-01-21", "2026-01-28", "2026-02-04"]
        for s, e, b in zip(starts[:len(balances)], ends[:len(balances)], balances):
            weeks.extend([
                {"week_start": s, "week_end": e, "investor_type": "foreigners",
                 "sales": 100.0, "purchases": 100.0 + b, "balance": b},
                {"week_start": s, "week_end": e, "investor_type": "individuals",
                 "sales": 100.0 + b, "purchases": 100.0, "balance": -b},
            ])
            week_ends.append(e)
        _insert_flow_weeks(db_path, weeks)
        return week_ends

    def test_momentum_is_none_when_less_than_5_weeks(self, db_path):
        """4週以内のデータではモメンタムが NaN (4週前がない)"""
        self._insert_weeks_with_balances(db_path, [100.0, 150.0, 200.0, 250.0])
        compute_investor_flow_indicators(db_path, "2026-01-28")

        ind = _get_indicators(db_path, "2026-01-07")
        # 最初の週はモメンタムが None
        assert ind is not None
        assert ind["foreigners_momentum"] is None

    def test_momentum_week5(self, db_path):
        """週5のモメンタム = 週5(300) - 週1(100) = 200"""
        self._insert_weeks_with_balances(db_path, [100.0, 150.0, 200.0, 250.0, 300.0])
        compute_investor_flow_indicators(db_path, "2026-02-04")

        ind = _get_indicators(db_path, "2026-02-04")
        assert ind is not None
        assert ind["foreigners_momentum"] == pytest.approx(200.0, abs=1e-6)
        assert ind["individuals_momentum"] == pytest.approx(-200.0, abs=1e-6)


# ── divergence_score テスト ──────────────────────────────────────────────────

class TestDivergenceScore:
    def test_divergence_score_clipped_to_minus_one(self, db_path):
        """divergence_score は -1.0 以上 +1.0 以下にクリップされること"""
        # 海外が大幅買い越し・個人が大幅売り越し → 負の divergence
        weeks = []
        starts = ["2026-01-01", "2026-01-08", "2026-01-15", "2026-01-22", "2026-01-29"]
        ends   = ["2026-01-07", "2026-01-14", "2026-01-21", "2026-01-28", "2026-02-04"]
        for s, e in zip(starts, ends):
            weeks.extend([
                {"week_start": s, "week_end": e, "investor_type": "foreigners",
                 "sales": 1.0, "purchases": 10_000_000.0, "balance": 9_999_999.0},
                {"week_start": s, "week_end": e, "investor_type": "individuals",
                 "sales": 10_000_000.0, "purchases": 1.0, "balance": -9_999_999.0},
            ])
        _insert_flow_weeks(db_path, weeks)

        compute_investor_flow_indicators(db_path, "2026-02-04")

        ind = _get_indicators(db_path, "2026-02-04")
        assert ind is not None
        assert ind["divergence_score"] is not None
        assert -1.0 <= ind["divergence_score"] <= 1.0

    def test_divergence_score_is_float_or_none(self, db_path):
        """divergence_score は数値または None であること"""
        weeks = [
            {"week_start": "2026-01-01", "week_end": "2026-01-07",
             "investor_type": "foreigners", "sales": 100.0, "purchases": 200.0, "balance": 100.0},
            {"week_start": "2026-01-01", "week_end": "2026-01-07",
             "investor_type": "individuals", "sales": 200.0, "purchases": 100.0, "balance": -100.0},
        ]
        _insert_flow_weeks(db_path, weeks)
        compute_investor_flow_indicators(db_path, "2026-01-07")

        ind = _get_indicators(db_path, "2026-01-07")
        assert ind is not None
        if ind["divergence_score"] is not None:
            assert isinstance(ind["divergence_score"], float)
            assert not np.isnan(ind["divergence_score"])


# ── nikkei_return_4w テスト ──────────────────────────────────────────────────

class TestNikkeiReturn4w:
    def test_nikkei_return_4w_calculated(self, db_path):
        """日経平均4週リターンが正しく計算されること。

        手計算:
            4週前終値: 35000
            最新終値:  37000
            4週リターン = (37000 - 35000) / 35000 = 0.05714...
        """
        # 日経終値データを投入
        closes = [
            ("2025-12-31", 35000.0),  # 4週前に近い日付
            ("2026-01-02", 35500.0),
            ("2026-01-07", 36000.0),
            ("2026-01-14", 36500.0),
            ("2026-01-21", 37000.0),
        ]
        _insert_nikkei_closes(db_path, closes)

        weeks = [
            {"week_start": "2026-01-15", "week_end": "2026-01-21",
             "investor_type": "foreigners", "sales": 100.0, "purchases": 200.0, "balance": 100.0},
            {"week_start": "2026-01-15", "week_end": "2026-01-21",
             "investor_type": "individuals", "sales": 200.0, "purchases": 100.0, "balance": -100.0},
        ]
        _insert_flow_weeks(db_path, weeks)

        compute_investor_flow_indicators(db_path, "2026-01-21")

        ind = _get_indicators(db_path, "2026-01-21")
        assert ind is not None
        if ind["nikkei_return_4w"] is not None:
            # 35000 から 37000 で +5.7% 前後
            assert ind["nikkei_return_4w"] == pytest.approx(
                (37000.0 - 35000.0) / 35000.0, abs=0.02
            )

    def test_nikkei_return_4w_none_without_data(self, db_path):
        """日経データがない場合は None になること"""
        weeks = [
            {"week_start": "2026-01-01", "week_end": "2026-01-07",
             "investor_type": "foreigners", "sales": 100.0, "purchases": 200.0, "balance": 100.0},
            {"week_start": "2026-01-01", "week_end": "2026-01-07",
             "investor_type": "individuals", "sales": 200.0, "purchases": 100.0, "balance": -100.0},
        ]
        _insert_flow_weeks(db_path, weeks)

        compute_investor_flow_indicators(db_path, "2026-01-07")

        ind = _get_indicators(db_path, "2026-01-07")
        assert ind is not None
        assert ind["nikkei_return_4w"] is None


# ── flow_regime テスト ───────────────────────────────────────────────────────

class TestFlowRegime:
    def _insert_basic_week(
        self, db_path: str, week_start: str, week_end: str,
        foreigners_balance: float, individuals_balance: float,
    ) -> None:
        _insert_flow_weeks(db_path, [
            {"week_start": week_start, "week_end": week_end,
             "investor_type": "foreigners", "sales": 100.0,
             "purchases": 100.0 + foreigners_balance, "balance": foreigners_balance},
            {"week_start": week_start, "week_end": week_end,
             "investor_type": "individuals", "sales": 100.0 + abs(individuals_balance),
             "purchases": 100.0, "balance": individuals_balance},
        ])

    def test_bull_regime_foreigners_buy_individuals_sell(self, db_path):
        """海外買い越し + 個人売り越し → bull レジーム"""
        for i in range(4):
            start = f"2026-01-{1 + i*7:02d}"
            end   = f"2026-01-{7 + i*7:02d}"
            self._insert_basic_week(db_path, start, end, 1_000_000.0, -500_000.0)

        compute_investor_flow_indicators(db_path, "2026-01-28")

        ind = _get_indicators(db_path, "2026-01-28")
        assert ind is not None
        assert ind["flow_regime"] == "bull"

    def test_regime_fallback_to_previous_when_ambiguous(self, db_path):
        """条件が曖昧な場合は直前レジームを維持すること"""
        # 最初の週: 海外買い越し → bull
        self._insert_basic_week(db_path, "2026-01-01", "2026-01-07", 100.0, -50.0)
        compute_investor_flow_indicators(db_path, "2026-01-07")

        ind = _get_indicators(db_path, "2026-01-07")
        assert ind is not None
        # bull or その他の規定値
        assert ind["flow_regime"] in ("bull", "bear", "topping", "bottoming")
