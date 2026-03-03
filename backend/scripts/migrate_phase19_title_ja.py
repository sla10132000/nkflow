"""Phase 19: news_articles に title_ja カラムを追加 (冪等)"""
import sqlite3
import sys


def migrate(db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    try:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(news_articles)")}
        if "title_ja" not in cols:
            conn.execute("ALTER TABLE news_articles ADD COLUMN title_ja TEXT")
            conn.commit()
            print(f"Phase 19: title_ja カラムを追加しました: {db_path}")
        else:
            print(f"Phase 19: title_ja は既に存在します (スキップ): {db_path}")
    finally:
        conn.close()


if __name__ == "__main__":
    db_path = sys.argv[1] if len(sys.argv) > 1 else "/tmp/stocks.db"
    migrate(db_path)
