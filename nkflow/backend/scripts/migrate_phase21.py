"""
Phase 21 マイグレーション: 恐怖指数 (VIX + BTC Fear & Greed)

変更内容:
  - crypto_fear_greed テーブルを作成 (冪等)
  - us_indices テーブルへの ^VIX データ取得は fetch_us_indices で自動実行

実行方法:
    cd backend
    SQLITE_PATH=/tmp/stocks.db .venv/bin/python scripts/migrate_phase21.py
"""
import os
import sqlite3
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def migrate(db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS crypto_fear_greed (
                date                   TEXT PRIMARY KEY,
                value                  INTEGER NOT NULL,
                value_classification   TEXT NOT NULL,
                created_at             TEXT
            );
        """)
        conn.commit()
        print(f"Phase 21 マイグレーション完了: {db_path}")
    finally:
        conn.close()


if __name__ == "__main__":
    from src.config import SQLITE_PATH
    path = os.environ.get("SQLITE_PATH", SQLITE_PATH)
    migrate(path)
