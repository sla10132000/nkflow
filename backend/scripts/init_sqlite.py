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

            -- === Phase 11: シグナル判定結果 ===
            CREATE TABLE IF NOT EXISTS signal_results (
                signal_id       INTEGER NOT NULL,
                horizon_days    INTEGER NOT NULL,
                eval_date       TEXT NOT NULL,
                actual_return   REAL,
                result          TEXT NOT NULL,
                created_at      TEXT DEFAULT (datetime('now')),
                PRIMARY KEY (signal_id, horizon_days),
                FOREIGN KEY (signal_id) REFERENCES signals(id)
            );

            CREATE INDEX IF NOT EXISTS idx_sr_eval_date ON signal_results(eval_date DESC);

            -- === Phase 11: シグナルタイプ別的中率集計 ===
            CREATE TABLE IF NOT EXISTS signal_accuracy (
                signal_type     TEXT NOT NULL,
                horizon_days    INTEGER NOT NULL,
                calc_date       TEXT NOT NULL,
                total_signals   INTEGER NOT NULL,
                hits            INTEGER NOT NULL,
                hit_rate        REAL NOT NULL,
                avg_return      REAL,
                PRIMARY KEY (signal_type, horizon_days, calc_date)
            );

            -- === Phase 13: 信用残高 (週次) ===
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

            -- === Phase 13: 為替レート (日次) ===
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

            -- === Phase 16: 市場圧力指標 ===
            CREATE TABLE IF NOT EXISTS margin_trading_weekly (
                week_date            TEXT NOT NULL,
                market_code          TEXT NOT NULL DEFAULT 'ALL',
                margin_buy_balance   REAL,
                margin_sell_balance  REAL,
                margin_ratio         REAL,
                lending_buy_balance  REAL,
                lending_sell_balance REAL,
                pl_ratio_proxy       REAL,
                PRIMARY KEY (week_date, market_code)
            );

            CREATE TABLE IF NOT EXISTS market_pressure_daily (
                date                TEXT PRIMARY KEY,
                pl_ratio            REAL,
                pl_zone             TEXT,
                buy_growth_4w       REAL,
                margin_ratio        REAL,
                margin_ratio_trend  REAL,
                signal_flags        TEXT
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

            -- === Phase 17: セクターローテーション分析 ===
            CREATE TABLE IF NOT EXISTS sector_daily_returns (
                date         TEXT NOT NULL,
                sector       TEXT NOT NULL,
                return_rate  REAL,
                stock_count  INTEGER,
                PRIMARY KEY (date, sector)
            );

            CREATE TABLE IF NOT EXISTS sector_weekly_returns (
                week_date    TEXT NOT NULL,
                sector       TEXT NOT NULL,
                return_rate  REAL,
                rank         INTEGER,
                PRIMARY KEY (week_date, sector)
            );

            CREATE TABLE IF NOT EXISTS sector_monthly_returns (
                month_date   TEXT NOT NULL,
                sector       TEXT NOT NULL,
                return_rate  REAL,
                rank         INTEGER,
                PRIMARY KEY (month_date, sector)
            );

            CREATE TABLE IF NOT EXISTS sector_rotation_states (
                period_date          TEXT NOT NULL,
                period_type          TEXT NOT NULL DEFAULT 'weekly',
                cluster_method       TEXT NOT NULL DEFAULT 'kmeans',
                state_id             INTEGER NOT NULL,
                state_name           TEXT,
                centroid_top_sectors TEXT,
                PRIMARY KEY (period_date, period_type, cluster_method)
            );

            CREATE TABLE IF NOT EXISTS sector_rotation_transitions (
                from_state     INTEGER NOT NULL,
                to_state       INTEGER NOT NULL,
                probability    REAL,
                count          INTEGER,
                period_type    TEXT NOT NULL DEFAULT 'weekly',
                cluster_method TEXT NOT NULL DEFAULT 'kmeans',
                calc_date      TEXT,
                PRIMARY KEY (from_state, to_state, period_type, cluster_method)
            );

            CREATE TABLE IF NOT EXISTS sector_rotation_predictions (
                id                   INTEGER PRIMARY KEY AUTOINCREMENT,
                calc_date            TEXT NOT NULL,
                current_state_id     INTEGER,
                current_state_name   TEXT,
                predicted_state_id   INTEGER,
                predicted_state_name TEXT,
                confidence           REAL,
                top_sectors          TEXT,
                all_probabilities    TEXT,
                model_accuracy       REAL
            );

            -- === Phase 18: ニュース記事 ===
            CREATE TABLE IF NOT EXISTS news_articles (
                id            TEXT PRIMARY KEY,
                published_at  TEXT NOT NULL,
                source        TEXT NOT NULL,
                source_name   TEXT,
                title         TEXT NOT NULL,
                title_ja      TEXT,
                url           TEXT NOT NULL UNIQUE,
                language      TEXT DEFAULT 'en',
                image_url     TEXT,
                tickers_json  TEXT DEFAULT '[]',
                sentiment     REAL,
                created_at    TEXT DEFAULT (datetime('now'))
            );
            CREATE INDEX IF NOT EXISTS idx_news_published ON news_articles(published_at DESC);
            CREATE INDEX IF NOT EXISTS idx_news_source ON news_articles(source);

            CREATE TABLE IF NOT EXISTS news_ticker_map (
                article_id  TEXT NOT NULL REFERENCES news_articles(id),
                ticker      TEXT NOT NULL,
                PRIMARY KEY (article_id, ticker)
            );
            CREATE INDEX IF NOT EXISTS idx_ntm_ticker ON news_ticker_map(ticker);

            -- === Phase 20: 米国主要株価指数 ===
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

            -- === 仮想通貨恐怖指数 (Phase 21) ===
            CREATE TABLE IF NOT EXISTS crypto_fear_greed (
                date                   TEXT PRIMARY KEY,
                value                  INTEGER NOT NULL,
                value_classification   TEXT NOT NULL,
                created_at             TEXT
            );

            -- === TD Sequential (Phase 22) ===
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
        print(f"SQLiteスキーマを初期化しました: {db_path}")
    finally:
        conn.close()


if __name__ == "__main__":
    db_path = sys.argv[1] if len(sys.argv) > 1 else "/tmp/stocks.db"
    init_sqlite(db_path)
