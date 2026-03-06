"""
Phase 20 マイグレーション: 米国主要株価指数テーブル追加

既存の stocks.db に対して安全に実行できる (CREATE TABLE IF NOT EXISTS)。
"""
import sqlite3
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


MIGRATION_SQL = """
-- ============================================================
-- Phase 20: 米国主要株価指数 (日次 OHLCV)
-- ============================================================
CREATE TABLE IF NOT EXISTS us_indices (
    date      TEXT    NOT NULL,
    ticker    TEXT    NOT NULL,
    name      TEXT    NOT NULL,
    open      REAL,
    high      REAL,
    low       REAL,
    close     REAL    NOT NULL,
    volume    INTEGER,
    PRIMARY KEY (date, ticker)
);

CREATE INDEX IF NOT EXISTS idx_us_indices_ticker ON us_indices(ticker);
CREATE INDEX IF NOT EXISTS idx_us_indices_date ON us_indices(date DESC);
"""


def migrate(db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(MIGRATION_SQL)
        conn.commit()
        print(f"Phase 20 マイグレーション完了: {db_path}")
    finally:
        conn.close()


if __name__ == "__main__":
    db_path = sys.argv[1] if len(sys.argv) > 1 else "/tmp/stocks.db"
    migrate(db_path)
