"""fetch_news.normalize_news() のテスト (moto S3 モック + SQLite)"""
import json
import os
import sqlite3
import sys
from unittest.mock import patch

import boto3
import pytest
from moto import mock_aws

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scripts.init_sqlite import init_sqlite

BUCKET = "test-nkflow-bucket"
TARGET_DATE = "2026-03-03"

FAKE_ARTICLES = [
    {
        "url": "https://reuters.com/article1",
        "title": "Nikkei rises on positive data",
        "seendate": "20260303T090000Z",
        "domain": "reuters.com",
        "sourcename": "Reuters",
        "language": "English",
        "socialimage": "https://example.com/img.jpg",
    },
    {
        "url": "https://bloomberg.com/article2",
        "title": "Tokyo Stock Exchange sees surge",
        "seendate": "20260303T080000Z",
        "domain": "bloomberg.com",
        "sourcename": "Bloomberg",
        "language": "English",
        "socialimage": None,
    },
    {
        "url": "https://nhk.or.jp/article3",
        "title": "日経平均が上昇",
        "seendate": "2026-03-03T09:00:00+00:00",
        "domain": "nhk_biz",
        "sourcename": "NHK",
        "language": "Japanese",
        "socialimage": None,
    },
]


@pytest.fixture
def db_conn(tmp_path):
    """Phase 19 スキーマ込みの SQLite 接続"""
    db_path = str(tmp_path / "test.db")
    init_sqlite(db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    yield conn
    conn.close()


def _fake_translate(titles: list) -> list:
    """_translate_titles のモック: 各タイトルに「（翻訳）」を付ける"""
    return [f"{t}（翻訳）" for t in titles]


@mock_aws
class TestNormalizeNews:
    def _setup_s3(self, articles=None):
        s3 = boto3.client("s3", region_name="ap-northeast-1")
        s3.create_bucket(
            Bucket=BUCKET,
            CreateBucketConfiguration={"LocationConstraint": "ap-northeast-1"},
        )
        if articles is not None:
            s3.put_object(
                Bucket=BUCKET,
                Key=f"news/raw/{TARGET_DATE}.json",
                Body=json.dumps(articles),
            )
        return s3

    def test_inserts_articles(self, db_conn):
        self._setup_s3(FAKE_ARTICLES)
        with patch("src.ingestion.news._translate_titles", side_effect=_fake_translate):
            from src.ingestion.news import normalize_news
            count = normalize_news(db_conn, TARGET_DATE)
        assert count == 3
        rows = db_conn.execute(
            "SELECT title, title_ja, language FROM news_articles ORDER BY title"
        ).fetchall()
        assert len(rows) == 3

    def test_japanese_article_title_ja_equals_title(self, db_conn):
        """日本語記事は title_ja = title になること"""
        self._setup_s3(FAKE_ARTICLES)
        with patch("src.ingestion.news._translate_titles", side_effect=_fake_translate):
            from src.ingestion.news import normalize_news
            normalize_news(db_conn, TARGET_DATE)

        row = db_conn.execute(
            "SELECT title, title_ja FROM news_articles WHERE language = 'Japanese'"
        ).fetchone()
        assert row is not None
        assert row["title"] == "日経平均が上昇"
        assert row["title_ja"] == "日経平均が上昇"

    def test_english_article_gets_translated_title_ja(self, db_conn):
        """英語記事は _translate_titles の結果が title_ja に設定されること"""
        self._setup_s3(FAKE_ARTICLES)
        with patch("src.ingestion.news._translate_titles", side_effect=_fake_translate):
            from src.ingestion.news import normalize_news
            normalize_news(db_conn, TARGET_DATE)

        rows = db_conn.execute(
            "SELECT title, title_ja FROM news_articles WHERE language = 'English' ORDER BY title"
        ).fetchall()
        assert len(rows) == 2
        for row in rows:
            assert row["title_ja"] == f"{row['title']}（翻訳）"

    def test_idempotent(self, db_conn):
        """同じ raw データを 2 回処理しても件数は増えない"""
        self._setup_s3(FAKE_ARTICLES)
        with patch("src.ingestion.news._translate_titles", side_effect=_fake_translate):
            from src.ingestion.news import normalize_news
            normalize_news(db_conn, TARGET_DATE)
            count = normalize_news(db_conn, TARGET_DATE)
        assert count == 3
        total = db_conn.execute("SELECT COUNT(*) FROM news_articles").fetchone()[0]
        assert total == 3

    def test_returns_zero_when_no_raw(self, db_conn):
        """S3 に raw がない場合は 0 を返す"""
        self._setup_s3(articles=None)
        from src.ingestion.news import normalize_news
        count = normalize_news(db_conn, TARGET_DATE)
        assert count == 0
        total = db_conn.execute("SELECT COUNT(*) FROM news_articles").fetchone()[0]
        assert total == 0

    def test_skips_articles_without_url_or_title(self, db_conn):
        bad_articles = [
            {"url": "", "title": "No URL"},
            {"url": "https://example.com/a", "title": ""},
        ]
        self._setup_s3(bad_articles)
        from src.ingestion.news import normalize_news
        count = normalize_news(db_conn, TARGET_DATE)
        assert count == 0

    def test_returns_zero_on_empty_list(self, db_conn):
        self._setup_s3([])
        from src.ingestion.news import normalize_news
        count = normalize_news(db_conn, TARGET_DATE)
        assert count == 0
