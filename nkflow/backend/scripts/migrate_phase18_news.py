"""Phase 18: news_articles / news_ticker_map テーブル追加 (冪等)"""
import sqlite3
import sys


def migrate(db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS news_articles (
                id            TEXT PRIMARY KEY,
                published_at  TEXT NOT NULL,
                source        TEXT NOT NULL,
                source_name   TEXT,
                title         TEXT NOT NULL,
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
        """)
        conn.commit()
        print(f"Phase 18 マイグレーション完了: {db_path}")
    finally:
        conn.close()


if __name__ == "__main__":
    db_path = sys.argv[1] if len(sys.argv) > 1 else "/tmp/stocks.db"
    migrate(db_path)
