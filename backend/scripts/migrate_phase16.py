"""Phase 16: 信用系データ統合 (Market Pressure) — DB スキーマ追加

実行方法:
  python backend/scripts/migrate_phase16.py [db_path]

引数:
  db_path  stocks.db のパス (デフォルト: /tmp/stocks.db)
"""
import sqlite3
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def migrate(db_path: str) -> None:
    """margin_trading_weekly / market_pressure_daily テーブルを追加する (冪等)。"""
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript("""
            -- === Phase 16: 市場レベル週次信用集計 ===
            CREATE TABLE IF NOT EXISTS margin_trading_weekly (
                week_date            TEXT NOT NULL,
                market_code          TEXT NOT NULL DEFAULT 'ALL',
                margin_buy_balance   REAL,   -- 全銘柄 SUM(margin_buy)
                margin_sell_balance  REAL,   -- 全銘柄 SUM(margin_sell)
                margin_ratio         REAL,   -- buy / sell
                lending_buy_balance  REAL,   -- 将来拡張用 (NULL可)
                lending_sell_balance REAL,
                pl_ratio_proxy       REAL,   -- 加重累積リターン近似値
                PRIMARY KEY (week_date, market_code)
            );

            -- === Phase 16: 日次市場圧力指標 ===
            CREATE TABLE IF NOT EXISTS market_pressure_daily (
                date                TEXT PRIMARY KEY,
                pl_ratio            REAL,      -- margin_trading_weekly から取得 (週次補完)
                pl_zone             TEXT,      -- ceiling/overheat/neutral/weak/sellin/bottom
                buy_growth_4w       REAL,      -- 4週前比増加率
                margin_ratio        REAL,      -- 信用倍率
                margin_ratio_trend  REAL,      -- 4週移動平均の傾き
                signal_flags        TEXT       -- JSON: {"credit_overheating": true/false}
            );
        """)
        conn.commit()
        print(f"Phase 16 マイグレーション完了: {db_path}")
    finally:
        conn.close()


def main() -> None:
    db_path = sys.argv[1] if len(sys.argv) > 1 else "/tmp/stocks.db"
    migrate(db_path)


if __name__ == "__main__":
    main()
