"""
pytest 設定: テスト実行前にダミー環境変数をセットする。
src/config.py の os.environ["S3_BUCKET"] などが KeyError を起こさないようにする。
"""
import os
import sqlite3
import sys

import pytest

# テスト用ダミー環境変数
os.environ.setdefault("S3_BUCKET", "test-hazardbrief-bucket")
os.environ.setdefault("REINFOLIB_API_KEY", "test-api-key")

# src/ と lib/ を Python パスに追加
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture
def db_path(tmp_path):
    """テスト用 SQLite DB を初期化して返す。"""
    path = str(tmp_path / "hazardbrief.db")
    from scripts.init_sqlite import init_sqlite
    init_sqlite(path)
    return path


@pytest.fixture
def db_conn(db_path):
    """テスト用 SQLite 接続を返す。"""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    yield conn
    conn.close()


@pytest.fixture
def db_with_property(db_conn, db_path, monkeypatch):
    """会社・物件・プロファイルが入ったDBを返す。"""
    monkeypatch.setenv("SQLITE_PATH", db_path)
    monkeypatch.setenv("S3_BUCKET", "")

    db_conn.execute(
        "INSERT INTO companies (id, name, plan) VALUES ('company-1', 'テスト不動産', 'free')"
    )
    db_conn.execute(
        """
        INSERT INTO properties
            (id, address, latitude, longitude, property_name, company_id)
        VALUES
            ('prop-1', '東京都千代田区丸の内1-1-1', 35.6812, 139.7671, 'テスト物件', 'company-1')
        """
    )
    db_conn.commit()
    return db_conn
