"""
Phase 22 マイグレーション: td_sequential テーブル作成 (冪等)

変更内容:
  - td_sequential テーブルを作成
    (code, date) PRIMARY KEY
    setup_bull / setup_bear: セットアップカウント 0-9 (0 = 非アクティブ)
    countdown_bull / countdown_bear: カウントダウン 0-13 (0 = 非アクティブ)

実行方法:
    cd backend
    SQLITE_PATH=/tmp/stocks.db .venv/bin/python scripts/migrate_phase22_td_sequential.py
"""
import os
import sqlite3
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def migrate(db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS td_sequential (
                code            TEXT NOT NULL,
                date            TEXT NOT NULL,
                setup_bull      INTEGER NOT NULL DEFAULT 0,
                setup_bear      INTEGER NOT NULL DEFAULT 0,
                countdown_bull  INTEGER NOT NULL DEFAULT 0,
                countdown_bear  INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (code, date)
            );

            CREATE INDEX IF NOT EXISTS idx_tds_code_date
                ON td_sequential(code, date DESC);
        """)
        conn.commit()
        print(f"Phase 22 マイグレーション完了: {db_path}")
    finally:
        conn.close()


if __name__ == "__main__":
    from src.config import SQLITE_PATH
    path = os.environ.get("SQLITE_PATH", SQLITE_PATH)
    migrate(path)
