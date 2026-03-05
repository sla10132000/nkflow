"""news-fetch Lambda ハンドラーのテスト"""
import json
import os
import sqlite3
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.setenv("S3_BUCKET", "test-bucket")
    monkeypatch.setenv("SNS_TOPIC_ARN", "arn:aws:sns:ap-northeast-1:123456789:test-topic")


def _make_context():
    ctx = MagicMock()
    ctx.aws_request_id = "test-request-id"
    return ctx


class TestLambdaHandler:
    def test_saves_articles_to_s3(self):
        fake_articles = [{"url": "https://example.com/1", "title": "Test"}]
        mock_s3 = MagicMock()

        with patch("src.news.rss.fetch_feeds", return_value=fake_articles), \
             patch("boto3.client", return_value=mock_s3), \
             patch("src.news.handler._normalize_to_sqlite", return_value=1):
            from src.news.handler import lambda_handler
            result = lambda_handler({"date": "2026-03-03"}, _make_context())

        assert result["statusCode"] == 200
        assert result["body"]["articles"] == 1
        assert result["body"]["normalized"] == 1
        mock_s3.put_object.assert_called_once()
        call_kwargs = mock_s3.put_object.call_args[1]
        assert call_kwargs["Key"] == "news/raw/2026-03-03.json"
        saved = json.loads(call_kwargs["Body"])
        assert saved == fake_articles

    def test_sends_sns_when_all_feeds_fail(self):
        mock_s3 = MagicMock()
        mock_sns = MagicMock()

        def boto3_client(service, **kwargs):
            return mock_sns if service == "sns" else mock_s3

        with patch("src.news.rss.fetch_feeds", return_value=[]), \
             patch("boto3.client", side_effect=boto3_client), \
             patch("src.news.handler._normalize_to_sqlite", return_value=0):
            from src.news import handler
            # SNS_TOPIC_ARN を確実にセット
            handler.SNS_TOPIC_ARN = "arn:aws:sns:ap-northeast-1:123456789:test-topic"
            result = handler.lambda_handler({"date": "2026-03-03"}, _make_context())

        assert result["statusCode"] == 200
        assert result["body"]["articles"] == 0
        mock_sns.publish.assert_called_once()
        call_kwargs = mock_sns.publish.call_args[1]
        assert "ニュース取得失敗" in call_kwargs["Subject"]

    def test_no_sns_when_topic_arn_empty(self, monkeypatch):
        monkeypatch.setenv("SNS_TOPIC_ARN", "")
        mock_s3 = MagicMock()
        mock_sns = MagicMock()

        def boto3_client(service, **kwargs):
            return mock_sns if service == "sns" else mock_s3

        with patch("src.news.rss.fetch_feeds", return_value=[]), \
             patch("boto3.client", side_effect=boto3_client), \
             patch("src.news.handler._normalize_to_sqlite", return_value=0):
            from src.news import handler
            handler.SNS_TOPIC_ARN = ""
            result = handler.lambda_handler({"date": "2026-03-03"}, _make_context())

        assert result["statusCode"] == 200
        mock_sns.publish.assert_not_called()

    def test_returns_500_on_s3_error(self):
        mock_s3 = MagicMock()
        mock_s3.put_object.side_effect = Exception("S3 connection error")

        with patch("src.news.rss.fetch_feeds", return_value=[{"url": "u", "title": "t"}]), \
             patch("boto3.client", return_value=mock_s3):
            from src.news.handler import lambda_handler
            result = lambda_handler({}, _make_context())

        assert result["statusCode"] == 500
        assert "error" in result["body"]


class TestNormalizeToSqlite:
    def test_normalizes_news_and_uploads(self, tmp_path):
        """正常系: SQLite ダウンロード → 正規化 → アップロード"""
        # S3 "上" にある DB ファイル (コピー元)
        source_db = str(tmp_path / "source.db")
        # Lambda の /tmp に展開される先
        dest_db = str(tmp_path / "stocks.db")

        conn = sqlite3.connect(source_db)
        conn.execute("""
            CREATE TABLE news_articles (
                id TEXT PRIMARY KEY,
                published_at TEXT,
                source TEXT,
                source_name TEXT,
                title TEXT,
                title_ja TEXT,
                url TEXT,
                language TEXT,
                image_url TEXT,
                sentiment REAL,
                category TEXT,
                created_at TEXT
            )
        """)
        conn.commit()
        conn.close()

        mock_s3 = MagicMock()

        def fake_download(bucket, key, path):
            import shutil
            shutil.copy(source_db, path)

        mock_s3.download_file.side_effect = fake_download

        with patch("boto3.client", return_value=mock_s3), \
             patch("src.batch.fetch_news.normalize_news", return_value=1) as mock_normalize, \
             patch("src.news.handler.SQLITE_PATH", dest_db):
            from src.news.handler import _normalize_to_sqlite
            result = _normalize_to_sqlite("2026-03-03")

        assert result == 1
        mock_normalize.assert_called_once()
        mock_s3.upload_file.assert_called_once()

    def test_returns_minus1_when_download_fails(self, tmp_path):
        """stocks.db ダウンロード失敗時は -1 を返す"""
        from botocore.exceptions import ClientError
        mock_s3 = MagicMock()
        mock_s3.download_file.side_effect = Exception("NoSuchKey")

        with patch("boto3.client", return_value=mock_s3):
            from src.news.handler import _normalize_to_sqlite
            result = _normalize_to_sqlite("2026-03-03")

        assert result == -1
        mock_s3.upload_file.assert_not_called()

    def test_returns_minus1_when_normalize_fails(self, tmp_path):
        """normalize_news 失敗時は -1 を返し、アップロードしない"""
        db_path = str(tmp_path / "stocks.db")
        sqlite3.connect(db_path).close()

        mock_s3 = MagicMock()

        def fake_download(bucket, key, path):
            import shutil
            shutil.copy(db_path, path)

        mock_s3.download_file.side_effect = fake_download

        with patch("boto3.client", return_value=mock_s3), \
             patch("src.batch.fetch_news.normalize_news", side_effect=Exception("DB error")), \
             patch("src.news.handler.SQLITE_PATH", db_path):
            from src.news.handler import _normalize_to_sqlite
            result = _normalize_to_sqlite("2026-03-03")

        assert result == -1
        mock_s3.upload_file.assert_not_called()
