"""td_sequential.py のテスト"""
import os
import sqlite3
import sys
from datetime import date, timedelta

import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scripts.init_sqlite import init_sqlite
from src.batch.td_sequential import (
    COUNTDOWN_COUNT,
    SETUP_COUNT,
    _compute_td_for_stock,
    backfill_td_sequential,
    compute_td_sequential,
)


# ── ヘルパー ──────────────────────────────────────────────────────────────────

def _make_df(prices: list[tuple]) -> pd.DataFrame:
    """(date, open, high, low, close) のリストから DataFrame を生成"""
    return pd.DataFrame(prices, columns=["date", "open", "high", "low", "close"])


def _prices_descending(n: int, start: str = "2025-01-06", start_close: float = 1000.0, step: float = 5.0) -> list[tuple]:
    """close[i] < close[i-4] が常に成立する価格系列 (強気セットアップ用)"""
    prices = []
    close = start_close
    base = date.fromisoformat(start)
    for i in range(n):
        d = (base + timedelta(days=i)).isoformat()
        close -= step
        prices.append((d, close + 2, close + 4, close - 1, close))
    return prices


def _prices_ascending(n: int, start: str = "2025-01-06", start_close: float = 1000.0, step: float = 5.0) -> list[tuple]:
    """close[i] > close[i-4] が常に成立する価格系列 (弱気セットアップ用)"""
    prices = []
    close = start_close
    base = date.fromisoformat(start)
    for i in range(n):
        d = (base + timedelta(days=i)).isoformat()
        close += step
        prices.append((d, close - 2, close + 4, close - 4, close))
    return prices


@pytest.fixture
def db_path(tmp_path):
    """強気セットアップが完成する価格データ入りの SQLite パス"""
    path = str(tmp_path / "test.db")
    init_sqlite(path)

    conn = sqlite3.connect(path)
    conn.execute("INSERT INTO stocks VALUES ('7203', 'トヨタ自動車', '輸送用機器')")

    rows = []
    close = 2000.0
    base = date(2025, 1, 6)
    for i in range(20):
        d = (base + timedelta(days=i)).isoformat()
        close -= 10.0
        rows.append(("7203", d, close + 5, close + 10, close - 5, close, 1_000_000, None, None, None, None))

    conn.executemany(
        "INSERT INTO daily_prices "
        "(code, date, open, high, low, close, volume, "
        " return_rate, price_range, range_pct, relative_strength) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        rows,
    )
    conn.commit()
    conn.close()
    return path


# ── TestComputeTdForStock (単体) ──────────────────────────────────────────────

class TestComputeTdForStock:
    def test_empty_df_returns_empty(self):
        df = _make_df([])
        result = _compute_td_for_stock(df)
        assert len(result) == 0

    def test_first_four_bars_have_zero_setup(self):
        """最初の4バーは close[i-4] 参照不可 → setup は全て 0"""
        df = _make_df(_prices_descending(10))
        result = _compute_td_for_stock(df)

        for i in range(4):
            assert result.iloc[i]["setup_bull"] == 0
            assert result.iloc[i]["setup_bear"] == 0

    def test_bull_setup_increments_1_to_9(self):
        """強気セットアップが index 4 から始まり 12 で 9 に達する"""
        df = _make_df(_prices_descending(15))
        result = _compute_td_for_stock(df)

        assert result.iloc[4]["setup_bull"] == 1
        assert result.iloc[5]["setup_bull"] == 2
        assert result.iloc[8]["setup_bull"] == 5
        assert result.iloc[12]["setup_bull"] == SETUP_COUNT  # 9

    def test_bull_setup_clips_at_9(self):
        """setup_bull は 9 を超えない"""
        df = _make_df(_prices_descending(20))
        result = _compute_td_for_stock(df)

        for i in range(12, 20):
            assert result.iloc[i]["setup_bull"] == SETUP_COUNT

    def test_bear_setup_increments_1_to_9(self):
        """弱気セットアップが同様に 1〜9 をカウントする"""
        df = _make_df(_prices_ascending(15))
        result = _compute_td_for_stock(df)

        assert result.iloc[4]["setup_bear"] == 1
        assert result.iloc[12]["setup_bear"] == SETUP_COUNT

    def test_setup_resets_on_condition_break(self):
        """条件が崩れるとカウントがリセットされる"""
        # 7バー下落 → 1バー横ばい (close == close[-4]) → リセット
        prices = _prices_descending(7)
        # close == close[-4] になる flat バーを1本挿入
        last_close = prices[-1][-1]
        d = (date.fromisoformat(prices[-1][0]) + timedelta(days=1)).isoformat()
        prices.append((d, last_close + 2, last_close + 3, last_close - 1, last_close + 20))  # 大幅上昇 → bear に
        df = _make_df(prices)
        result = _compute_td_for_stock(df)

        # index 6 まで bull が進んでいる (最大3カウント = index4,5,6)
        assert result.iloc[6]["setup_bull"] == 3
        # 上昇バーでリセット
        assert result.iloc[7]["setup_bull"] == 0

    def test_bull_countdown_starts_after_setup_9(self):
        """強気セットアップ 9 完成後にカウントダウンが開始される"""
        df = _make_df(_prices_descending(30))
        result = _compute_td_for_stock(df)

        assert result.iloc[12]["setup_bull"] == SETUP_COUNT
        # 完成後のいずれかのバーで countdown_bull > 0 になるはず
        assert result.iloc[13:]["countdown_bull"].max() > 0

    def test_bear_countdown_cancelled_by_bull_setup(self):
        """弱気 Countdown 中に強気 Setup 9 が完成すると弱気 Countdown がキャンセルされる"""
        # 弱気セットアップ完成 (15バー上昇)
        prices = _prices_ascending(15)
        # 続いて強気セットアップ完成 (15バー下落)
        last_close = prices[-1][-1]
        base = date.fromisoformat(prices[-1][0]) + timedelta(days=1)
        for i in range(20):
            d = (base + timedelta(days=i)).isoformat()
            last_close -= 5.0
            prices.append((d, last_close + 2, last_close + 4, last_close - 1, last_close))

        df = _make_df(prices)
        result = _compute_td_for_stock(df)

        # 強気 Setup 9 が完成する行 (初出) 以降で countdown_bear == 0 になる
        bull9_idx = result[result["setup_bull"] == SETUP_COUNT].index
        if len(bull9_idx) > 0:
            first_bull9 = bull9_idx[0]
            assert result.iloc[first_bull9]["countdown_bear"] == 0

    def test_countdown_bull_reaches_13(self):
        """
        強気カウントダウン条件 close[i] <= low[i-2] が毎バー成立する場合、
        13 に到達する
        """
        # セットアップ完成 (15バー急落) → カウントダウン条件が毎バー成立する急落を続ける
        prices = []
        close = 2000.0
        base = date(2025, 1, 6)

        # セットアップ フェーズ: 15バー下落
        for i in range(15):
            d = (base + timedelta(days=i)).isoformat()
            close -= 10.0
            prices.append((d, close + 2, close + 4, close - 1, close))

        # カウントダウン フェーズ: さらに急落 → close[i] <= low[i-2] を常に成立させる
        # low[i] = close - 1 として、close は毎バー low[i-2] = prev_prev_close - 1 以下にする
        for i in range(15, 40):
            d = (base + timedelta(days=i)).isoformat()
            close -= 20.0   # 急落 → close が 2バー前の low を確実に下回る
            low = close - 1
            prices.append((d, close + 2, close + 4, low, close))

        df = _make_df(prices)
        result = _compute_td_for_stock(df)

        assert result["countdown_bull"].max() == COUNTDOWN_COUNT


# ── TestComputeTdSequential (統合) ───────────────────────────────────────────

class TestComputeTdSequential:
    def test_upserts_target_date(self, db_path):
        """compute_td_sequential が target_date の行を UPSERT する"""
        conn = sqlite3.connect(db_path)
        target = conn.execute(
            "SELECT MAX(date) FROM daily_prices WHERE code = '7203'"
        ).fetchone()[0]
        conn.close()

        count = compute_td_sequential(db_path, target)
        assert count == 1

        conn = sqlite3.connect(db_path)
        row = conn.execute(
            "SELECT * FROM td_sequential WHERE code = '7203' AND date = ?",
            (target,),
        ).fetchone()
        conn.close()
        assert row is not None

    def test_no_data_returns_zero(self, db_path):
        """対象日にデータがない場合は 0 を返す"""
        count = compute_td_sequential(db_path, "2099-01-01")
        assert count == 0

    def test_upsert_is_idempotent(self, db_path):
        """2回実行しても DB に重複行が発生しない"""
        conn = sqlite3.connect(db_path)
        target = conn.execute(
            "SELECT MAX(date) FROM daily_prices WHERE code = '7203'"
        ).fetchone()[0]
        conn.close()

        compute_td_sequential(db_path, target)
        compute_td_sequential(db_path, target)

        conn = sqlite3.connect(db_path)
        count_in_db = conn.execute(
            "SELECT COUNT(*) FROM td_sequential WHERE code = '7203' AND date = ?",
            (target,),
        ).fetchone()[0]
        conn.close()
        assert count_in_db == 1


# ── TestBackfillTdSequential (統合) ─────────────────────────────────────────

class TestBackfillTdSequential:
    def test_backfills_all_dates(self, db_path):
        """backfill_td_sequential が全日付を埋める"""
        conn = sqlite3.connect(db_path)
        total_price_rows = conn.execute(
            "SELECT COUNT(*) FROM daily_prices WHERE code = '7203'"
        ).fetchone()[0]
        conn.close()

        backfill_td_sequential(db_path)

        conn = sqlite3.connect(db_path)
        total_tds_rows = conn.execute(
            "SELECT COUNT(*) FROM td_sequential WHERE code = '7203'"
        ).fetchone()[0]
        conn.close()

        assert total_tds_rows == total_price_rows

    def test_values_within_bounds(self, db_path):
        """setup は 0-9、countdown は 0-13 の範囲に収まる"""
        backfill_td_sequential(db_path)

        conn = sqlite3.connect(db_path)
        rows = conn.execute("SELECT * FROM td_sequential").fetchall()
        conn.close()

        for row in rows:
            code, d, sb, ss, cb, cs = row
            assert 0 <= sb <= 9,  f"setup_bull 範囲外: {sb}"
            assert 0 <= ss <= 9,  f"setup_bear 範囲外: {ss}"
            assert 0 <= cb <= 13, f"countdown_bull 範囲外: {cb}"
            assert 0 <= cs <= 13, f"countdown_bear 範囲外: {cs}"
