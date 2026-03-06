"""news_enrichment: センチメント分析・テーマ分類・ティッカー抽出のテスト"""
import sqlite3

import pytest


# ── analyze_sentiment ─────────────────────────────────────────────────


class TestAnalyzeSentiment:
    def test_positive_ja(self):
        from src.transform.news_enrichment import analyze_sentiment

        score = analyze_sentiment("トヨタ自動車、通期上方修正で最高益更新", None)
        assert score > 0

    def test_negative_ja(self):
        from src.transform.news_enrichment import analyze_sentiment

        score = analyze_sentiment("ソニー、減益で株価急落", None)
        assert score < 0

    def test_positive_en(self):
        from src.transform.news_enrichment import analyze_sentiment

        score = analyze_sentiment(None, "Markets surge on strong profit growth")
        assert score > 0

    def test_negative_en(self):
        from src.transform.news_enrichment import analyze_sentiment

        score = analyze_sentiment(None, "Stock market crash as recession fears grow")
        assert score < 0

    def test_neutral_no_keywords(self):
        from src.transform.news_enrichment import analyze_sentiment

        score = analyze_sentiment("今日の天気は晴れです", "Weather is sunny today")
        assert score == 0.0

    def test_mixed_returns_balanced(self):
        from src.transform.news_enrichment import analyze_sentiment

        # 1 positive + 1 negative → 0.0
        score = analyze_sentiment("増益だが赤字部門あり", None)
        assert score == 0.0

    def test_none_inputs(self):
        from src.transform.news_enrichment import analyze_sentiment

        assert analyze_sentiment(None, None) == 0.0

    def test_score_clamped_to_range(self):
        from src.transform.news_enrichment import analyze_sentiment

        score = analyze_sentiment(
            "上昇 好調 増益 増収 最高益 反発 上方修正", None
        )
        assert -1.0 <= score <= 1.0


# ── classify_theme ────────────────────────────────────────────────────


class TestClassifyTheme:
    def test_earnings(self):
        from src.transform.news_enrichment import classify_theme

        assert classify_theme("トヨタ通期決算、増益で過去最高", None) == "決算"

    def test_monetary_policy(self):
        from src.transform.news_enrichment import classify_theme

        assert classify_theme("日銀、利上げを決定", None) == "金融政策"

    def test_forex(self):
        from src.transform.news_enrichment import classify_theme

        assert classify_theme("円安加速、ドル円150円台に", None) == "為替"

    def test_us_market(self):
        from src.transform.news_enrichment import classify_theme

        assert classify_theme(None, "Dow Jones closes at record high on Wall Street") == "米国市場"

    def test_semiconductor(self):
        from src.transform.news_enrichment import classify_theme

        assert classify_theme("NVIDIA決算好調、半導体株に追い風", None) == "決算"
        # 決算が先にマッチ (辞書の順序)

    def test_ai(self):
        from src.transform.news_enrichment import classify_theme

        assert classify_theme("生成AIの新サービス開始", None) == "AI"

    def test_geopolitics(self):
        from src.transform.news_enrichment import classify_theme

        assert classify_theme("米中関税戦争が激化", None) == "地政学"

    def test_other(self):
        from src.transform.news_enrichment import classify_theme

        assert classify_theme("今日の天気は晴れです", None) == "その他"

    def test_none_inputs(self):
        from src.transform.news_enrichment import classify_theme

        assert classify_theme(None, None) == "その他"

    def test_english_fed(self):
        from src.transform.news_enrichment import classify_theme

        assert classify_theme(None, "FOMC meeting results") == "金融政策"


# ── extract_tickers_from_title ────────────────────────────────────────


class TestExtractTickers:
    def test_code_match(self):
        from src.transform.news_enrichment import extract_tickers_from_title

        codes = extract_tickers_from_title(
            "7203 トヨタが上方修正",
            {"トヨタ自動車": "7203"},
        )
        assert "7203" in codes

    def test_name_match(self):
        from src.transform.news_enrichment import extract_tickers_from_title

        codes = extract_tickers_from_title(
            "ソニーグループの新製品発表",
            {"ソニーグループ": "6758"},
        )
        assert "6758" in codes

    def test_no_match(self):
        from src.transform.news_enrichment import extract_tickers_from_title

        codes = extract_tickers_from_title(
            "今日の天気は晴れです",
            {"トヨタ自動車": "7203"},
        )
        assert len(codes) == 0

    def test_multiple_matches(self):
        from src.transform.news_enrichment import extract_tickers_from_title

        codes = extract_tickers_from_title(
            "トヨタ自動車とソニーが提携",
            {"トヨタ自動車": "7203", "ソニーグループ": "6758", "ソニー": "6758"},
        )
        assert "7203" in codes
        assert "6758" in codes

    def test_code_not_in_stocks_ignored(self):
        from src.transform.news_enrichment import extract_tickers_from_title

        codes = extract_tickers_from_title(
            "電話番号は 0120 です",
            {"トヨタ自動車": "7203"},
        )
        assert len(codes) == 0


# ── enrich_articles (統合テスト) ──────────────────────────────────────


class TestEnrichArticles:
    @pytest.fixture()
    def db(self, tmp_path):
        """テスト用 SQLite DB を作成する。"""
        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        conn.executescript("""
            CREATE TABLE stocks (
                code TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                sector TEXT NOT NULL
            );
            INSERT INTO stocks VALUES ('7203', 'トヨタ自動車', '輸送用機器');
            INSERT INTO stocks VALUES ('6758', 'ソニーグループ', '電気機器');

            CREATE TABLE news_articles (
                id TEXT PRIMARY KEY,
                published_at TEXT NOT NULL,
                source TEXT NOT NULL,
                source_name TEXT,
                title TEXT NOT NULL,
                title_ja TEXT,
                url TEXT NOT NULL UNIQUE,
                language TEXT DEFAULT 'en',
                image_url TEXT,
                tickers_json TEXT DEFAULT '[]',
                sentiment REAL,
                category TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE news_ticker_map (
                article_id TEXT NOT NULL REFERENCES news_articles(id),
                ticker TEXT NOT NULL,
                PRIMARY KEY (article_id, ticker)
            );
        """)
        return conn

    def test_enriches_all_fields(self, db):
        from src.transform.news_enrichment import enrich_articles

        db.execute(
            """INSERT INTO news_articles (id, published_at, source, title, title_ja, url)
               VALUES ('a1', '2026-03-04T10:00:00', 'nhk', 'Toyota profit rises',
                       'トヨタ自動車、増益で上方修正', 'https://example.com/1')"""
        )
        db.commit()

        counts = enrich_articles(db)

        assert counts["sentiment"] == 1
        assert counts["category"] == 1

        # sentiment > 0 (positive)
        row = db.execute("SELECT sentiment, category FROM news_articles WHERE id='a1'").fetchone()
        assert row["sentiment"] > 0
        assert row["category"] == "決算"

        # ticker map
        tickers = db.execute("SELECT ticker FROM news_ticker_map WHERE article_id='a1'").fetchall()
        assert any(t["ticker"] == "7203" for t in tickers)

    def test_idempotent(self, db):
        from src.transform.news_enrichment import enrich_articles

        db.execute(
            """INSERT INTO news_articles (id, published_at, source, title, title_ja, url)
               VALUES ('a1', '2026-03-04T10:00:00', 'nhk', 'Test',
                       'テスト記事', 'https://example.com/1')"""
        )
        db.commit()

        enrich_articles(db)
        counts = enrich_articles(db)

        # 2回目は更新なし
        assert counts["sentiment"] == 0
        assert counts["category"] == 0

    def test_no_stocks_table(self, tmp_path):
        """stocks テーブルがなくてもセンチメント・テーマは動く。"""
        from src.transform.news_enrichment import enrich_articles

        db_path = tmp_path / "no_stocks.db"
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        conn.executescript("""
            CREATE TABLE news_articles (
                id TEXT PRIMARY KEY,
                published_at TEXT NOT NULL,
                source TEXT NOT NULL,
                source_name TEXT,
                title TEXT NOT NULL,
                title_ja TEXT,
                url TEXT NOT NULL UNIQUE,
                language TEXT DEFAULT 'en',
                image_url TEXT,
                tickers_json TEXT DEFAULT '[]',
                sentiment REAL,
                category TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE news_ticker_map (
                article_id TEXT NOT NULL,
                ticker TEXT NOT NULL,
                PRIMARY KEY (article_id, ticker)
            );
            INSERT INTO news_articles (id, published_at, source, title, url)
            VALUES ('b1', '2026-03-04', 'test', 'Market crash', 'https://ex.com/1');
        """)

        counts = enrich_articles(conn)
        assert counts["sentiment"] == 1
        assert counts["category"] == 1
        assert counts["tickers"] == 0
        conn.close()
