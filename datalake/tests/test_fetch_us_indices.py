"""fetch_us_indices のテスト (Yahoo Finance モック + SQLite)"""
import sqlite3
import sys
import os
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scripts.init_sqlite import init_sqlite


# Yahoo Finance レスポンス例 (^GSPC 3日分)
FAKE_YAHOO_RESPONSE = {
    "chart": {
        "result": [{
            "timestamp": [1735689600, 1735776000, 1735862400],  # 2025-01-01〜03
            "indicators": {
                "quote": [{
                    "open":   [4700.0, 4710.0, 4720.0],
                    "high":   [4750.0, 4760.0, 4770.0],
                    "low":    [4680.0, 4690.0, 4700.0],
                    "close":  [4720.0, 4730.0, 4740.0],
                    "volume": [3000000000, 3100000000, 3200000000],
                }]
            }
        }]
    }
}


@pytest.fixture
def db_path(tmp_path):
    """テスト用 SQLite (us_indices スキーマ込み)"""
    path = str(tmp_path / "test.db")
    init_sqlite(path)
    return path


def _mock_get_ok():
    mock_resp = MagicMock()
    mock_resp.json.return_value = FAKE_YAHOO_RESPONSE
    mock_resp.raise_for_status.return_value = None
    return mock_resp


class TestFetchUsIndices:
    def test_creates_table(self, db_path):
        """空のDBに対して実行しても us_indices テーブルが存在すること"""
        with patch("requests.get") as mock_get:
            mock_get.return_value = _mock_get_ok()
            from src.ingestion.yahoo_finance import fetch_us_indices
            fetch_us_indices(db_path)

        conn = sqlite3.connect(db_path)
        tables = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()]
        conn.close()
        assert "us_indices" in tables

    def test_inserts_data(self, db_path):
        """15ティッカー (US 3 + VIX 1 + セクター ETF 11) × 3日 = 45行が挿入されること"""
        with patch("requests.get") as mock_get:
            mock_get.return_value = _mock_get_ok()
            from src.ingestion.yahoo_finance import fetch_us_indices
            result = fetch_us_indices(db_path)

        conn = sqlite3.connect(db_path)
        count = conn.execute("SELECT COUNT(*) FROM us_indices").fetchone()[0]
        conn.close()

        # 15 tickers (^GSPC, ^DJI, ^IXIC, ^VIX + 11 sector ETFs) × 3 rows each
        assert count == 45
        assert result["rows_inserted"] == 45
        assert len(result["tickers"]) == 15

    def test_incremental_update(self, db_path):
        """既存データがある場合、差分のみ取得して重複しないこと"""
        conn = sqlite3.connect(db_path)
        conn.executemany(
            "INSERT INTO us_indices (date, ticker, name, open, high, low, close, volume) VALUES (?,?,?,?,?,?,?,?)",
            [
                ("2025-01-01", "^GSPC", "S&P 500", 4700.0, 4750.0, 4680.0, 4720.0, 3000000000),
            ],
        )
        conn.commit()
        conn.close()

        with patch("requests.get") as mock_get:
            mock_get.return_value = _mock_get_ok()
            from src.ingestion.yahoo_finance import fetch_us_indices
            result = fetch_us_indices(db_path)

        conn = sqlite3.connect(db_path)
        gspc_count = conn.execute(
            "SELECT COUNT(*) FROM us_indices WHERE ticker='^GSPC'"
        ).fetchone()[0]
        conn.close()

        # 2025-01-01 は既存、01-02・01-03 が新規 → 合計3行
        assert gspc_count == 3
        # 新規挿入は01-02, 01-03 の2行 (^GSPC) + 他14ティッカー × 3行
        assert result["rows_inserted"] <= 44  # 2 for ^GSPC + 3*14 for others

    def test_handles_error_gracefully(self, db_path):
        """yfinance エラー時に例外を投げず、status=ok を返すこと"""
        with patch("requests.get") as mock_get:
            mock_get.side_effect = Exception("connection timeout")
            from src.ingestion.yahoo_finance import fetch_us_indices
            result = fetch_us_indices(db_path)

        assert result["status"] == "ok"
        assert result["rows_inserted"] == 0

    @patch("src.pipeline.raw_store.save_raw")
    def test_saves_raw_data(self, mock_save_raw, db_path):
        """raw データが S3 に保存されること"""
        mock_save_raw.return_value = "raw/market/index/yahoo_finance/us_indices/2026-03-06.json"
        with patch("requests.get") as mock_get:
            mock_get.return_value = _mock_get_ok()
            from src.ingestion.yahoo_finance import fetch_us_indices
            fetch_us_indices(db_path)

        mock_save_raw.assert_called_once()
        args = mock_save_raw.call_args[0]
        assert args[0] == "market"
        assert args[1] == "index"
        assert args[2] == "yahoo_finance"
        assert args[3] == "us_indices"
        assert isinstance(args[5], dict)  # {ticker: [records]}
        assert len(args[5]) == 15  # 15 tickers
