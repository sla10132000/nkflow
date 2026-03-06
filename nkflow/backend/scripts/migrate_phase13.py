"""
Phase 13 マイグレーション: 信用残・為替テーブル追加

既存の stocks.db に対して安全に実行できる (CREATE TABLE IF NOT EXISTS)。
ロールバックが必要な場合は migrate_phase13_rollback.py を実行する。
"""
import sqlite3
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


MIGRATION_SQL = """
-- ============================================================
-- Phase 13: 信用残高 (週次)
-- ============================================================
CREATE TABLE IF NOT EXISTS margin_balances (
    code            TEXT NOT NULL REFERENCES stocks(code),
    week_date       TEXT NOT NULL,
    margin_buy      REAL,
    margin_sell     REAL,
    margin_ratio    REAL,
    buy_change      REAL,
    sell_change     REAL,
    created_at      TEXT DEFAULT (datetime('now')),
    PRIMARY KEY (code, week_date)
);

CREATE INDEX IF NOT EXISTS idx_mb_week ON margin_balances(week_date DESC);
CREATE INDEX IF NOT EXISTS idx_mb_code ON margin_balances(code, week_date DESC);

-- ============================================================
-- Phase 13: 為替レート (日次)
-- ============================================================
CREATE TABLE IF NOT EXISTS exchange_rates (
    date            TEXT NOT NULL,
    pair            TEXT NOT NULL,
    open            REAL,
    high            REAL,
    low             REAL,
    close           REAL,
    change_rate     REAL,
    ma20            REAL,
    PRIMARY KEY (date, pair)
);

CREATE INDEX IF NOT EXISTS idx_er_date ON exchange_rates(date DESC);
"""


def migrate(db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(MIGRATION_SQL)
        conn.commit()
        print(f"Phase 13 マイグレーション完了: {db_path}")
    finally:
        conn.close()


if __name__ == "__main__":
    db_path = sys.argv[1] if len(sys.argv) > 1 else "/tmp/stocks.db"
    migrate(db_path)
