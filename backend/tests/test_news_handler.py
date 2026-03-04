"""news-fetch Lambda ハンドラーのテスト"""
import json
import os
import shutil
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


def _make_db(tmp_path) -> str:
    """テスト用の最小限 news_articles テーブルを持つ SQLite を作成する。"""
    db_path = str(tmp_path / "stocks.db")
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS news_articles (
            id TEXT PRIMARY KEY,
            published_at TEXT,
            source TEXT,
            source_name TEXT,
            title TEXT,
            title_ja TEXT,
            url TEXT,
            language TEXT,
            image_url TEXT,
            tickers_json TEXT,
            sentiment REAL,
            created_at TEXT
        )
    """)
    conn.commit()
    conn.close()
    return db_path


class TestLambdaHandler:
    def test_saves_articles_to_s3(self, tmp_path):
        fake_articles = [{"url": "https://example.com/1", "title": "Test"}]
        db_path = _make_db(tmp_path)
        mock_s3 = MagicMock()

        def fake_download(bucket, key, path):
            shutil.copy(db_path, path)

        mock_s3.download_file.side_effect = fake_download

        with patch("src.news.rss.fetch_feeds", return_value=fake_articles), \
             patch("boto3.client", return_value=mock_s3), \
             patch("src.batch.fetch_news.normalize_news", return_value=1):
            from src.news.handler import lambda_handler
            result = lambda_handler({"date": "2026-03-03"}, _make_context())

        assert result["statusCode"] == 200
        assert result["body"]["articles"] == 1
        mock_s3.put_object.assert_called_once()
        call_kwargs = mock_s3.put_object.call_args[1]
        assert call_kwargs["Key"] == "news/raw/2026-03-03.json"
        saved = json.loads(call_kwargs["Body"])
        assert saved == fake_articles

    def test_normalizes_articles_to_sqlite(self, tmp_path):
        fake_articles = [{"url": "https://example.com/1", "title": "Test"}]
        db_path = _make_db(tmp_path)
        mock_s3 = MagicMock()

        def fake_download(bucket, key, path):
            shutil.copy(db_path, path)

        mock_s3.download_file.side_effect = fake_download

        with patch("src.news.rss.fetch_feeds", return_value=fake_articles), \
             patch("boto3.client", return_value=mock_s3), \
             patch("src.batch.fetch_news.normalize_news", return_value=1) as mock_normalize:
            from src.news.handler import lambda_handler
            result = lambda_handler({"date": "2026-03-03"}, _make_context())

        assert result["statusCode"] == 200
        assert result["body"]["normalized"] == 1
        mock_normalize.assert_called_once()
        # stocks.db をアップロードしていることを確認
        mock_s3.upload_file.assert_called_once()
        upload_args = mock_s3.upload_file.call_args[0]
        assert upload_args[1] == "test-bucket"
        assert upload_args[2] == "data/stocks.db"

    def test_skips_normalize_when_no_articles(self):
        mock_s3 = MagicMock()
        mock_sns = MagicMock()

        def boto3_client(service, **kwargs):
            return mock_sns if service == "sns" else mock_s3

        with patch("src.news.rss.fetch_feeds", return_value=[]), \
             patch("boto3.client", side_effect=boto3_client):
            from src.news import handler
            handler.SNS_TOPIC_ARN = "arn:aws:sns:ap-northeast-1:123456789:test-topic"
            result = handler.lambda_handler({"date": "2026-03-03"}, _make_context())

        assert result["statusCode"] == 200
        assert result["body"]["articles"] == 0
        assert result["body"]["normalized"] == 0
        # 記事0件時は stocks.db をダウンロードしない
        mock_s3.download_file.assert_not_called()

    def test_sends_sns_when_all_feeds_fail(self):
        mock_s3 = MagicMock()
        mock_sns = MagicMock()

        def boto3_client(service, **kwargs):
            return mock_sns if service == "sns" else mock_s3

        with patch("src.news.rss.fetch_feeds", return_value=[]), \
             patch("boto3.client", side_effect=boto3_client):
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
             patch("boto3.client", side_effect=boto3_client):
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

    def test_continues_on_sqlite_download_failure(self):
        """stocks.db ダウンロード失敗時は normalized=0 で正常終了する。"""
        from botocore.exceptions import ClientError

        fake_articles = [{"url": "https://example.com/1", "title": "Test"}]
        mock_s3 = MagicMock()
        error_response = {"Error": {"Code": "NoSuchKey", "Message": "Not found"}}
        mock_s3.download_file.side_effect = ClientError(error_response, "download_file")

        with patch("src.news.rss.fetch_feeds", return_value=fake_articles), \
             patch("boto3.client", return_value=mock_s3):
            from src.news.handler import lambda_handler
            result = lambda_handler({"date": "2026-03-03"}, _make_context())

        assert result["statusCode"] == 200
        assert result["body"]["articles"] == 1
        assert result["body"]["normalized"] == 0
        mock_s3.upload_file.assert_not_called()

    def test_continues_on_sqlite_upload_failure(self, tmp_path):
        """stocks.db アップロード失敗時は normalized=0 を返すが、raw保存は成功する。"""
        fake_articles = [{"url": "https://example.com/1", "title": "Test"}]
        db_path = _make_db(tmp_path)
        mock_s3 = MagicMock()

        def fake_download(bucket, key, path):
            shutil.copy(db_path, path)

        mock_s3.download_file.side_effect = fake_download
        mock_s3.upload_file.side_effect = Exception("upload error")

        with patch("src.news.rss.fetch_feeds", return_value=fake_articles), \
             patch("boto3.client", return_value=mock_s3), \
             patch("src.batch.fetch_news.normalize_news", return_value=1):
            from src.news.handler import lambda_handler
            result = lambda_handler({"date": "2026-03-03"}, _make_context())

        assert result["statusCode"] == 200
        # raw JSON は保存成功 (put_object呼び出し済み)
        mock_s3.put_object.assert_called_once()
        # アップロード失敗 → normalized=0
        assert result["body"]["normalized"] == 0
