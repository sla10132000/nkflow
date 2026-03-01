"""fetch_external.py のテスト (Yahoo Finance モック + SQLite)"""
import sqlite3
import sys
import os
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scripts.init_sqlite import init_sqlite
from scripts.migrate_phase13 import migrate


@pytest.fixture
def db_conn(tmp_path):
    """テスト用 SQLite (Phase 13 スキーマ込み)"""
    db_path = str(tmp_path / "test.db")
    init_sqlite(db_path)
    migrate(db_path)
    conn = sqlite3.connect(db_path)
    # 銘柄マスタを投入
    conn.executemany(
        "INSERT OR REPLACE INTO stocks (code, name, sector) VALUES (?, ?, ?)",
        [
            ("7203", "トヨタ自動車", "輸送用機器"),
            ("6758", "ソニーグループ", "電気機器"),
            ("9202", "ANA", "空運業"),
        ],
    )
    conn.commit()
    yield conn
    conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# 為替レート取得テスト
# ─────────────────────────────────────────────────────────────────────────────

FAKE_YAHOO_RESPONSE = {
    "chart": {
        "result": [{
            "timestamp": [1735689600, 1735776000, 1735862400],  # 2025-01-01〜03
            "indicators": {
                "quote": [{
                    "open":  [157.0, 157.5, 158.0],
                    "high":  [157.8, 158.0, 158.5],
                    "low":   [156.5, 157.0, 157.5],
                    "close": [157.3, 157.8, 158.2],
                }]
            }
        }]
    }
}


class TestFetchExchangeRates:
    def test_inserts_rows(self, db_conn):
        """正常なレスポンスでexchange_ratesに行が挿入される"""
        from src.batch.fetch_external import fetch_exchange_rates

        with patch("requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.json.return_value = FAKE_YAHOO_RESPONSE
            mock_resp.raise_for_status.return_value = None
            mock_get.return_value = mock_resp

            rows = fetch_exchange_rates(db_conn, target_date="2025-01-04")

        assert rows > 0
        count = db_conn.execute("SELECT COUNT(*) FROM exchange_rates").fetchone()[0]
        assert count > 0

    def test_stores_pair_name(self, db_conn):
        """USDJPY として保存される"""
        from src.batch.fetch_external import fetch_exchange_rates

        with patch("requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.json.return_value = FAKE_YAHOO_RESPONSE
            mock_resp.raise_for_status.return_value = None
            mock_get.return_value = mock_resp

            fetch_exchange_rates(db_conn, target_date="2025-01-04")

        pairs = [r[0] for r in db_conn.execute("SELECT DISTINCT pair FROM exchange_rates").fetchall()]
        assert "USDJPY" in pairs

    def test_calculates_change_rate(self, db_conn):
        """変化率が計算されている"""
        from src.batch.fetch_external import fetch_exchange_rates

        with patch("requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.json.return_value = FAKE_YAHOO_RESPONSE
            mock_resp.raise_for_status.return_value = None
            mock_get.return_value = mock_resp

            fetch_exchange_rates(db_conn, target_date="2025-01-04")

        rows = db_conn.execute(
            "SELECT change_rate FROM exchange_rates WHERE pair='USDJPY' ORDER BY date"
        ).fetchall()
        # 先頭は NaN になるが、2行目以降は値がある
        non_null = [r[0] for r in rows if r[0] is not None]
        assert len(non_null) >= 1

    def test_handles_api_failure_gracefully(self, db_conn):
        """APIエラー時は 0 を返し、例外を投げない"""
        from src.batch.fetch_external import fetch_exchange_rates

        with patch("requests.get") as mock_get:
            mock_get.side_effect = Exception("connection timeout")
            rows = fetch_exchange_rates(db_conn, target_date="2025-01-04")

        assert rows == 0

    def test_idempotent_upsert(self, db_conn):
        """同じデータを2回投入しても件数が増えない"""
        from src.batch.fetch_external import fetch_exchange_rates

        with patch("requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.json.return_value = FAKE_YAHOO_RESPONSE
            mock_resp.raise_for_status.return_value = None
            mock_get.return_value = mock_resp

            fetch_exchange_rates(db_conn, target_date="2025-01-04")
            count_before = db_conn.execute("SELECT COUNT(*) FROM exchange_rates").fetchone()[0]

            mock_get.return_value = mock_resp
            fetch_exchange_rates(db_conn, target_date="2025-01-04")
            count_after = db_conn.execute("SELECT COUNT(*) FROM exchange_rates").fetchone()[0]

        assert count_before == count_after


# ─────────────────────────────────────────────────────────────────────────────
# 信用残高取得テスト
# ─────────────────────────────────────────────────────────────────────────────

class TestFetchMarginBalance:
    def _make_client(self, df: pd.DataFrame):
        """J-Quants v2 クライアントのモックを作成する"""
        import jquantsapi
        client = MagicMock(spec=jquantsapi.ClientV2)
        client.get_mkt_margin_interest.return_value = df
        return client

    def test_inserts_rows(self, db_conn):
        """正常データで margin_balances に行が挿入される"""
        from src.batch.fetch_external import fetch_margin_balance

        df = pd.DataFrame({
            "Code": ["72030", "67580"],
            "Date": ["20250110", "20250110"],
            "LongMarginTradeVolume": [1000000, 500000],
            "ShortMarginTradeVolume": [100000, 80000],
        })
        client = self._make_client(df)

        rows = fetch_margin_balance(db_conn, target_date="2025-01-10", client=client)

        assert rows == 2
        count = db_conn.execute("SELECT COUNT(*) FROM margin_balances").fetchone()[0]
        assert count == 2

    def test_calculates_margin_ratio(self, db_conn):
        """信用倍率が正しく計算される"""
        from src.batch.fetch_external import fetch_margin_balance

        df = pd.DataFrame({
            "Code": ["72030"],
            "Date": ["20250110"],
            "LongMarginTradeVolume": [1000000],
            "ShortMarginTradeVolume": [100000],
        })
        client = self._make_client(df)

        fetch_margin_balance(db_conn, target_date="2025-01-10", client=client)

        row = db_conn.execute(
            "SELECT margin_ratio FROM margin_balances WHERE code='7203'"
        ).fetchone()
        assert row is not None
        assert abs(row[0] - 10.0) < 0.01  # 1000000 / 100000 = 10.0

    def test_filters_unregistered_stocks(self, db_conn):
        """stocks テーブルに未登録の銘柄は無視される"""
        from src.batch.fetch_external import fetch_margin_balance

        df = pd.DataFrame({
            "Code": ["72030", "99990"],  # 9999は未登録
            "Date": ["20250110", "20250110"],
            "LongMarginTradeVolume": [1000000, 200000],
            "ShortMarginTradeVolume": [100000, 50000],
        })
        client = self._make_client(df)

        rows = fetch_margin_balance(db_conn, target_date="2025-01-10", client=client)

        assert rows == 1  # 7203 のみ

    def test_returns_zero_on_unavailable_method(self, db_conn):
        """margin interest APIが利用できないクライアントは0を返す"""
        from src.batch.fetch_external import fetch_margin_balance

        import jquantsapi
        client = MagicMock(spec=jquantsapi.ClientV2)
        client.get_mkt_margin_interest.side_effect = AttributeError("not available")

        rows = fetch_margin_balance(db_conn, target_date="2025-01-10", client=client)

        assert rows == 0

    def test_empty_response_returns_zero(self, db_conn):
        """空のDataFrameが返された場合は0を返す"""
        from src.batch.fetch_external import fetch_margin_balance

        client = self._make_client(pd.DataFrame())

        rows = fetch_margin_balance(db_conn, target_date="2025-01-10", client=client)

        assert rows == 0


# ─────────────────────────────────────────────────────────────────────────────
# signals.py の Phase 13 シグナルテスト
# ─────────────────────────────────────────────────────────────────────────────

class TestMarginSqueezeSignals:
    def test_generates_bearish_signal_on_high_ratio_and_decline(self, db_conn):
        """信用倍率高 + 当日下落で bearish シグナルが生成される"""
        from src.batch.signals import generate_margin_squeeze_signals

        # 信用残高投入
        db_conn.execute(
            "INSERT INTO margin_balances (code, week_date, margin_buy, margin_sell, margin_ratio) "
            "VALUES ('7203', '2025-01-06', 1000000, 80000, 12.5)"
        )
        # 当日価格 (下落)
        db_conn.execute(
            "INSERT INTO daily_prices (code, date, open, high, low, close, volume, return_rate) "
            "VALUES ('7203', '2025-01-10', 3000, 3010, 2950, 2960, 5000000, -0.013)"
        )
        db_conn.commit()

        count = generate_margin_squeeze_signals(db_conn, "2025-01-10")

        assert count == 1
        row = db_conn.execute(
            "SELECT direction, signal_type FROM signals WHERE date='2025-01-10'"
        ).fetchone()
        assert row[0] == "bearish"
        assert row[1] == "margin_squeeze"

    def test_no_signal_when_ratio_low(self, db_conn):
        """信用倍率が閾値未満なら生成しない"""
        from src.batch.signals import generate_margin_squeeze_signals

        db_conn.execute(
            "INSERT INTO margin_balances (code, week_date, margin_buy, margin_sell, margin_ratio) "
            "VALUES ('7203', '2025-01-06', 100000, 80000, 1.25)"
        )
        db_conn.execute(
            "INSERT INTO daily_prices (code, date, open, high, low, close, volume, return_rate) "
            "VALUES ('7203', '2025-01-10', 3000, 3010, 2950, 2960, 5000000, -0.013)"
        )
        db_conn.commit()

        count = generate_margin_squeeze_signals(db_conn, "2025-01-10")

        assert count == 0

    def test_no_signal_when_no_margin_data(self, db_conn):
        """信用残高データがない場合は生成しない"""
        from src.batch.signals import generate_margin_squeeze_signals

        count = generate_margin_squeeze_signals(db_conn, "2025-01-10")

        assert count == 0


class TestYenSensitivitySignals:
    def test_generates_bullish_for_exporters_on_yen_weakening(self, db_conn):
        """円安時に輸送用機器セクター銘柄に bullish シグナルが生成される"""
        from src.batch.signals import generate_yen_sensitivity_signals

        # USDJPY: 円安 (変動率 +1%)
        db_conn.execute(
            "INSERT INTO exchange_rates (date, pair, open, high, low, close, change_rate) "
            "VALUES ('2025-01-10', 'USDJPY', 157.0, 158.5, 157.0, 158.5, 0.0095)"
        )
        db_conn.commit()

        count = generate_yen_sensitivity_signals(db_conn, "2025-01-10")

        # トヨタ (輸送用機器) → bullish シグナルが生成されるはず
        assert count > 0
        rows = db_conn.execute(
            "SELECT direction, signal_type, code FROM signals WHERE date='2025-01-10'"
        ).fetchall()
        assert all(r[0] == "bullish" for r in rows)
        assert all(r[1] == "yen_sensitivity" for r in rows)
        codes = [r[2] for r in rows]
        assert "7203" in codes  # トヨタ

    def test_generates_bullish_for_airlines_on_yen_strengthening(self, db_conn):
        """円高時に空運業セクター銘柄に bullish シグナルが生成される"""
        from src.batch.signals import generate_yen_sensitivity_signals

        # USDJPY: 円高 (変動率 -0.8%)
        db_conn.execute(
            "INSERT INTO exchange_rates (date, pair, open, high, low, close, change_rate) "
            "VALUES ('2025-01-10', 'USDJPY', 158.0, 158.0, 156.5, 156.8, -0.0076)"
        )
        db_conn.commit()

        count = generate_yen_sensitivity_signals(db_conn, "2025-01-10")

        assert count > 0
        codes = [r[0] for r in db_conn.execute(
            "SELECT code FROM signals WHERE date='2025-01-10' AND signal_type='yen_sensitivity'"
        ).fetchall()]
        assert "9202" in codes  # ANA (空運業)

    def test_no_signal_below_threshold(self, db_conn):
        """変動率が閾値未満はシグナルなし"""
        from src.batch.signals import generate_yen_sensitivity_signals

        # 変動率 0.1% (< 0.5%)
        db_conn.execute(
            "INSERT INTO exchange_rates (date, pair, open, high, low, close, change_rate) "
            "VALUES ('2025-01-10', 'USDJPY', 157.0, 157.2, 156.9, 157.1, 0.001)"
        )
        db_conn.commit()

        count = generate_yen_sensitivity_signals(db_conn, "2025-01-10")

        assert count == 0

    def test_no_signal_when_no_fx_data(self, db_conn):
        """当日の為替データがない場合はシグナルなし"""
        from src.batch.signals import generate_yen_sensitivity_signals

        count = generate_yen_sensitivity_signals(db_conn, "2025-01-10")

        assert count == 0
