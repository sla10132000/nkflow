"""
Phase 14 マイグレーション: バックテスト用テーブル追加

既存の stocks.db に対して安全に実行できる (CREATE TABLE IF NOT EXISTS)。
"""
import sqlite3
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


MIGRATION_SQL = """
-- ============================================================
-- Phase 14: バックテスト実行設定
-- ============================================================
CREATE TABLE IF NOT EXISTS backtest_runs (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    name             TEXT NOT NULL,
    signal_type      TEXT,
    from_date        TEXT NOT NULL,
    to_date          TEXT NOT NULL,
    holding_days     INTEGER NOT NULL,
    direction_filter TEXT,
    min_confidence   REAL NOT NULL DEFAULT 0.0,
    created_at       TEXT DEFAULT (datetime('now'))
);

-- ============================================================
-- Phase 14: バックテスト個別トレード
-- ============================================================
CREATE TABLE IF NOT EXISTS backtest_trades (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id       INTEGER NOT NULL REFERENCES backtest_runs(id),
    signal_id    INTEGER NOT NULL,
    code         TEXT NOT NULL,
    signal_date  TEXT NOT NULL,
    entry_date   TEXT,
    exit_date    TEXT,
    entry_price  REAL,
    exit_price   REAL,
    return_rate  REAL,
    direction    TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_bt_trades_run ON backtest_trades(run_id);
CREATE INDEX IF NOT EXISTS idx_bt_trades_code ON backtest_trades(code);

-- ============================================================
-- Phase 14: バックテスト集計結果
-- ============================================================
CREATE TABLE IF NOT EXISTS backtest_results (
    run_id         INTEGER PRIMARY KEY REFERENCES backtest_runs(id),
    total_trades   INTEGER NOT NULL,
    winning_trades INTEGER NOT NULL,
    win_rate       REAL NOT NULL,
    avg_return     REAL NOT NULL,
    total_return   REAL NOT NULL,
    max_drawdown   REAL,
    sharpe_ratio   REAL,
    calc_date      TEXT NOT NULL
);
"""


def migrate(db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(MIGRATION_SQL)
        conn.commit()
        print(f"Phase 14 マイグレーション完了: {db_path}")
    finally:
        conn.close()


if __name__ == "__main__":
    db_path = sys.argv[1] if len(sys.argv) > 1 else "/tmp/stocks.db"
    migrate(db_path)
