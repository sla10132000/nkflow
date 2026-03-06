"""
Phase 23 マイグレーション: investor_flow_weekly / investor_flow_indicators テーブル作成 (冪等)

変更内容:
  - investor_flow_weekly テーブルを作成
    (week_start, week_end, section, investor_type) PRIMARY KEY
  - investor_flow_indicators テーブルを作成
    week_end PRIMARY KEY

実行方法:
    cd nkflow/backend
    SQLITE_PATH=/tmp/stocks.db .venv/bin/python scripts/migrate_phase23_investor_flow.py
"""
import os
import sqlite3
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def migrate(db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS investor_flow_weekly (
                week_start      TEXT NOT NULL,
                week_end        TEXT NOT NULL,
                section         TEXT NOT NULL,
                investor_type   TEXT NOT NULL,
                sales           REAL,
                purchases       REAL,
                balance         REAL,
                published_date  TEXT,
                created_at      TEXT DEFAULT (datetime('now')),
                PRIMARY KEY (week_start, week_end, section, investor_type)
            );

            CREATE INDEX IF NOT EXISTS idx_ifw_week_end
                ON investor_flow_weekly(week_end DESC);

            CREATE TABLE IF NOT EXISTS investor_flow_indicators (
                week_end             TEXT PRIMARY KEY,
                foreigners_net       REAL,
                individuals_net      REAL,
                foreigners_4w_ma     REAL,
                individuals_4w_ma    REAL,
                foreigners_momentum  REAL,
                individuals_momentum REAL,
                divergence_score     REAL,
                nikkei_return_4w     REAL,
                flow_regime          TEXT
            );
        """)
        conn.commit()
        print(f"Phase 23 マイグレーション完了: {db_path}")
    finally:
        conn.close()


if __name__ == "__main__":
    from src.config import SQLITE_PATH
    path = os.environ.get("SQLITE_PATH", SQLITE_PATH)
    migrate(path)
