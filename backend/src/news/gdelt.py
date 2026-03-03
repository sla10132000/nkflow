"""GDELT DOC 2.0 API クライアント"""
import logging
from urllib.parse import urlencode

import requests

logger = logging.getLogger(__name__)

GDELT_BASE = "https://api.gdeltproject.org/api/v2/doc/doc"

# 4カテゴリのデフォルトクエリ
DEFAULT_QUERIES = [
    # 日本株
    '"Nikkei" OR "Tokyo Stock Exchange" OR "Japanese stocks"',
    # 日本経済・金融政策
    '"Japan economy" OR "Bank of Japan" OR "Japanese yen"',
    # 世界マクロ
    '"Wall Street" OR "Federal Reserve" OR "global markets"',
    # コモディティ (エネルギー・貴金属・穀物)
    '"crude oil" OR "gold price" OR "wheat corn" OR "natural gas" OR "commodity markets"',
]


def fetch_articles(
    queries: list[str] | None = None,
    timespan: str = "1d",
    max_records: int = 50,
    source_lang: str = "English",
) -> list[dict]:
    """GDELT DOC 2.0 API から記事を取得。URL ベースで重複排除して返す。

    Args:
        queries: 検索クエリのリスト。None の場合は DEFAULT_QUERIES を使用。
        timespan: 取得期間 ("1d", "12h" 等)。
        max_records: 1クエリあたりの最大取得件数 (上限 250)。
        source_lang: 記事言語フィルタ。

    Returns:
        重複排除済み記事リスト。各要素は dict:
          url, title, seendate, socialimage, domain, language, sourcecountry
    """
    if queries is None:
        queries = DEFAULT_QUERIES

    seen_urls: set[str] = set()
    articles: list[dict] = []

    for query in queries:
        params = {
            "query": query,
            "mode": "artlist",
            "maxrecords": max_records,
            "format": "json",
            "sort": "DateDesc",
            "timespan": timespan,
            "sourcelang": source_lang,
        }
        url = f"{GDELT_BASE}?{urlencode(params)}"

        try:
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.warning(f"GDELT 取得失敗 (query={query!r}): {e}")
            continue

        for art in data.get("articles") or []:
            art_url = art.get("url", "")
            if not art_url or art_url in seen_urls:
                continue
            seen_urls.add(art_url)
            articles.append(art)

    logger.info(f"GDELT: {len(articles)} 件取得 (クエリ数={len(queries)})")
    return articles
