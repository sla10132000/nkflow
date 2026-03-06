"""fetch.py のテスト (モック使用)"""
import sqlite3
import sys
import os
from unittest.mock import MagicMock, patch, call

import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scripts.init_sqlite import init_sqlite


@pytest.fixture
def db_conn(tmp_path):
    """テスト用インメモリ SQLite (スキーマ初期化済み)"""
    db_path = str(tmp_path / "test.db")
    init_sqlite(db_path)
    conn = sqlite3.connect(db_path)
    yield conn
    conn.close()


@pytest.fixture
def mock_client():
    """J-Quants APIクライアントのモック"""
    client = MagicMock()

    # listed_info のレスポンス
    client.get_listed_info.return_value = pd.DataFrame({
        "Code": ["72030", "67580", "69020"],
        "CompanyName": ["トヨタ自動車", "ソニーグループ", "デンソー"],
        "Sector33CodeName": ["輸送用機器", "電気機器", "輸送用機器"],
        "MarketCode": ["0111", "0111", "0111"],
    })

    # 取引日のレスポンス
    client.get_prices_daily_quotes.return_value = pd.DataFrame({
        "Code": ["72030", "67580", "69020"],
        "Date": ["2025-01-06", "2025-01-06", "2025-01-06"],
        "Open": [3000.0, 2500.0, 1800.0],
        "High": [3050.0, 2540.0, 1830.0],
        "Low": [2980.0, 2480.0, 1790.0],
        "Close": [3020.0, 2510.0, 1810.0],
        "Volume": [5000000, 3000000, 2000000],
    })

    return client


class TestSyncStockMaster:
    def test_registers_prime_market_stocks(self, db_conn, mock_client):
        from src.ingestion.jquants import sync_stock_master

        count = sync_stock_master(db_conn, client=mock_client)

        assert count == 3
        rows = db_conn.execute("SELECT code, name, sector FROM stocks ORDER BY code").fetchall()
        assert len(rows) == 3
        codes = [r[0] for r in rows]
        assert "7203" in codes
        assert "6758" in codes

    def test_normalizes_5digit_code(self, db_conn, mock_client):
        from src.ingestion.jquants import sync_stock_master

        sync_stock_master(db_conn, client=mock_client)

        codes = [r[0] for r in db_conn.execute("SELECT code FROM stocks").fetchall()]
        # 末尾の "0" が除去されて4桁になっている
        assert all(len(c) == 4 for c in codes)

    def test_filters_non_prime_market(self, db_conn, mock_client):
        """プライム市場以外の銘柄は登録されない"""
        mock_client.get_listed_info.return_value = pd.DataFrame({
            "Code": ["72030", "99990"],
            "CompanyName": ["トヨタ自動車", "スタンダード株"],
            "Sector33CodeName": ["輸送用機器", "その他"],
            "MarketCode": ["0111", "0121"],  # 0121 = Standard
        })
        from src.ingestion.jquants import sync_stock_master

        count = sync_stock_master(db_conn, client=mock_client)

        assert count == 1

    def test_upserts_existing_stock(self, db_conn, mock_client):
        """既存銘柄はINSERT OR REPLACEで上書きされる"""
        from src.ingestion.jquants import sync_stock_master

        sync_stock_master(db_conn, client=mock_client)

        mock_client.get_listed_info.return_value = pd.DataFrame({
            "Code": ["72030"],
            "CompanyName": ["トヨタ自動車(変更後)"],
            "Sector33CodeName": ["輸送用機器"],
            "MarketCode": ["0111"],
        })
        sync_stock_master(db_conn, client=mock_client)

        row = db_conn.execute("SELECT name FROM stocks WHERE code='7203'").fetchone()
        assert row[0] == "トヨタ自動車(変更後)"

    def test_empty_response_returns_zero(self, db_conn, mock_client):
        mock_client.get_listed_info.return_value = pd.DataFrame()
        from src.ingestion.jquants import sync_stock_master

        count = sync_stock_master(db_conn, client=mock_client)
        assert count == 0


class TestFetchDaily:
    def test_inserts_ohlcv_rows(self, db_conn, mock_client):
        from src.ingestion.jquants import fetch_daily

        # 先にマスタを登録
        db_conn.executemany(
            "INSERT INTO stocks VALUES (?, ?, ?)",
            [("7203", "トヨタ自動車", "輸送用機器"),
             ("6758", "ソニーグループ", "電気機器"),
             ("6902", "デンソー", "輸送用機器")],
        )
        db_conn.commit()

        count = fetch_daily(db_conn, target_date="2025-01-06", client=mock_client)

        assert count == 3
        rows = db_conn.execute(
            "SELECT code, open, close FROM daily_prices ORDER BY code"
        ).fetchall()
        assert len(rows) == 3
        assert rows[0] == ("6758", 2500.0, 2510.0)

    def test_non_trading_day_returns_zero(self, db_conn, mock_client):
        """取引日でない場合は0を返す"""
        mock_client.get_prices_daily_quotes.return_value = pd.DataFrame()
        db_conn.executemany(
            "INSERT INTO stocks VALUES (?, ?, ?)",
            [("7203", "トヨタ", "輸送用機器")],
        )
        db_conn.commit()

        from src.ingestion.jquants import fetch_daily

        count = fetch_daily(db_conn, target_date="2025-01-04", client=mock_client)
        assert count == 0

    def test_syncs_master_if_empty(self, db_conn, mock_client):
        """stocks テーブルが空なら自動的に sync_stock_master を呼ぶ"""
        from src.ingestion.jquants import fetch_daily

        count = fetch_daily(db_conn, target_date="2025-01-06", client=mock_client)

        # マスタ同期 + 日次データ挿入が両方行われる
        assert mock_client.get_listed_info.call_count == 1
        assert count > 0

    def test_only_registered_stocks_inserted(self, db_conn, mock_client):
        """stocks マスタにない銘柄はスキップされる"""
        # 7203 のみ登録
        db_conn.execute("INSERT INTO stocks VALUES ('7203', 'トヨタ', '輸送用機器')")
        db_conn.commit()

        from src.ingestion.jquants import fetch_daily

        count = fetch_daily(db_conn, target_date="2025-01-06", client=mock_client)

        assert count == 1
        rows = db_conn.execute("SELECT code FROM daily_prices").fetchall()
        assert rows[0][0] == "7203"

    def test_computed_columns_are_null(self, db_conn, mock_client):
        """計算カラムは NULL (compute.py で後から埋める)"""
        db_conn.executemany(
            "INSERT INTO stocks VALUES (?, ?, ?)",
            [("7203", "トヨタ", "輸送用機器")],
        )
        db_conn.commit()

        from src.ingestion.jquants import fetch_daily

        fetch_daily(db_conn, target_date="2025-01-06", client=mock_client)

        row = db_conn.execute(
            "SELECT return_rate, price_range, range_pct, relative_strength "
            "FROM daily_prices WHERE code='7203'"
        ).fetchone()
        assert all(v is None for v in row)


class TestRawSave:
    @patch("src.pipeline.raw_store.save_raw")
    def test_sync_stock_master_saves_raw(self, mock_save_raw, db_conn, mock_client):
        mock_save_raw.return_value = "raw/jquants/stock_master/2026-03-06.json"
        from src.ingestion.jquants import sync_stock_master

        sync_stock_master(db_conn, client=mock_client)

        mock_save_raw.assert_called_once()
        args = mock_save_raw.call_args
        assert args[0][0] == "jquants"
        assert args[0][1] == "stock_master"
        # payload は DataFrame
        assert isinstance(args[0][3], pd.DataFrame)

    @patch("src.pipeline.raw_store.save_raw")
    def test_fetch_daily_saves_raw(self, mock_save_raw, db_conn, mock_client):
        mock_save_raw.return_value = "raw/jquants/daily_prices/2025-01-06.json"
        db_conn.executemany(
            "INSERT INTO stocks VALUES (?, ?, ?)",
            [("7203", "トヨタ", "輸送用機器"),
             ("6758", "ソニー", "電気機器"),
             ("6902", "デンソー", "輸送用機器")],
        )
        db_conn.commit()

        from src.ingestion.jquants import fetch_daily

        fetch_daily(db_conn, target_date="2025-01-06", client=mock_client)

        mock_save_raw.assert_called_once()
        args = mock_save_raw.call_args
        assert args[0][0] == "jquants"
        assert args[0][1] == "daily_prices"
        assert args[0][2] == "2025-01-06"

    @patch("src.pipeline.raw_store.save_raw")
    def test_fetch_daily_no_raw_on_non_trading_day(self, mock_save_raw, db_conn, mock_client):
        mock_client.get_prices_daily_quotes.return_value = pd.DataFrame()
        db_conn.execute("INSERT INTO stocks VALUES ('7203', 'トヨタ', '輸送用機器')")
        db_conn.commit()

        from src.ingestion.jquants import fetch_daily

        fetch_daily(db_conn, target_date="2025-01-04", client=mock_client)

        mock_save_raw.assert_not_called()
