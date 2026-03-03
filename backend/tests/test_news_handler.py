"""news-fetch Lambda ハンドラーのテスト"""
import json
import os
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

        with patch("src.news.gdelt.fetch_articles", return_value=fake_articles), \
             patch("boto3.client", return_value=mock_s3):
            from src.news.handler import lambda_handler
            result = lambda_handler({"date": "2026-03-03"}, _make_context())

        assert result["statusCode"] == 200
        assert result["body"]["articles"] == 1
        mock_s3.put_object.assert_called_once()
        call_kwargs = mock_s3.put_object.call_args[1]
        assert call_kwargs["Key"] == "news/raw/2026-03-03.json"
        saved = json.loads(call_kwargs["Body"])
        assert saved == fake_articles

    def test_sends_sns_when_all_queries_fail(self):
        mock_s3 = MagicMock()
        mock_sns = MagicMock()

        def boto3_client(service, **kwargs):
            return mock_sns if service == "sns" else mock_s3

        with patch("src.news.gdelt.fetch_articles", return_value=[]), \
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

        with patch("src.news.gdelt.fetch_articles", return_value=[]), \
             patch("boto3.client", side_effect=boto3_client):
            from src.news import handler
            handler.SNS_TOPIC_ARN = ""
            result = handler.lambda_handler({"date": "2026-03-03"}, _make_context())

        assert result["statusCode"] == 200
        mock_sns.publish.assert_not_called()

    def test_returns_500_on_s3_error(self):
        mock_s3 = MagicMock()
        mock_s3.put_object.side_effect = Exception("S3 connection error")

        with patch("src.news.gdelt.fetch_articles", return_value=[{"url": "u", "title": "t"}]), \
             patch("boto3.client", return_value=mock_s3):
            from src.news.handler import lambda_handler
            result = lambda_handler({}, _make_context())

        assert result["statusCode"] == 500
        assert "error" in result["body"]
