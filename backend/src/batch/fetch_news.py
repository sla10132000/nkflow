"""Phase 18: S3 の raw ニュース JSON → SQLite news_articles テーブルに正規化"""
import hashlib
import json
import logging
import sqlite3
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


def normalize_news(conn: sqlite3.Connection, target_date: str) -> int:
    """S3 の raw JSON を読み、news_articles に INSERT OR REPLACE する。

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

    rows = []
    for art in articles:
        url = art.get("url", "")
        title = art.get("title", "")
        if not url or not title:
            continue

        rows.append((
            _article_id(url),
            art.get("seendate", ""),
            _domain(url),
            art.get("sourcename") or art.get("domain", ""),
            title,
            url,
            art.get("language", "English"),
            art.get("socialimage") or None,
        ))

    if not rows:
        return 0

    conn.executemany(
        """
        INSERT OR REPLACE INTO news_articles
            (id, published_at, source, source_name, title, url, language, image_url)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    conn.commit()

    logger.info(f"ニュース正規化: {len(rows)} 件 ({target_date})")
    return len(rows)
