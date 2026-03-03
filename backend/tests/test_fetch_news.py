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
]


@pytest.fixture
def db_conn(tmp_path):
    """Phase 18 スキーマ込みの SQLite 接続"""
    db_path = str(tmp_path / "test.db")
    init_sqlite(db_path)
    conn = sqlite3.connect(db_path)
    yield conn
    conn.close()


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
        from src.batch.fetch_news import normalize_news
        count = normalize_news(db_conn, TARGET_DATE)
        assert count == 2
        rows = db_conn.execute("SELECT id, title, source FROM news_articles ORDER BY source").fetchall()
        assert len(rows) == 2
        assert rows[1][1] == "Nikkei rises on positive data"

    def test_idempotent(self, db_conn):
        """同じ raw データを 2 回処理しても件数は増えない"""
        self._setup_s3(FAKE_ARTICLES)
        from src.batch.fetch_news import normalize_news
        normalize_news(db_conn, TARGET_DATE)
        count = normalize_news(db_conn, TARGET_DATE)
        assert count == 2
        total = db_conn.execute("SELECT COUNT(*) FROM news_articles").fetchone()[0]
        assert total == 2

    def test_returns_zero_when_no_raw(self, db_conn):
        """S3 に raw がない場合は 0 を返す"""
        self._setup_s3(articles=None)
        from src.batch.fetch_news import normalize_news
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
        from src.batch.fetch_news import normalize_news
        count = normalize_news(db_conn, TARGET_DATE)
        assert count == 0

    def test_returns_zero_on_empty_list(self, db_conn):
        self._setup_s3([])
        from src.batch.fetch_news import normalize_news
        count = normalize_news(db_conn, TARGET_DATE)
        assert count == 0
