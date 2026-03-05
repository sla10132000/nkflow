"""セクター ETF 取得テスト (Phase 23b)"""
import sqlite3
import sys
import os
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scripts.init_sqlite import init_sqlite

FAKE_YAHOO_RESPONSE = {
    "chart": {
        "result": [{
            "timestamp": [1735689600, 1735776000, 1735862400],  # 2025-01-01〜03
            "indicators": {
                "quote": [{
                    "open":   [220.0, 221.0, 222.0],
                    "high":   [225.0, 226.0, 227.0],
                    "low":    [218.0, 219.0, 220.0],
                    "close":  [222.0, 223.0, 224.0],
                    "volume": [12000000, 12500000, 13000000],
                }]
            }
        }]
    }
}


@pytest.fixture
def db_path(tmp_path):
    path = str(tmp_path / "test.db")
    init_sqlite(path)
    return path


def _mock_get_ok():
    mock_resp = MagicMock()
    mock_resp.json.return_value = FAKE_YAHOO_RESPONSE
    mock_resp.raise_for_status.return_value = None
    return mock_resp


class TestFetchUsIndicesIncludesSectorEtfs:
    def test_fetch_us_indices_includes_sector_etfs(self, db_path):
        """fetch_us_indices() がセクター ETF も取得すること"""
        with patch("requests.get") as mock_get:
            mock_get.return_value = _mock_get_ok()
            from src.batch.fetch_external import fetch_us_indices
            result = fetch_us_indices(db_path)

        # 4 指数 + 11 セクター ETF = 15 ティッカー
        assert len(result["tickers"]) == 15
        assert "XLK" in result["tickers"]
        assert "XLC" in result["tickers"]
        assert "XLRE" in result["tickers"]

    def test_sector_etf_data_in_us_indices_table(self, db_path):
        """セクター ETF データが us_indices テーブルに保存されること"""
        with patch("requests.get") as mock_get:
            mock_get.return_value = _mock_get_ok()
            from src.batch.fetch_external import fetch_us_indices
            fetch_us_indices(db_path)

        conn = sqlite3.connect(db_path)
        # 11 ETF × 3 rows = 33 rows のセクター ETF データ
        sector_etf_tickers = (
            "XLK", "XLF", "XLV", "XLE", "XLI", "XLY", "XLP", "XLU", "XLB", "XLRE", "XLC"
        )
        placeholders = ",".join("?" * len(sector_etf_tickers))
        count = conn.execute(
            f"SELECT COUNT(*) FROM us_indices WHERE ticker IN ({placeholders})",
            sector_etf_tickers,
        ).fetchone()[0]
        conn.close()
        assert count == 33  # 11 ETF × 3 rows

    def test_sector_etf_name_stored_correctly(self, db_path):
        """セクター ETF の name が正しく保存されること"""
        with patch("requests.get") as mock_get:
            mock_get.return_value = _mock_get_ok()
            from src.batch.fetch_external import fetch_us_indices
            fetch_us_indices(db_path)

        conn = sqlite3.connect(db_path)
        row = conn.execute(
            "SELECT name FROM us_indices WHERE ticker = 'XLK' LIMIT 1"
        ).fetchone()
        conn.close()
        assert row is not None
        assert "Technology" in row[0]

    def test_sector_etf_incremental_update(self, db_path):
        """既存データがある場合、差分のみ取得すること"""
        conn = sqlite3.connect(db_path)
        conn.execute(
            "INSERT INTO us_indices (date, ticker, name, open, high, low, close, volume) "
            "VALUES (?,?,?,?,?,?,?,?)",
            ("2025-01-01", "XLK", "Technology Select Sector SPDR",
             220.0, 225.0, 218.0, 222.0, 12000000),
        )
        conn.commit()
        conn.close()

        with patch("requests.get") as mock_get:
            mock_get.return_value = _mock_get_ok()
            from src.batch.fetch_external import fetch_us_indices
            fetch_us_indices(db_path)

        conn = sqlite3.connect(db_path)
        xlk_count = conn.execute(
            "SELECT COUNT(*) FROM us_indices WHERE ticker = 'XLK'"
        ).fetchone()[0]
        conn.close()
        # 2025-01-01 は既存、01-02・01-03 が新規 → 合計3行
        assert xlk_count == 3
