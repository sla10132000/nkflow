"""news-fetch Lambda エントリポイント: RSS → S3 raw JSON 保存 + SQLite 正規化"""
import json
import logging
import os
import sqlite3
from datetime import date

import boto3

from src.news import rss

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

S3_BUCKET = os.environ["S3_BUCKET"]
SNS_TOPIC_ARN = os.environ.get("SNS_TOPIC_ARN", "")
S3_SQLITE_KEY = "data/stocks.db"
SQLITE_PATH = "/tmp/stocks.db"


def lambda_handler(event: dict, context) -> dict:
    """RSS フィードからニュースを取得し S3 に raw JSON として保存する。
    その後 stocks.db に正規化して S3 に書き戻す。

    Event:
        date (str, optional): 対象日 YYYY-MM-DD。省略時は今日。

    Returns:
        {"statusCode": 200, "body": {"date": str, "articles": int, "normalized": int}}
    """
    date_str = event.get("date") or date.today().isoformat()

    articles = rss.fetch_feeds()

    if not articles and SNS_TOPIC_ARN:
        _notify_failure(date_str)

    s3_key = f"news/raw/{date_str}.json"
    s3 = boto3.client("s3")
    try:
        s3.put_object(
            Bucket=S3_BUCKET,
            Key=s3_key,
            Body=json.dumps(articles, ensure_ascii=False),
            ContentType="application/json; charset=utf-8",
        )
        logger.info(f"S3 保存完了: s3://{S3_BUCKET}/{s3_key} ({len(articles)} 件)")
    except Exception as e:
        logger.error(f"S3 保存失敗: {e}")
        return {"statusCode": 500, "body": {"error": str(e)}}

    # stocks.db に正規化 (失敗しても raw 保存は成功扱い)
    normalized = _normalize_to_sqlite(date_str)

    return {
        "statusCode": 200,
        "body": {"date": date_str, "articles": len(articles), "normalized": normalized},
    }


def _normalize_to_sqlite(date_str: str) -> int:
    """stocks.db をダウンロードしてニュースを正規化し S3 に書き戻す。

    Returns:
        正規化した件数。失敗時は -1。
    """
    s3 = boto3.client("s3")

    # stocks.db を S3 からダウンロード
    try:
        s3.download_file(S3_BUCKET, S3_SQLITE_KEY, SQLITE_PATH)
        logger.info(f"stocks.db を S3 から取得: s3://{S3_BUCKET}/{S3_SQLITE_KEY}")
    except Exception as e:
        logger.warning(f"stocks.db ダウンロード失敗 (正規化スキップ): {e}")
        return -1

    try:
        conn = sqlite3.connect(SQLITE_PATH)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        from src.batch.fetch_news import normalize_news
        count = normalize_news(conn, date_str)
        conn.close()
        logger.info(f"ニュース正規化完了: {count} 件 ({date_str})")
    except Exception as e:
        logger.error(f"ニュース正規化失敗: {e}")
        return -1

    # stocks.db を S3 に書き戻し
    try:
        conn = sqlite3.connect(SQLITE_PATH)
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        conn.close()
        s3.upload_file(SQLITE_PATH, S3_BUCKET, S3_SQLITE_KEY)
        logger.info(f"stocks.db を S3 に書き戻し: s3://{S3_BUCKET}/{S3_SQLITE_KEY}")
    except Exception as e:
        logger.error(f"stocks.db アップロード失敗: {e}")
        return -1

    return count


def _notify_failure(date_str: str) -> None:
    """全フィード失敗時に SNS で通知する。"""
    try:
        boto3.client("sns").publish(
            TopicArn=SNS_TOPIC_ARN,
            Subject=f"[nkflow] ニュース取得失敗 {date_str}",
            Message=(
                f"RSS フィードからの記事取得が全件失敗しました。\n"
                f"対象日: {date_str}\n"
                f"CloudWatch Logs を確認してください: /aws/lambda/nkflow-news-fetch"
            ),
        )
        logger.info("SNS 通知送信済み (全フィード失敗)")
    except Exception as e:
        logger.error(f"SNS 通知失敗: {e}")
