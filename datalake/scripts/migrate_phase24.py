"""Phase 24: news_articles テーブルに category カラムを追加"""
import sqlite3
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def migrate(db_path: str = "/tmp/stocks.db") -> None:
    conn = sqlite3.connect(db_path)
    try:
        # category カラムが存在しない場合のみ追加 (冪等)
        cols = {row[1] for row in conn.execute("PRAGMA table_info(news_articles)")}
        if "category" not in cols:
            conn.execute("ALTER TABLE news_articles ADD COLUMN category TEXT")
            conn.commit()
            print("✅ news_articles.category カラムを追加しました")
        else:
            print("⏭  news_articles.category カラムは既に存在します")

        # category インデックス
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_news_category ON news_articles(category)"
        )
        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "/tmp/stocks.db"
    migrate(path)
