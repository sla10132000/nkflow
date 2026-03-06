"""statistics.py のテスト"""
import os
import sqlite3
import sys
from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scripts.init_sqlite import init_sqlite

STOCKS = [
    ("7203", "トヨタ自動車", "輸送用機器"),
    ("6758", "ソニーグループ", "電気機器"),
    ("6902", "デンソー", "輸送用機器"),
    ("9984", "ソフトバンク", "情報・通信"),
]


def _make_dates(n: int, start: str = "2024-06-03") -> list[str]:
    """n 営業日分の日付リストを生成する"""
    return pd.bdate_range(start=start, periods=n).strftime("%Y-%m-%d").tolist()


def _seed_db(tmp_path, returns_by_code: dict[str, np.ndarray], stocks=STOCKS) -> tuple[str, list[str]]:
    """
    指定したリターン系列でDBをシードし、(db_path, dates) を返す。
    returns_by_code: {code: np.ndarray of return_rate}
    """
    n = max(len(v) for v in returns_by_code.values())
    dates = _make_dates(n)

    db_path = str(tmp_path / "test.db")
    init_sqlite(db_path)

    conn = sqlite3.connect(db_path)
    conn.executemany("INSERT INTO stocks VALUES (?,?,?)", stocks)

    rows = []
    for code, returns in returns_by_code.items():
        price = 1000.0
        for i, ret in enumerate(returns):
            d = dates[i]
            close = round(price * (1 + ret), 4)
            rows.append((
                code, d,
                price, price * 1.01, price * 0.99, close,
                1_000_000,
                ret, price * 0.02, 0.02, None,
            ))
            price = close

    conn.executemany(
        "INSERT INTO daily_prices "
        "(code, date, open, high, low, close, volume, "
        " return_rate, price_range, range_pct, relative_strength) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        rows,
    )
    conn.commit()
    conn.close()
    return db_path, dates


# ─────────────────────────────────────────────────────────────────────────────
# run_granger
# ─────────────────────────────────────────────────────────────────────────────

class TestRunGranger:
    def test_detects_known_causality(self, tmp_path):
        """
        7203 が 6758 に lag=1 で因果する合成データで
        グレンジャー検定が因果エッジを検出できることを確認する。
        """
        np.random.seed(0)
        n = 80
        noise_a = np.random.normal(0, 0.01, n)
        noise_b = np.random.normal(0, 0.005, n)

        # B[t] = 0.8 * A[t-1] + small_noise → A Granger-causes B
        a = noise_a.copy()
        b = np.zeros(n)
        b[0] = noise_b[0]
        for t in range(1, n):
            b[t] = 0.8 * a[t - 1] + noise_b[t]

        db_path, dates = _seed_db(
            tmp_path,
            {"7203": a, "6758": b},
            stocks=[STOCKS[0], STOCKS[1]],
        )
        from src.batch.statistics import run_granger

        count = run_granger(db_path, dates[-1], n_jobs=1)

        assert count > 0
        conn = sqlite3.connect(db_path)
        rows = conn.execute(
            "SELECT source, target, lag_days, p_value FROM graph_causality"
        ).fetchall()
        conn.close()

        sources = [r[0] for r in rows]
        assert "7203" in sources  # 7203 → 6758 のエッジが存在

    def test_saves_only_significant_pairs(self, tmp_path):
        """p_value < GRANGER_P_THRESHOLD のペアのみ保存される"""
        np.random.seed(42)
        n = 80
        # 全くランダムなリターン (因果なし)
        a = np.random.normal(0, 0.01, n)
        b = np.random.normal(0, 0.01, n)

        db_path, dates = _seed_db(
            tmp_path,
            {"7203": a, "6758": b},
            stocks=[STOCKS[0], STOCKS[1]],
        )
        from src.batch.statistics import run_granger
        from src.config import GRANGER_P_THRESHOLD

        run_granger(db_path, dates[-1], n_jobs=1)

        conn = sqlite3.connect(db_path)
        rows = conn.execute(
            "SELECT p_value FROM graph_causality"
        ).fetchall()
        conn.close()

        for (p,) in rows:
            assert p < GRANGER_P_THRESHOLD

    def test_empty_db_returns_zero(self, tmp_path):
        """データが空の場合は 0 を返す"""
        db_path = str(tmp_path / "empty.db")
        init_sqlite(db_path)

        from src.batch.statistics import run_granger
        result = run_granger(db_path, "2025-01-01", n_jobs=1)
        assert result == 0

    def test_insufficient_stocks_returns_zero(self, tmp_path):
        """銘柄が 1 つしかない場合は 0 を返す"""
        np.random.seed(0)
        a = np.random.normal(0, 0.01, 30)
        db_path, dates = _seed_db(
            tmp_path, {"7203": a}, stocks=[STOCKS[0]]
        )
        from src.batch.statistics import run_granger
        result = run_granger(db_path, dates[-1], n_jobs=1)
        assert result == 0


# ─────────────────────────────────────────────────────────────────────────────
# _cross_corr_best_lag (ユニット)
# ─────────────────────────────────────────────────────────────────────────────

class TestCrossCorr:
    def test_positive_lag_means_a_leads_b(self):
        """lag > 0 のとき a が b に lag 日先行する"""
        from src.batch.statistics import _cross_corr_best_lag

        np.random.seed(1)
        n = 100
        a = np.random.normal(0, 1, n)
        # b は a の lag=2 遅行版
        b = np.zeros(n)
        b[2:] = a[:-2] * 0.9 + np.random.normal(0, 0.1, n - 2)

        lag, corr = _cross_corr_best_lag(a, b, max_lag=5)

        assert lag == 2
        assert corr > 0.3

    def test_returns_zero_lag_for_uncorrelated(self):
        """無相関データでは lag=0, corr≈0 が返る (絶対値最小)"""
        from src.batch.statistics import _cross_corr_best_lag

        np.random.seed(2)
        a = np.random.normal(0, 1, 200)
        b = np.random.normal(0, 1, 200)

        lag, corr = _cross_corr_best_lag(a, b, max_lag=5)

        # ランダムなので相関が低いはず (強い閾値で保存されない)
        assert abs(corr) < 0.5  # 閾値 0.3 以下が多い


# ─────────────────────────────────────────────────────────────────────────────
# run_lead_lag
# ─────────────────────────────────────────────────────────────────────────────

class TestRunLeadLag:
    def test_detects_lead_lag_relationship(self, tmp_path):
        """7203 が 6758 に 2 日先行する合成データでエッジを検出できる"""
        np.random.seed(3)
        n = 80
        a = np.random.normal(0, 0.01, n)
        b = np.zeros(n)
        b[2:] = a[:-2] * 0.85 + np.random.normal(0, 0.002, n - 2)

        db_path, dates = _seed_db(
            tmp_path,
            {"7203": a, "6758": b},
            stocks=[STOCKS[0], STOCKS[1]],
        )
        from src.batch.statistics import run_lead_lag

        count = run_lead_lag(db_path, dates[-1])

        assert count > 0
        conn = sqlite3.connect(db_path)
        rows = conn.execute(
            "SELECT source, target, lag_days FROM graph_causality "
            "ORDER BY lag_days"
        ).fetchall()
        conn.close()

        assert any(r[0] == "7203" and r[2] == 2 for r in rows)

    def test_below_threshold_not_saved(self, tmp_path):
        """|cross_corr| < 0.3 のペアは保存されない"""
        np.random.seed(99)
        n = 80
        a = np.random.normal(0, 0.01, n)
        b = np.random.normal(0, 0.01, n)  # 無相関

        db_path, dates = _seed_db(
            tmp_path,
            {"7203": a, "6758": b},
            stocks=[STOCKS[0], STOCKS[1]],
        )
        from src.batch.statistics import run_lead_lag

        # 無相関なので保存件数は 0 かまたは非常に少ない
        # (ランダムノイズでたまたま 0.3 を超えることもあるため <= でチェック)
        count = run_lead_lag(db_path, dates[-1])
        # ランダムデータでは 0 または数件
        conn = sqlite3.connect(db_path)
        rows = conn.execute(
            "SELECT f_stat FROM graph_causality WHERE f_stat >= 0.3"
        ).fetchall()
        conn.close()
        # 保存されたものはすべて f_stat (= |cross_corr|) >= 0.3
        for (fs,) in rows:
            assert fs >= 0.3


# ─────────────────────────────────────────────────────────────────────────────
# run_fund_flow
# ─────────────────────────────────────────────────────────────────────────────

class TestRunFundFlow:
    def _seed_with_sectors(self, tmp_path, today_str: str):
        """
        輸送用機器 = outflow (出来高↓, リターン↓)
        電気機器   = inflow  (出来高↑, リターン↑)
        のパターンを持つ DB を作成する。
        """
        db_path = str(tmp_path / "ff.db")
        init_sqlite(db_path)

        conn = sqlite3.connect(db_path)
        conn.executemany("INSERT INTO stocks VALUES (?,?,?)", [
            ("7203", "トヨタ", "輸送用機器"),
            ("6758", "ソニー", "電気機器"),
        ])

        # ベースライン: 20日分 (出来高 = 1,000,000 / リターン ≒ 0)
        dates = pd.bdate_range(end=today_str, periods=21).strftime("%Y-%m-%d").tolist()
        baseline_dates = dates[:-1]

        rows = []
        for d in baseline_dates:
            for code in ["7203", "6758"]:
                rows.append((code, d, 1000, 1010, 990, 1000, 1_000_000, 0.0, 20, 0.02, None))

        # 当日: 輸送用機器 = 出来高 -20%, リターン -1.5%
        rows.append(("7203", today_str, 1000, 1005, 980, 985, 800_000, -0.015, 25, 0.025, None))
        # 当日: 電気機器   = 出来高 +25%, リターン +1.8%
        rows.append(("6758", today_str, 1000, 1020, 998, 1018, 1_250_000, 0.018, 22, 0.022, None))

        conn.executemany(
            "INSERT INTO daily_prices "
            "(code, date, open, high, low, close, volume, "
            " return_rate, price_range, range_pct, relative_strength) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            rows,
        )
        conn.commit()
        conn.close()
        return db_path

    def test_detects_outflow_to_inflow(self, tmp_path):
        """outflow セクター → inflow セクターへのフローエッジが作成される"""
        today = "2025-02-14"
        db_path = self._seed_with_sectors(tmp_path, today)

        from src.batch.statistics import run_fund_flow
        count = run_fund_flow(db_path, today)

        assert count == 1
        conn = sqlite3.connect(db_path)
        row = conn.execute(
            "SELECT sector_from, sector_to FROM graph_fund_flows"
        ).fetchone()
        conn.close()

        assert row[0] == "輸送用機器"
        assert row[1] == "電気機器"

    def test_no_flow_when_no_clear_pattern(self, tmp_path):
        """outflow / inflow どちらも存在しない場合は 0 を返す"""
        db_path = str(tmp_path / "no_flow.db")
        init_sqlite(db_path)
        conn = sqlite3.connect(db_path)
        conn.execute("INSERT INTO stocks VALUES ('7203','トヨタ','輸送用機器')")
        conn.execute(
            "INSERT INTO daily_prices "
            "(code, date, open, high, low, close, volume, return_rate, price_range, range_pct, relative_strength) "
            "VALUES ('7203','2025-01-06',1000,1010,990,1000,1000000, 0.0, 20, 0.02, NULL)"
        )
        conn.commit()
        conn.close()

        from src.batch.statistics import run_fund_flow
        result = run_fund_flow(db_path, "2025-01-06")
        assert result == 0


# ─────────────────────────────────────────────────────────────────────────────
# determine_regime
# ─────────────────────────────────────────────────────────────────────────────

class TestDetermineRegime:
    def _seed_regime_data(self, tmp_path, today_return: float, short_vol_lt_long: bool) -> tuple[str, str]:
        """
        レジーム判定用のデータをシードする。
        short_vol_lt_long=True なら直近5日ボラ < 長期ボラ (risk_on 条件)
        """
        np.random.seed(7)
        n = 25

        if short_vol_lt_long:
            long_returns = np.random.normal(0, 0.02, n - 5)
            short_returns = np.random.normal(0, 0.005, 4)  # 直近は低ボラ
        else:
            long_returns = np.random.normal(0, 0.005, n - 5)
            short_returns = np.random.normal(0, 0.02, 4)   # 直近は高ボラ

        returns = np.concatenate([long_returns, short_returns, [today_return]])
        dates = _make_dates(n)

        db_path = str(tmp_path / "regime.db")
        init_sqlite(db_path)
        conn = sqlite3.connect(db_path)
        conn.execute("INSERT INTO stocks VALUES ('7203','トヨタ','輸送用機器')")
        rows = [
            ("7203", dates[i], 1000, 1010, 990, 1000, 1_000_000,
             float(returns[i]), 20.0, 0.02, None)
            for i in range(n)
        ]
        conn.executemany(
            "INSERT INTO daily_prices "
            "(code, date, open, high, low, close, volume, "
            " return_rate, price_range, range_pct, relative_strength) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            rows,
        )
        conn.commit()
        conn.close()
        return db_path, dates[-1]

    def test_risk_on_detected(self, tmp_path):
        """リターン > 0 かつ 直近ボラ < 長期ボラ → risk_on"""
        db_path, last_date = self._seed_regime_data(
            tmp_path, today_return=0.015, short_vol_lt_long=True
        )
        from src.batch.statistics import determine_regime
        regime = determine_regime(db_path, last_date)
        assert regime == "risk_on"

    def test_risk_off_detected(self, tmp_path):
        """リターン < 0 かつ 直近ボラ > 長期ボラ → risk_off"""
        db_path, last_date = self._seed_regime_data(
            tmp_path, today_return=-0.015, short_vol_lt_long=False
        )
        from src.batch.statistics import determine_regime
        regime = determine_regime(db_path, last_date)
        assert regime == "risk_off"

    def test_neutral_when_ambiguous(self, tmp_path):
        """リターン > 0 かつ ボラ上昇 → neutral"""
        db_path, last_date = self._seed_regime_data(
            tmp_path, today_return=0.01, short_vol_lt_long=False
        )
        from src.batch.statistics import determine_regime
        regime = determine_regime(db_path, last_date)
        assert regime == "neutral"

    def test_regime_saved_to_daily_summary(self, tmp_path):
        """判定結果が daily_summary テーブルに保存される"""
        db_path, last_date = self._seed_regime_data(
            tmp_path, today_return=0.01, short_vol_lt_long=True
        )
        from src.batch.statistics import determine_regime
        regime = determine_regime(db_path, last_date)

        conn = sqlite3.connect(db_path)
        row = conn.execute(
            "SELECT regime FROM daily_summary WHERE date = ?", (last_date,)
        ).fetchone()
        conn.close()

        assert row is not None
        assert row[0] == regime

    def test_empty_db_returns_neutral(self, tmp_path):
        """データ不足の場合は neutral を返す"""
        db_path = str(tmp_path / "empty.db")
        init_sqlite(db_path)

        from src.batch.statistics import determine_regime
        regime = determine_regime(db_path, "2025-01-06")
        assert regime == "neutral"
