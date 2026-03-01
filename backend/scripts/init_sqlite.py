"""SQLite初期スキーマ作成"""
import sqlite3
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def init_sqlite(db_path: str = "/tmp/stocks.db") -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript("""
            -- === マスタ ===
            CREATE TABLE IF NOT EXISTS stocks (
                code        TEXT PRIMARY KEY,
                name        TEXT NOT NULL,
                sector      TEXT NOT NULL
            );

            -- === 日次価格データ ===
            CREATE TABLE IF NOT EXISTS daily_prices (
                code              TEXT NOT NULL REFERENCES stocks(code),
                date              TEXT NOT NULL,
                open              REAL,
                high              REAL,
                low               REAL,
                close             REAL,
                volume            INTEGER,
                return_rate       REAL,
                price_range       REAL,
                range_pct         REAL,
                relative_strength REAL,
                PRIMARY KEY (code, date)
            );

            CREATE INDEX IF NOT EXISTS idx_dp_date ON daily_prices(date);
            CREATE INDEX IF NOT EXISTS idx_dp_code_date ON daily_prices(code, date DESC);

            -- === グラフ分析結果 (KùzuDBから書き戻し) ===

            -- 因果関係エッジ
            CREATE TABLE IF NOT EXISTS graph_causality (
                source      TEXT NOT NULL,
                target      TEXT NOT NULL,
                lag_days    INTEGER NOT NULL,
                p_value     REAL NOT NULL,
                f_stat      REAL NOT NULL,
                period      TEXT NOT NULL,
                calc_date   TEXT NOT NULL,
                PRIMARY KEY (source, target, period, calc_date)
            );

            -- 相関エッジ
            CREATE TABLE IF NOT EXISTS graph_correlations (
                stock_a     TEXT NOT NULL,
                stock_b     TEXT NOT NULL,
                coefficient REAL NOT NULL,
                period      TEXT NOT NULL,
                calc_date   TEXT NOT NULL,
                PRIMARY KEY (stock_a, stock_b, period, calc_date)
            );

            -- セクター間資金フロー
            CREATE TABLE IF NOT EXISTS graph_fund_flows (
                sector_from    TEXT NOT NULL,
                sector_to      TEXT NOT NULL,
                volume_delta   REAL,
                return_spread  REAL,
                date           TEXT NOT NULL,
                PRIMARY KEY (sector_from, sector_to, date)
            );

            -- コミュニティ(クラスター)
            CREATE TABLE IF NOT EXISTS graph_communities (
                code           TEXT NOT NULL,
                community_id   INTEGER NOT NULL,
                calc_date      TEXT NOT NULL,
                PRIMARY KEY (code, calc_date)
            );

            -- === 予測シグナル ===
            CREATE TABLE IF NOT EXISTS signals (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                date           TEXT NOT NULL,
                signal_type    TEXT NOT NULL,
                code           TEXT,
                sector         TEXT,
                direction      TEXT NOT NULL,
                confidence     REAL NOT NULL,
                reasoning      TEXT NOT NULL,
                created_at     TEXT DEFAULT (datetime('now'))
            );

            CREATE INDEX IF NOT EXISTS idx_signals_date ON signals(date DESC);
            CREATE INDEX IF NOT EXISTS idx_signals_code ON signals(code, date DESC);

            -- === 日次サマリ ===
            CREATE TABLE IF NOT EXISTS daily_summary (
                date            TEXT PRIMARY KEY,
                nikkei_close    REAL,
                nikkei_return   REAL,
                regime          TEXT,
                top_gainers     TEXT,
                top_losers      TEXT,
                active_signals  INTEGER,
                sector_rotation TEXT
            );

            -- === Phase 14: バックテスト ===
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
        """)
        conn.commit()
        print(f"SQLiteスキーマを初期化しました: {db_path}")
    finally:
        conn.close()


if __name__ == "__main__":
    db_path = sys.argv[1] if len(sys.argv) > 1 else "/tmp/stocks.db"
    init_sqlite(db_path)
