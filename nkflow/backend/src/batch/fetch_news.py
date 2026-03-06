"""Phase 18/19: S3 の raw ニュース JSON → SQLite news_articles テーブルに正規化"""
import hashlib
import json
import logging
import sqlite3
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional
from urllib.parse import urlparse

import boto3
from botocore.exceptions import ClientError

from src.config import S3_BUCKET

logger = logging.getLogger(__name__)

S3_NEWS_RAW_PREFIX = "news/raw"


def _article_id(url: str) -> str:
    """URL から SHA256[:16] で記事 ID を生成する。"""
    return hashlib.sha256(url.encode()).hexdigest()[:16]


def _domain(url: str) -> str:
    """URL からドメイン名を抽出する。"""
    try:
        return urlparse(url).netloc or url[:64]
    except Exception:
        return url[:64]


def _translate_titles(titles: list[str], max_workers: int = 8) -> list[Optional[str]]:
    """Amazon Translate で英語タイトルを日本語に翻訳する。

    Args:
        titles: 翻訳対象の英語タイトルリスト。
        max_workers: 並列翻訳ワーカー数。

    Returns:
        翻訳結果リスト。失敗した場合は None。
    """
    translate = boto3.client("translate", region_name="ap-northeast-1")
    results: list[Optional[str]] = [None] * len(titles)

    def _translate_one(idx: int, text: str) -> tuple[int, Optional[str]]:
        try:
            resp = translate.translate_text(
                Text=text,
                SourceLanguageCode="en",
                TargetLanguageCode="ja",
            )
            return idx, resp["TranslatedText"]
        except Exception as e:
            logger.warning(f"翻訳失敗 (idx={idx}): {e}")
            return idx, None

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_translate_one, i, t): i for i, t in enumerate(titles)}
        for future in as_completed(futures):
            idx, translated = future.result()
            results[idx] = translated

    return results


def normalize_news(conn: sqlite3.Connection, target_date: str) -> int:
    """S3 の raw JSON を読み、news_articles に INSERT OR REPLACE する。

    Phase 19: 英語記事は Amazon Translate で title_ja を生成。
              日本語記事 (language=Japanese) は title をそのまま title_ja に使用。

    Args:
        conn: SQLite 接続。
        target_date: 対象日 (YYYY-MM-DD)。

    Returns:
        挿入/更新した行数。S3 に raw がない場合は 0。
    """
    s3_key = f"{S3_NEWS_RAW_PREFIX}/{target_date}.json"
    s3 = boto3.client("s3")

    try:
        obj = s3.get_object(Bucket=S3_BUCKET, Key=s3_key)
        articles: list[dict] = json.loads(obj["Body"].read())
    except ClientError as e:
        code = e.response["Error"]["Code"]
        if code in ("NoSuchKey", "404"):
            logger.info(f"ニュース raw データなし (news-fetch 未実行の可能性): {s3_key}")
            return 0
        logger.warning(f"S3 取得失敗 ({s3_key}): {e}")
        return 0
    except Exception as e:
        logger.warning(f"ニュース raw 読み込み失敗: {e}")
        return 0

    if not articles:
        return 0

    # 有効な記事を事前フィルタ
    valid_articles = [
        art for art in articles
        if art.get("url") and art.get("title")
    ]
    if not valid_articles:
        return 0

    # 英語記事のインデックスとタイトルを収集して一括翻訳
    english_indices = [
        i for i, art in enumerate(valid_articles)
        if art.get("language", "English") != "Japanese"
    ]
    english_titles = [valid_articles[i]["title"] for i in english_indices]

    translated: dict[int, Optional[str]] = {}
    if english_titles:
        logger.info(f"Amazon Translate: {len(english_titles)} 件を翻訳中...")
        translate_results = _translate_titles(english_titles)
        translated = {english_indices[j]: t for j, t in enumerate(translate_results)}
        logger.info(f"翻訳完了: {sum(1 for t in translate_results if t is not None)} 件成功")

    rows = []
    for i, art in enumerate(valid_articles):
        url = art["url"]
        title = art["title"]
        language = art.get("language", "English")

        if language == "Japanese":
            title_ja = title
        else:
            title_ja = translated.get(i)

        rows.append((
            _article_id(url),
            art.get("seendate", ""),
            _domain(url),
            art.get("sourcename") or art.get("domain", ""),
            title,
            title_ja,
            url,
            language,
            art.get("socialimage") or None,
        ))

    conn.executemany(
        """
        INSERT OR REPLACE INTO news_articles
            (id, published_at, source, source_name, title, title_ja, url, language, image_url)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    conn.commit()

    logger.info(f"ニュース正規化: {len(rows)} 件 ({target_date})")
    return len(rows)
