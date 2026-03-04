"""Phase 17: セクターローテーション分析 — DB スキーマ追加

実行方法:
  python backend/scripts/migrate_phase17.py [db_path]

引数:
  db_path  stocks.db のパス (デフォルト: /tmp/stocks.db)
"""
import sqlite3
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def migrate(db_path: str) -> None:
    """セクターローテーション分析用テーブルを追加する (冪等)。"""
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript("""
            -- === Phase 17-1: セクター日次リターン ===
            CREATE TABLE IF NOT EXISTS sector_daily_returns (
                date         TEXT NOT NULL,
                sector       TEXT NOT NULL,
                return_rate  REAL,
                stock_count  INTEGER,
                PRIMARY KEY (date, sector)
            );

            -- === Phase 17-2: セクター週次リターン (金曜締め) ===
            CREATE TABLE IF NOT EXISTS sector_weekly_returns (
                week_date    TEXT NOT NULL,   -- 週末金曜の日付 (YYYY-MM-DD)
                sector       TEXT NOT NULL,
                return_rate  REAL,
                rank         INTEGER,          -- リターン降順の順位 (1=最高)
                PRIMARY KEY (week_date, sector)
            );

            -- === Phase 17-3: セクター月次リターン (月末締め) ===
            CREATE TABLE IF NOT EXISTS sector_monthly_returns (
                month_date   TEXT NOT NULL,   -- YYYY-MM
                sector       TEXT NOT NULL,
                return_rate  REAL,
                rank         INTEGER,
                PRIMARY KEY (month_date, sector)
            );

            -- === Phase 17-4: ローテーション状態 (クラスタリング / HMM) ===
            CREATE TABLE IF NOT EXISTS sector_rotation_states (
                period_date          TEXT NOT NULL,
                period_type          TEXT NOT NULL DEFAULT 'weekly',  -- 'weekly' | 'monthly'
                cluster_method       TEXT NOT NULL DEFAULT 'kmeans',  -- 'kmeans' | 'hmm'
                state_id             INTEGER NOT NULL,
                state_name           TEXT,             -- 例: "電機・情通主導/不動産安"
                centroid_top_sectors TEXT,             -- JSON: [{sector, avg_return}, ...]
                PRIMARY KEY (period_date, period_type, cluster_method)
            );

            -- === Phase 17-5: 状態遷移確率行列 ===
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

            -- === Phase 17-6: 次期状態予測 (LightGBM) ===
            CREATE TABLE IF NOT EXISTS sector_rotation_predictions (
                id                   INTEGER PRIMARY KEY AUTOINCREMENT,
                calc_date            TEXT NOT NULL,
                current_state_id     INTEGER,
                current_state_name   TEXT,
                predicted_state_id   INTEGER,
                predicted_state_name TEXT,
                confidence           REAL,
                top_sectors          TEXT,   -- JSON: [{sector, avg_return}, ...]
                all_probabilities    TEXT,   -- JSON: [{state_id, state_name, probability}, ...]
                model_accuracy       REAL
            );
        """)
        conn.commit()
        print(f"Phase 17 マイグレーション完了: {db_path}")
    finally:
        conn.close()


def main() -> None:
    db_path = sys.argv[1] if len(sys.argv) > 1 else "/tmp/stocks.db"
    migrate(db_path)


if __name__ == "__main__":
    main()
