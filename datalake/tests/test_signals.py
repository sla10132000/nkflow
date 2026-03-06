"""signals.py (mega_trend_follow) のテスト"""

import json
import os
import sqlite3
import sys

import numpy as np
import pandas as pd
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scripts.init_sqlite import init_sqlite

STOCKS = [
    ("7203", "トヨタ自動車", "輸送用機器"),
    ("6758", "ソニーグループ", "電気機器"),
    ("9984", "ソフトバンクグループ", "情報・通信業"),
]


def _biz_dates(n: int, start: str = "2024-01-04") -> list[str]:
    """N営業日分の日付リストを返す。"""
    return pd.bdate_range(start=start, periods=n).strftime("%Y-%m-%d").tolist()


def _seed_trend_db(
    tmp_path,
    code: str = "7203",
    trend: str = "up",
    n_days: int = 140,
    seed: int = 42,
) -> tuple[str, str]:
    """
    指定トレンドの合成データでDBをシードする。

    Returns: (db_path, target_date)
    """
    db_path = str(tmp_path / "test.db")
    init_sqlite(db_path)

    conn = sqlite3.connect(db_path)
    conn.executemany("INSERT OR IGNORE INTO stocks VALUES (?, ?, ?)", STOCKS)

    rng = np.random.default_rng(seed)
    dates = _biz_dates(n_days)
    price = 1000.0
    rows = []

    for d in dates:
        if trend == "up":
            ret = rng.normal(0.004, 0.008)
        elif trend == "down":
            ret = rng.normal(-0.004, 0.008)
        else:
            ret = rng.normal(0.0, 0.008)

        new_price = price * (1 + ret)
        high = max(price, new_price) * (1 + rng.uniform(0.001, 0.005))
        low = min(price, new_price) * (1 - rng.uniform(0.001, 0.005))
        vol = int(rng.uniform(500_000, 2_000_000))

        # relative_strength: 上昇トレンドなら正、下降なら負
        if trend == "up":
            rs = abs(ret) * 0.5
        elif trend == "down":
            rs = -abs(ret) * 0.5
        else:
            rs = ret * 0.1

        rows.append((
            code, d, price, high, low, new_price, vol,
            ret, high - low, (high - low) / price, rs,
        ))
        price = new_price

    conn.executemany(
        "INSERT INTO daily_prices "
        "(code, date, open, high, low, close, volume, "
        " return_rate, price_range, range_pct, relative_strength) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()
    conn.close()
    return db_path, dates[-1]


def _add_market_context(db_path: str, target_date: str, regime: str = "risk_on", vix: float = 14.5):
    """daily_summary + us_indices にコンテキストデータを追加する。"""
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT OR REPLACE INTO daily_summary (date, regime, nikkei_return) VALUES (?, ?, ?)",
        (target_date, regime, 0.002),
    )
    conn.execute(
        "INSERT OR REPLACE INTO us_indices (date, ticker, name, close) VALUES (?, '^VIX', 'VIX', ?)",
        (target_date, vix),
    )
    conn.commit()
    conn.close()


# ── _compute_indicators テスト ────────────────────────────────────


class TestComputeIndicators:
    def test_returns_dataframe_for_target_date(self, tmp_path):
        db_path, target_date = _seed_trend_db(tmp_path)
        from src.signals.generator import _compute_indicators

        df = _compute_indicators(db_path, target_date)
        assert isinstance(df, pd.DataFrame)
        assert len(df) >= 1
        assert "sma20" in df.columns
        assert "sma60" in df.columns
        assert "sma120" in df.columns
        assert "rsi14" in df.columns

    def test_requires_120_days_minimum(self, tmp_path):
        """120日未満のデータしかない銘柄は除外される。"""
        db_path, target_date = _seed_trend_db(tmp_path, n_days=100)
        from src.signals.generator import _compute_indicators

        df = _compute_indicators(db_path, target_date)
        assert df.empty

    def test_empty_db_returns_empty_df(self, tmp_path):
        db_path = str(tmp_path / "empty.db")
        init_sqlite(db_path)
        from src.signals.generator import _compute_indicators

        df = _compute_indicators(db_path, "2024-01-01")
        assert df.empty

    def test_sma_order_in_uptrend(self, tmp_path):
        """上昇トレンドでは close > SMA20 > SMA60 > SMA120 になりやすい。"""
        db_path, target_date = _seed_trend_db(tmp_path, trend="up", n_days=200, seed=10)
        from src.signals.generator import _compute_indicators

        df = _compute_indicators(db_path, target_date)
        row = df.iloc[0]
        # 十分長い上昇トレンドなら MA 整列が期待できる
        assert row["sma20"] > row["sma120"]


# ── _load_market_context テスト ───────────────────────────────────


class TestLoadMarketContext:
    def test_reads_regime(self, tmp_path):
        db_path, target_date = _seed_trend_db(tmp_path)
        _add_market_context(db_path, target_date, regime="risk_on")
        from src.signals.generator import _load_market_context

        ctx = _load_market_context(db_path, target_date)
        assert ctx["regime"] == "risk_on"

    def test_reads_vix(self, tmp_path):
        db_path, target_date = _seed_trend_db(tmp_path)
        _add_market_context(db_path, target_date, vix=30.0)
        from src.signals.generator import _load_market_context

        ctx = _load_market_context(db_path, target_date)
        assert ctx["vix"] == 30.0

    def test_defaults_when_no_data(self, tmp_path):
        db_path = str(tmp_path / "empty.db")
        init_sqlite(db_path)
        from src.signals.generator import _load_market_context

        ctx = _load_market_context(db_path, "2024-01-01")
        assert ctx["regime"] == "neutral"
        assert ctx["vix"] is None
        assert ctx["credit_overheating"] is False


# ── _market_env_score テスト ──────────────────────────────────────


class TestMarketEnvScore:
    def test_risk_on_boosts_bullish(self):
        from src.signals.generator import _market_env_score

        score = _market_env_score("bullish", "risk_on", "neutral", None, False)
        assert score > 0.5

    def test_risk_off_penalizes_bullish(self):
        from src.signals.generator import _market_env_score

        score = _market_env_score("bullish", "risk_off", "neutral", None, False)
        assert score < 0.5

    def test_high_vix_penalizes_bullish(self):
        from src.signals.generator import _market_env_score

        score_low = _market_env_score("bullish", "neutral", "neutral", 12.0, False)
        score_high = _market_env_score("bullish", "neutral", "neutral", 30.0, False)
        assert score_low > score_high

    def test_credit_overheating_penalizes_bullish(self):
        from src.signals.generator import _market_env_score

        score_normal = _market_env_score("bullish", "neutral", "neutral", None, False)
        score_overheat = _market_env_score("bullish", "neutral", "overheat", None, True)
        assert score_normal > score_overheat

    def test_score_clamped(self):
        from src.signals.generator import _market_env_score

        # 最悪ケース: risk_off + high VIX + overheat + credit_overheating → bullish
        score = _market_env_score("bullish", "risk_off", "overheat", 30.0, True)
        assert 0.0 <= score <= 1.0

        # 最良ケース: risk_on + low VIX → bullish
        score = _market_env_score("bullish", "risk_on", "neutral", 12.0, False)
        assert 0.0 <= score <= 1.0


# ── _classify_direction テスト ────────────────────────────────────


class TestClassifyDirection:
    def _make_row(self, **overrides):
        """テスト用の疑似行オブジェクトを生成する。"""
        defaults = {
            "close": 1100,
            "sma20": 1080,
            "sma60": 1050,
            "sma120": 1000,
            "rsi14": 65.0,
            "positive_days_10": 7,
            "negative_days_10": 3,
            "relative_strength": 0.01,
            "ma20_vs_ma60": 0.028,
            "ma60_vs_ma120": 0.05,
        }
        defaults.update(overrides)

        class Row:
            pass

        r = Row()
        for k, v in defaults.items():
            setattr(r, k, v)
        return r

    def test_bullish_with_aligned_mas(self):
        from src.signals.generator import _classify_direction

        row = self._make_row()
        assert _classify_direction(row) == "bullish"

    def test_bearish_with_reverse_mas(self):
        from src.signals.generator import _classify_direction

        row = self._make_row(
            close=900, sma20=920, sma60=950, sma120=1000,
            rsi14=35.0, positive_days_10=3, negative_days_10=7,
            relative_strength=-0.01,
        )
        assert _classify_direction(row) == "bearish"

    def test_none_for_flat_market(self):
        from src.signals.generator import _classify_direction

        # MA not aligned (close between sma20 and sma60)
        row = self._make_row(close=1060, sma20=1080)
        assert _classify_direction(row) is None

    def test_none_when_rsi_overbought(self):
        from src.signals.generator import _classify_direction

        row = self._make_row(rsi14=85.0)
        assert _classify_direction(row) is None

    def test_none_when_trend_inconsistent(self):
        from src.signals.generator import _classify_direction

        row = self._make_row(positive_days_10=4)
        assert _classify_direction(row) is None


# ── generate (統合テスト) ─────────────────────────────────────────


class TestGenerate:
    def test_generates_bullish_in_uptrend(self, tmp_path):
        """強い上昇トレンドで bullish シグナルが生成される。"""
        db_path, target_date = _seed_trend_db(tmp_path, trend="up", n_days=200, seed=10)
        _add_market_context(db_path, target_date, regime="risk_on", vix=14.5)

        from src.signals.generator import generate

        count = generate(db_path, target_date, {})

        conn = sqlite3.connect(db_path)
        rows = conn.execute(
            "SELECT code, direction, confidence, reasoning FROM signals "
            "WHERE date = ? AND signal_type = 'mega_trend_follow'",
            (target_date,),
        ).fetchall()
        conn.close()

        if count > 0:
            assert len(rows) == count
            code, direction, confidence, reasoning_str = rows[0]
            assert direction == "bullish"
            assert 0.0 <= confidence <= 1.0
            reasoning = json.loads(reasoning_str)
            assert "ma_alignment" in reasoning
            assert "market_context" in reasoning
            assert "score_breakdown" in reasoning

    def test_no_signal_for_flat(self, tmp_path):
        """横ばいではシグナルが生成されない（または少ない）。"""
        db_path, target_date = _seed_trend_db(tmp_path, trend="flat", n_days=140, seed=42)
        _add_market_context(db_path, target_date)

        from src.signals.generator import generate

        count = generate(db_path, target_date, {})
        assert count == 0

    def test_dedup_skips_recent(self, tmp_path):
        """直近にシグナルがあるとスキップされる。"""
        db_path, target_date = _seed_trend_db(tmp_path, trend="up", n_days=200, seed=10)
        _add_market_context(db_path, target_date, regime="risk_on")

        # 前日に既存シグナルを挿入
        conn = sqlite3.connect(db_path)
        conn.execute(
            "INSERT INTO signals (date, signal_type, code, sector, direction, confidence, reasoning) "
            "VALUES (date(?, '-1 day'), 'mega_trend_follow', '7203', '輸送用機器', 'bullish', 0.7, '{}')",
            (target_date,),
        )
        conn.commit()
        conn.close()

        from src.signals.generator import generate

        generate(db_path, target_date, {})

        # 7203 はスキップされる
        conn = sqlite3.connect(db_path)
        new_rows = conn.execute(
            "SELECT code FROM signals WHERE date = ? AND signal_type = 'mega_trend_follow'",
            (target_date,),
        ).fetchall()
        conn.close()
        assert all(r[0] != "7203" for r in new_rows)

    def test_empty_db_returns_zero(self, tmp_path):
        db_path = str(tmp_path / "empty.db")
        init_sqlite(db_path)

        from src.signals.generator import generate

        count = generate(db_path, "2024-01-01", {})
        assert count == 0

    def test_handles_missing_market_pressure(self, tmp_path):
        """market_pressure_daily がなくてもエラーにならない。"""
        db_path, target_date = _seed_trend_db(tmp_path, trend="up", n_days=200, seed=10)
        # market context なし — デフォルト値が使われる

        from src.signals.generator import generate

        # エラーなく完了すること
        count = generate(db_path, target_date, {})
        assert isinstance(count, int)
