"""RSS フィードクライアントのテスト"""
import time
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


# ── ヘルパー: feedparser エントリ風 dict を作る ──────────────────────────


def _entry(**kwargs) -> dict:
    base = {
        "link": "https://example.com/article",
        "title": "Test Article",
        "published": "",
        "published_parsed": None,
        "updated": "",
        "media_thumbnail": [],
        "media_content": [],
        "enclosures": [],
    }
    base.update(kwargs)
    return base


def _feed_result(entries: list[dict], feed_title: str = "Test Feed", bozo: bool = False):
    """feedparser.parse() の戻り値を模倣する SimpleNamespace。
    feed.feed は FeedParserDict 互換の dict にする (.get() が必要)。
    """
    ns = SimpleNamespace()
    ns.entries = entries
    ns.bozo = bozo
    ns.bozo_exception = Exception("parse error") if bozo else None
    ns.feed = {"title": feed_title}
    return ns


# ── _parse_date ──────────────────────────────────────────────────────────


class TestParseDate:
    def test_published_parsed_takes_priority(self):
        from src.news.rss import _parse_date

        entry = _entry(published_parsed=(2026, 3, 3, 9, 0, 0, 0, 0, 0))
        result = _parse_date(entry)
        assert result == "2026-03-03T09:00:00+00:00"

    def test_rfc2822_fallback(self):
        from src.news.rss import _parse_date

        entry = _entry(published="Mon, 03 Mar 2026 09:00:00 +0000")
        result = _parse_date(entry)
        assert "2026-03-03" in result

    def test_no_date_returns_now(self):
        from src.news.rss import _parse_date

        before = datetime.now(timezone.utc)
        entry = _entry()  # published も published_parsed もなし
        result = _parse_date(entry)
        after = datetime.now(timezone.utc)

        # ISO 8601 形式で返り、大体 now に近い
        dt = datetime.fromisoformat(result)
        assert before <= dt <= after

    def test_invalid_rfc2822_returns_raw_string(self):
        from src.news.rss import _parse_date

        entry = _entry(published="not-a-date")
        result = _parse_date(entry)
        assert result == "not-a-date"


# ── _extract_image ────────────────────────────────────────────────────────


class TestExtractImage:
    def test_media_thumbnail(self):
        from src.news.rss import _extract_image

        entry = _entry(media_thumbnail=[{"url": "https://img.example.com/thumb.jpg"}])
        assert _extract_image(entry) == "https://img.example.com/thumb.jpg"

    def test_media_content_image(self):
        from src.news.rss import _extract_image

        entry = _entry(
            media_thumbnail=[],
            media_content=[{"url": "https://img.example.com/photo.jpg", "type": "image/jpeg"}],
        )
        assert _extract_image(entry) == "https://img.example.com/photo.jpg"

    def test_enclosure_image(self):
        from src.news.rss import _extract_image

        entry = _entry(
            media_thumbnail=[],
            media_content=[],
            enclosures=[{"type": "image/png", "href": "https://img.example.com/enc.png"}],
        )
        assert _extract_image(entry) == "https://img.example.com/enc.png"

    def test_no_image_returns_none(self):
        from src.news.rss import _extract_image

        entry = _entry()
        assert _extract_image(entry) is None

    def test_media_content_non_image_skipped(self):
        from src.news.rss import _extract_image

        entry = _entry(
            media_thumbnail=[],
            media_content=[{"url": "https://example.com/video.mp4", "type": "video/mp4"}],
        )
        assert _extract_image(entry) is None


# ── _fetch_one ────────────────────────────────────────────────────────────


class TestFetchOne:
    def test_returns_articles(self):
        from src.news.rss import _fetch_one

        entry = _entry(
            link="https://nhk.or.jp/news/1",
            title="NHK ニュース",
            published_parsed=(2026, 3, 3, 9, 0, 0, 0, 0, 0),
        )
        fake_result = _feed_result([entry], feed_title="NHK NEWS WEB")

        with patch("src.news.rss.feedparser.parse", return_value=fake_result):
            arts = _fetch_one("nhk_biz", "https://www3.nhk.or.jp/rss/news/cat6.xml")

        assert len(arts) == 1
        assert arts[0]["url"] == "https://nhk.or.jp/news/1"
        assert arts[0]["title"] == "NHK ニュース"
        assert arts[0]["domain"] == "nhk_biz"
        assert arts[0]["language"] == "Japanese"
        assert arts[0]["sourcename"] == "NHK NEWS WEB"

    def test_skips_entry_without_link(self):
        from src.news.rss import _fetch_one

        entry = _entry(link="", title="No Link Article")
        fake_result = _feed_result([entry])

        with patch("src.news.rss.feedparser.parse", return_value=fake_result):
            arts = _fetch_one("cnbc_markets", "https://cnbc.com/rss")

        assert arts == []

    def test_skips_entry_without_title(self):
        from src.news.rss import _fetch_one

        entry = _entry(link="https://example.com/a", title="")
        fake_result = _feed_result([entry])

        with patch("src.news.rss.feedparser.parse", return_value=fake_result):
            arts = _fetch_one("cnbc_markets", "https://cnbc.com/rss")

        assert arts == []

    def test_bozo_with_no_entries_returns_empty(self):
        from src.news.rss import _fetch_one

        fake_result = _feed_result([], bozo=True)

        with patch("src.news.rss.feedparser.parse", return_value=fake_result):
            arts = _fetch_one("ft_markets", "https://ft.com/rss")

        assert arts == []

    def test_bozo_with_entries_still_parsed(self):
        """bozo=True でもエントリがあれば返す"""
        from src.news.rss import _fetch_one

        entry = _entry(link="https://ft.com/1", title="FT Article")
        fake_result = _feed_result([entry], bozo=True)

        with patch("src.news.rss.feedparser.parse", return_value=fake_result):
            arts = _fetch_one("ft_markets", "https://ft.com/rss")

        assert len(arts) == 1

    def test_exception_returns_empty(self):
        from src.news.rss import _fetch_one

        with patch("src.news.rss.feedparser.parse", side_effect=Exception("network error")):
            arts = _fetch_one("mw_top", "https://example.com/rss")

        assert arts == []

    def test_english_language_for_non_nhk(self):
        from src.news.rss import _fetch_one

        entry = _entry(link="https://cnbc.com/1", title="CNBC Story")
        fake_result = _feed_result([entry])

        with patch("src.news.rss.feedparser.parse", return_value=fake_result):
            arts = _fetch_one("cnbc_markets", "https://cnbc.com/rss")

        assert arts[0]["language"] == "English"

    @pytest.mark.parametrize("feed_id,expected_lang", [
        ("yahoo_jp_biz", "Japanese"),
        ("yahoo_jp_world", "Japanese"),
        ("toyokeizai", "Japanese"),
        ("bloomberg_mkts", "English"),
        ("japan_today", "Japanese"),
        ("reuters_top_ja", "Japanese"),
    ])
    def test_language_detection_for_feeds(self, feed_id, expected_lang):
        from src.news.rss import _fetch_one

        entry = _entry(link="https://example.com/1", title="記事タイトル")
        fake_result = _feed_result([entry])

        with patch("src.news.rss.feedparser.parse", return_value=fake_result):
            arts = _fetch_one(feed_id, "https://example.com/rss")

        assert arts[0]["language"] == expected_lang


# ── fetch_feeds ───────────────────────────────────────────────────────────


class TestFetchFeeds:
    def test_deduplicates_by_url(self):
        from src.news.rss import fetch_feeds

        article = {
            "url": "https://example.com/dup",
            "title": "Dup",
            "seendate": "2026-03-03T09:00:00+00:00",
            "domain": "feed_a",
            "sourcename": "Feed A",
            "language": "English",
            "socialimage": None,
        }

        def fake_fetch_one(feed_id, url):
            return [article]

        with patch("src.news.rss._fetch_one", side_effect=fake_fetch_one):
            results = fetch_feeds(feeds={"feed_a": "https://a.com/rss", "feed_b": "https://b.com/rss"})

        # 2フィードが同じ URL を返しても 1 件のみ
        assert len(results) == 1

    def test_aggregates_all_feeds(self):
        from src.news.rss import fetch_feeds

        def fake_fetch_one(feed_id, url):
            return [{
                "url": f"https://example.com/{feed_id}",
                "title": feed_id,
                "seendate": "2026-03-03T09:00:00+00:00",
                "domain": feed_id,
                "sourcename": feed_id,
                "language": "English",
                "socialimage": None,
            }]

        feeds = {"feed_a": "https://a.com/rss", "feed_b": "https://b.com/rss"}
        with patch("src.news.rss._fetch_one", side_effect=fake_fetch_one):
            results = fetch_feeds(feeds=feeds)

        assert len(results) == 2

    def test_returns_empty_when_all_feeds_fail(self):
        from src.news.rss import fetch_feeds

        with patch("src.news.rss._fetch_one", return_value=[]):
            results = fetch_feeds(feeds={"bad_feed": "https://bad.com/rss"})

        assert results == []

    def test_uses_default_feeds_when_none(self):
        from src.news.rss import FEEDS, fetch_feeds

        called_ids = []

        def fake_fetch_one(feed_id, url):
            called_ids.append(feed_id)
            return []

        with patch("src.news.rss._fetch_one", side_effect=fake_fetch_one):
            fetch_feeds()

        assert set(called_ids) == set(FEEDS.keys())
