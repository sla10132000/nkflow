"""ingestor モジュールのユニットテスト"""
import json
import sqlite3
from unittest.mock import MagicMock, patch

import pytest

from src.ingestor.dispatcher import _REGISTRY, dispatch, register


# ─────────────────────────────────────────────────────────────
# dispatcher テスト
# ─────────────────────────────────────────────────────────────

class TestDispatcher:
    def test_register_and_dispatch(self):
        """register デコレータで登録した writer が dispatch で呼ばれること"""
        @register("test_cat", "test_src", "test_type")
        def _dummy_writer(conn, date_str, data):
            return 42

        conn = MagicMock(spec=sqlite3.Connection)
        result = dispatch(conn, "test_cat", "test_src", "test_type", "2026-03-06", [])
        assert result == 42

    def test_dispatch_unregistered_returns_zero(self):
        """未登録の (category, source, data_type) は 0 を返し例外を起こさないこと"""
        conn = MagicMock(spec=sqlite3.Connection)
        result = dispatch(conn, "unknown", "unknown", "unknown", "2026-03-06", [])
        assert result == 0


# ─────────────────────────────────────────────────────────────
# handler テスト
# ─────────────────────────────────────────────────────────────

def _make_sqs_event(s3_bucket: str, s3_key: str) -> dict:
    """SQS → Lambda に届くイベント形式のモックを生成する"""
    s3_notification = {
        "Records": [
            {
                "s3": {
                    "bucket": {"name": s3_bucket},
                    "object": {"key": s3_key},
                }
            }
        ]
    }
    return {
        "Records": [
            {"body": json.dumps(s3_notification)}
        ]
    }


def _make_envelope(category, source, data_type, date_str, data) -> dict:
    return {
        "category": category,
        "source": source,
        "data_type": data_type,
        "date": date_str,
        "data": data,
    }


class TestHandler:
    def test_empty_records_returns_ok(self):
        """Records が空の場合は正常終了すること"""
        import src.ingestor.handler as h
        result = h.handler({"Records": []}, None)
        assert result["statusCode"] == 200

    def test_empty_s3_event_returns_ok(self):
        """S3 イベントレコードが空 (テスト通知) の場合は正常終了すること"""
        import src.ingestor.handler as h
        event = {"Records": [{"body": json.dumps({"Records": []})}]}
        result = h.handler(event, None)
        assert result["statusCode"] == 200

    @patch("src.ingestor.handler.boto3")
    @patch("src.ingestor.handler.dispatch")
    def test_handler_calls_dispatch(self, mock_dispatch, mock_boto3):
        """handler が S3 key を取得し dispatch を呼ぶこと"""
        import src.ingestor.handler as h

        envelope = _make_envelope("market", "jquants", "daily_prices", "2026-03-06", [])

        # S3 get_object のモック
        mock_s3 = MagicMock()
        mock_s3.get_object.return_value = {
            "Body": MagicMock(read=MagicMock(return_value=json.dumps(envelope).encode()))
        }
        mock_s3.download_file.return_value = None
        mock_s3.upload_file.return_value = None
        mock_boto3.client.return_value = mock_s3

        mock_dispatch.return_value = 5

        # stocks.db download をモック (ファイルが存在しなくてよいように)
        with patch("sqlite3.connect") as mock_connect:
            mock_conn = MagicMock()
            mock_connect.return_value = mock_conn
            mock_conn.execute.return_value = None
            mock_conn.commit.return_value = None

            event = _make_sqs_event("test-bucket", "raw/market/equity/jquants/daily_prices/2026-03-06.json")
            result = h.handler(event, None)

        assert result["statusCode"] == 200
        assert result["body"]["rows_written"] == 5
        mock_dispatch.assert_called_once()


# ─────────────────────────────────────────────────────────────
# daily_prices writer テスト
# ─────────────────────────────────────────────────────────────

@pytest.fixture()
def in_memory_db():
    """テスト用インメモリ SQLite (stocks + daily_prices テーブルあり)"""
    conn = sqlite3.connect(":memory:")
    conn.execute("""
        CREATE TABLE stocks (
            code TEXT PRIMARY KEY,
            name TEXT,
            sector TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE daily_prices (
            code TEXT,
            date TEXT,
            open REAL,
            high REAL,
            low REAL,
            close REAL,
            volume INTEGER,
            return_rate REAL,
            price_range REAL,
            range_pct REAL,
            relative_strength REAL,
            PRIMARY KEY (code, date)
        )
    """)
    # テスト銘柄を登録
    conn.executemany("INSERT INTO stocks (code, name, sector) VALUES (?, ?, ?)", [
        ("7203", "トヨタ自動車", "輸送用機器"),
        ("6758", "ソニーグループ", "電気機器"),
    ])
    conn.commit()
    yield conn
    conn.close()


class TestDailyPricesWriter:
    def test_write_v1_format(self, in_memory_db):
        """v1 API 形式 (Open/High/Low/Close/Volume) のデータを挿入できること"""
        from src.ingestor.writers.daily_prices import write

        data = [
            {"Code": "72030", "Date": "2026-03-06", "Open": 2500.0, "High": 2550.0,
             "Low": 2480.0, "Close": 2530.0, "Volume": 1200000},
            {"Code": "67580", "Date": "2026-03-06", "Open": 3100.0, "High": 3200.0,
             "Low": 3050.0, "Close": 3150.0, "Volume": 800000},
        ]
        rows = write(in_memory_db, "2026-03-06", data)
        assert rows == 2

        result = in_memory_db.execute("SELECT code, close FROM daily_prices ORDER BY code").fetchall()
        assert result == [("6758", 3150.0), ("7203", 2530.0)]

    def test_write_v2_format(self, in_memory_db):
        """v2 API 形式 (O/H/L/C/Vo) のデータを挿入できること"""
        from src.ingestor.writers.daily_prices import write

        data = [
            {"Code": "72030", "Date": "2026-03-06", "O": 2500.0, "H": 2550.0,
             "L": 2480.0, "C": 2530.0, "Vo": 1200000},
        ]
        rows = write(in_memory_db, "2026-03-06", data)
        assert rows == 1

        result = in_memory_db.execute("SELECT close FROM daily_prices WHERE code='7203'").fetchone()
        assert result[0] == 2530.0

    def test_computed_columns_are_null(self, in_memory_db):
        """compute.py が後から埋める計算カラムは NULL で挿入されること"""
        from src.ingestor.writers.daily_prices import write

        data = [{"Code": "72030", "Date": "2026-03-06", "Open": 2500.0, "High": 2550.0,
                 "Low": 2480.0, "Close": 2530.0, "Volume": 1200000}]
        write(in_memory_db, "2026-03-06", data)

        row = in_memory_db.execute(
            "SELECT return_rate, price_range, range_pct, relative_strength FROM daily_prices WHERE code='7203'"
        ).fetchone()
        assert all(v is None for v in row)

    def test_unregistered_code_is_skipped(self, in_memory_db):
        """stocks テーブルに存在しない銘柄は挿入されないこと"""
        from src.ingestor.writers.daily_prices import write

        data = [{"Code": "99990", "Date": "2026-03-06", "Open": 100.0, "High": 110.0,
                 "Low": 90.0, "Close": 105.0, "Volume": 500}]
        rows = write(in_memory_db, "2026-03-06", data)
        assert rows == 0

    def test_empty_data_returns_zero(self, in_memory_db):
        """data が空のときは 0 を返すこと"""
        from src.ingestor.writers.daily_prices import write

        rows = write(in_memory_db, "2026-03-06", [])
        assert rows == 0

    def test_insert_or_replace(self, in_memory_db):
        """同じ (code, date) への再挿入は REPLACE されること"""
        from src.ingestor.writers.daily_prices import write

        data = [{"Code": "72030", "Date": "2026-03-06", "Open": 2500.0, "High": 2550.0,
                 "Low": 2480.0, "Close": 2530.0, "Volume": 1200000}]
        write(in_memory_db, "2026-03-06", data)

        # close を変えて再挿入
        data[0]["Close"] = 9999.0
        rows = write(in_memory_db, "2026-03-06", data)
        assert rows == 1

        result = in_memory_db.execute("SELECT close FROM daily_prices WHERE code='7203'").fetchone()
        assert result[0] == 9999.0
