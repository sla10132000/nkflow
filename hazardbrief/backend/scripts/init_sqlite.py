"""HazardBrief DB スキーマ初期化スクリプト

テーブル:
  - companies: テナント（不動産会社）
  - profiles: ユーザー（エージェント）
  - properties: 物件
  - hazard_reports: ハザードレポートキャッシュ
"""
import sqlite3
import sys


def init_sqlite(db_path: str) -> None:
    """指定パスに HazardBrief SQLite スキーマを初期化する (冪等)。"""
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")

    conn.executescript("""
        -- 会社（テナント）
        CREATE TABLE IF NOT EXISTS companies (
            id          TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
            name        TEXT NOT NULL,
            plan        TEXT NOT NULL DEFAULT 'free',
            created_at  TEXT NOT NULL DEFAULT (datetime('now'))
        );

        -- ユーザー（エージェント）
        CREATE TABLE IF NOT EXISTS profiles (
            id          TEXT PRIMARY KEY,
            company_id  TEXT REFERENCES companies(id),
            full_name   TEXT,
            email       TEXT,
            role        TEXT NOT NULL DEFAULT 'agent',
            created_at  TEXT NOT NULL DEFAULT (datetime('now'))
        );

        -- 物件
        CREATE TABLE IF NOT EXISTS properties (
            id            TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
            company_id    TEXT REFERENCES companies(id),
            created_by    TEXT REFERENCES profiles(id),
            address       TEXT NOT NULL,
            latitude      REAL,
            longitude     REAL,
            property_name TEXT,
            notes         TEXT,
            created_at    TEXT NOT NULL DEFAULT (datetime('now'))
        );

        -- ハザードレポート（取得結果キャッシュ）
        CREATE TABLE IF NOT EXISTS hazard_reports (
            id            TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
            property_id   TEXT NOT NULL REFERENCES properties(id),
            flood_risk    TEXT,
            landslide_risk TEXT,
            tsunami_risk  TEXT,
            ground_risk   TEXT,
            risk_summary  TEXT,
            fetched_at    TEXT NOT NULL DEFAULT (datetime('now')),
            expires_at    TEXT
        );

        -- インデックス
        CREATE INDEX IF NOT EXISTS idx_properties_company ON properties(company_id);
        CREATE INDEX IF NOT EXISTS idx_properties_created_by ON properties(created_by);
        CREATE INDEX IF NOT EXISTS idx_hazard_reports_property ON hazard_reports(property_id);
        CREATE INDEX IF NOT EXISTS idx_profiles_company ON profiles(company_id);
    """)

    conn.commit()
    conn.close()
    print(f"DB初期化完了: {db_path}")


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "/tmp/hazardbrief.db"
    init_sqlite(path)
