"""RSS フィードクライアント: 複数の金融ニュース RSS を取得・正規化"""
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Optional

import feedparser

logger = logging.getLogger(__name__)

FEEDS: dict[str, str] = {
    "nhk_biz":      "https://www3.nhk.or.jp/rss/news/cat6.xml",
    "nikkei_asia":  "https://asia.nikkei.com/rss/feed/nar",
    "investing_fx": "https://www.investing.com/rss/news_25.rss",
    "investing_jp": "https://www.investing.com/rss/news_301.rss",
    "cnbc_markets": "https://www.cnbc.com/id/15838459/device/rss/rss.html",
    "mw_top":       "https://feeds.content.dowjones.io/public/rss/mw_topstories",
    "ft_markets":   "https://www.ft.com/markets?format=rss",
}

REQUEST_TIMEOUT = 10  # 秒


def _parse_date(entry: dict) -> str:
    """RSS エントリの日付を ISO 8601 文字列に変換する。"""
    # feedparser が parsed tuple を提供する場合
    if entry.get("published_parsed"):
        try:
            dt = datetime(*entry["published_parsed"][:6], tzinfo=timezone.utc)
            return dt.isoformat()
        except Exception:
            pass
    # RFC 2822 文字列をフォールバック
    raw = entry.get("published") or entry.get("updated", "")
    if raw:
        try:
            return parsedate_to_datetime(raw).isoformat()
        except Exception:
            return raw
    # nikkei_asia 等: 日付フィールドなし → 取得時刻を使用
    return datetime.now(timezone.utc).isoformat()


def _fetch_one(feed_id: str, url: str) -> list[dict]:
    """単一フィードを取得してパースする。"""
    try:
        feed = feedparser.parse(
            url,
            request_headers={"User-Agent": "nkflow-news/1.0"},
        )
        if feed.bozo and not feed.entries:
            logger.warning(f"RSS パース失敗 ({feed_id}): {feed.bozo_exception}")
            return []

        articles = []
        for entry in feed.entries:
            link = entry.get("link", "")
            title = entry.get("title", "")
            if not link or not title:
                continue

            articles.append({
                "url": link,
                "title": title,
                "seendate": _parse_date(entry),
                "domain": feed_id,
                "sourcename": feed.feed.get("title", feed_id),
                "language": "Japanese" if feed_id.startswith("nhk") else "English",
                "socialimage": _extract_image(entry),
            })
        logger.info(f"RSS {feed_id}: {len(articles)} 件取得")
        return articles
    except Exception as e:
        logger.warning(f"RSS 取得失敗 ({feed_id}): {e}")
        return []


def _extract_image(entry: dict) -> Optional[str]:
    """RSS エントリからサムネイル画像 URL を抽出する。"""
    # media:thumbnail
    for media in entry.get("media_thumbnail", []):
        if media.get("url"):
            return media["url"]
    # media:content
    for media in entry.get("media_content", []):
        if media.get("url") and "image" in media.get("type", "image"):
            return media["url"]
    # enclosure
    for enc in entry.get("enclosures", []):
        if enc.get("type", "").startswith("image"):
            return enc.get("href") or enc.get("url")
    return None


def fetch_feeds(
    feeds: dict[str, str] | None = None,
    max_workers: int = 4,
) -> list[dict]:
    """全フィードを並列取得し、URL ベースで重複排除して返す。

    Returns:
        GDELT 互換の記事リスト (handler.py / fetch_news.py と同じ構造)
    """
    if feeds is None:
        feeds = FEEDS

    seen_urls: set[str] = set()
    all_articles: list[dict] = []

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(_fetch_one, fid, url): fid
            for fid, url in feeds.items()
        }
        for future in as_completed(futures):
            fid = futures[future]
            try:
                articles = future.result()
            except Exception as e:
                logger.warning(f"RSS {fid} 例外: {e}")
                continue

            for art in articles:
                if art["url"] not in seen_urls:
                    seen_urls.add(art["url"])
                    all_articles.append(art)

    logger.info(f"RSS 合計: {len(all_articles)} 件 (フィード数={len(feeds)})")
    return all_articles
