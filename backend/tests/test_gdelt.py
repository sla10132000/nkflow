"""GDELT クライアントのテスト"""
import json
from unittest.mock import MagicMock, patch

import pytest

from src.news.gdelt import fetch_articles

FAKE_RESPONSE = {
    "articles": [
        {
            "url": "https://reuters.com/article1",
            "title": "Nikkei rises on positive data",
            "seendate": "2026-03-03T09:00:00Z",
            "domain": "reuters.com",
            "sourcename": "Reuters",
            "language": "English",
            "socialimage": "https://example.com/img.jpg",
        },
        {
            "url": "https://bloomberg.com/article2",
            "title": "Tokyo Stock Exchange sees surge",
            "seendate": "2026-03-03T08:00:00Z",
            "domain": "bloomberg.com",
            "sourcename": "Bloomberg",
            "language": "English",
            "socialimage": None,
        },
    ]
}


class TestFetchArticles:
    def _make_mock_response(self, data: dict) -> MagicMock:
        mock = MagicMock()
        mock.json.return_value = data
        mock.raise_for_status.return_value = None
        return mock

    def test_returns_articles(self):
        with patch("requests.get", return_value=self._make_mock_response(FAKE_RESPONSE)):
            result = fetch_articles(queries=['"Nikkei"'])
        assert len(result) == 2
        assert result[0]["url"] == "https://reuters.com/article1"

    def test_deduplicates_across_queries(self):
        # 2クエリで同じ記事が返っても重複しないこと
        with patch("requests.get", return_value=self._make_mock_response(FAKE_RESPONSE)):
            result = fetch_articles(queries=['"Nikkei"', '"Japan economy"'])
        assert len(result) == 2  # 重複排除で 2件のまま

    def test_handles_api_error_gracefully(self):
        with patch("requests.get", side_effect=Exception("timeout")):
            result = fetch_articles(queries=['"Nikkei"'])
        assert result == []

    def test_handles_http_error_gracefully(self):
        mock = MagicMock()
        mock.raise_for_status.side_effect = Exception("503 Service Unavailable")
        with patch("requests.get", return_value=mock):
            result = fetch_articles(queries=['"Nikkei"'])
        assert result == []

    def test_skips_articles_without_url(self):
        data = {"articles": [{"url": "", "title": "No URL article"}]}
        with patch("requests.get", return_value=self._make_mock_response(data)):
            result = fetch_articles(queries=['"Nikkei"'])
        assert result == []

    def test_empty_articles_key(self):
        with patch("requests.get", return_value=self._make_mock_response({"articles": []})):
            result = fetch_articles(queries=['"Nikkei"'])
        assert result == []

    def test_partial_query_failure_continues(self):
        # 1クエリ目が失敗、2クエリ目は成功
        def side_effect(url, **kwargs):
            if "Nikkei" in url:
                raise Exception("timeout")
            return self._make_mock_response(FAKE_RESPONSE)

        with patch("requests.get", side_effect=side_effect):
            result = fetch_articles(queries=['"Nikkei"', '"Japan economy"'])
        assert len(result) == 2
