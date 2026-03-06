"""Phase 15: ポートフォリオ連携 — portfolio.db スキーマ初期化 + S3 アップロード

実行方法:
  python scripts/migrate_phase15.py [--db-path /tmp/portfolio.db] [--upload]

引数:
  --db-path  ローカルの portfolio.db パス (デフォルト: /tmp/portfolio.db)
  --upload   完了後に S3 へアップロード (本番環境向け)
"""
import argparse
import os
import sqlite3
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

S3_PORTFOLIO_KEY = "data/portfolio.db"


def init_portfolio_db(db_path: str) -> None:
    """portfolio.db スキーマを初期化する (IF NOT EXISTS で冪等)。"""
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript("""
            -- === 保有銘柄マスタ ===
            CREATE TABLE IF NOT EXISTS portfolio_holdings (
                code       TEXT PRIMARY KEY,
                quantity   REAL NOT NULL CHECK(quantity > 0),
                avg_cost   REAL NOT NULL CHECK(avg_cost > 0),
                entry_date TEXT NOT NULL,
                note       TEXT,
                updated_at TEXT DEFAULT (datetime('now'))
            );

            -- === 取引履歴 ===
            CREATE TABLE IF NOT EXISTS portfolio_transactions (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                code       TEXT NOT NULL,
                date       TEXT NOT NULL,
                action     TEXT NOT NULL CHECK(action IN ('buy', 'sell')),
                quantity   REAL NOT NULL CHECK(quantity > 0),
                price      REAL NOT NULL CHECK(price > 0),
                fee        REAL NOT NULL DEFAULT 0 CHECK(fee >= 0),
                note       TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE INDEX IF NOT EXISTS idx_ptx_code ON portfolio_transactions(code, date DESC);
            CREATE INDEX IF NOT EXISTS idx_ptx_date ON portfolio_transactions(date DESC);

            -- === 日次評価額スナップショット ===
            -- バッチ Lambda が毎営業日終了後に stocks.db の終値を参照して書き込む
            CREATE TABLE IF NOT EXISTS portfolio_snapshots (
                date           TEXT NOT NULL,
                code           TEXT NOT NULL,
                close_price    REAL NOT NULL,
                quantity       REAL NOT NULL,
                valuation      REAL NOT NULL,
                unrealized_pnl REAL,
                PRIMARY KEY (date, code)
            );

            CREATE INDEX IF NOT EXISTS idx_psnap_date ON portfolio_snapshots(date DESC);
        """)
        conn.commit()
        print(f"portfolio.db スキーマを初期化しました: {db_path}")
    finally:
        conn.close()


def upload_to_s3(db_path: str) -> None:
    """portfolio.db を S3 にアップロードする。"""
    import boto3

    bucket = os.environ["S3_BUCKET"]
    s3 = boto3.client("s3")
    s3.upload_file(db_path, bucket, S3_PORTFOLIO_KEY)
    print(f"S3 にアップロードしました: s3://{bucket}/{S3_PORTFOLIO_KEY}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 15: portfolio.db 初期化")
    parser.add_argument("--db-path", default="/tmp/portfolio.db", help="ローカル DB パス")
    parser.add_argument("--upload", action="store_true", help="S3 にアップロード")
    args = parser.parse_args()

    init_portfolio_db(args.db_path)

    if args.upload:
        upload_to_s3(args.db_path)


if __name__ == "__main__":
    main()
