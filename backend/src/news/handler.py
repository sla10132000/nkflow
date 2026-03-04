"""news-fetch Lambda エントリポイント: RSS → S3 raw JSON 保存 + SQLite 正規化"""
import json
import logging
import os
import sqlite3
import tempfile
from datetime import date

import boto3
from botocore.exceptions import ClientError

from src.news import rss

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

S3_BUCKET = os.environ["S3_BUCKET"]
S3_SQLITE_KEY = "data/stocks.db"
SNS_TOPIC_ARN = os.environ.get("SNS_TOPIC_ARN", "")


def lambda_handler(event: dict, context) -> dict:
    """RSS フィードからニュースを取得し S3 raw JSON 保存後、SQLite に正規化する。

    Event:
        date (str, optional): 対象日 YYYY-MM-DD。省略時は今日。

    Returns:
        {"statusCode": 200, "body": {"date": str, "articles": int, "normalized": int}}
    """
    date_str = event.get("date") or date.today().isoformat()

    articles = rss.fetch_feeds()

    if not articles and SNS_TOPIC_ARN:
        _notify_failure(date_str)

    # Step 1: S3 に raw JSON を保存
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

    if not articles:
        return {
            "statusCode": 200,
            "body": {"date": date_str, "articles": 0, "normalized": 0},
        }

    # Step 2: SQLite をダウンロードして正規化し、アップロード
    normalized = _normalize_to_sqlite(date_str)

    return {
        "statusCode": 200,
        "body": {"date": date_str, "articles": len(articles), "normalized": normalized},
    }


def _normalize_to_sqlite(date_str: str) -> int:
    """S3 から stocks.db をダウンロードし、正規化してアップロードする。

    同時書き込みリスクを最小化するため:
    - ダウンロード → 正規化 → WAL チェックポイント → アップロードの順で実行
    - アップロード失敗時はログのみで続行 (次回バッチで補完される)

    Returns:
        正規化した記事数。失敗時は 0。
    """
    from src.batch.fetch_news import normalize_news

    s3 = boto3.client("s3")
    tmp_path = os.path.join(tempfile.gettempdir(), "news_stocks.db")

    # stocks.db をダウンロード
    try:
        s3.download_file(S3_BUCKET, S3_SQLITE_KEY, tmp_path)
        logger.info(f"stocks.db をダウンロード: {tmp_path}")
    except ClientError as e:
        code = e.response["Error"]["Code"]
        if code in ("NoSuchKey", "404"):
            logger.warning("stocks.db が S3 に存在しません — 正規化をスキップ")
        else:
            logger.error(f"stocks.db ダウンロード失敗: {e}")
        return 0
    except Exception as e:
        logger.error(f"stocks.db ダウンロード失敗: {e}")
        return 0

    count = 0
    try:
        conn = sqlite3.connect(tmp_path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=10000")
        try:
            count = normalize_news(conn, date_str)
            logger.info(f"正規化完了: {count} 件 ({date_str})")
        finally:
            # WAL をフラッシュしてからアップロード
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            conn.close()
    except Exception as e:
        logger.error(f"正規化失敗: {e}")
        return 0

    # アップロード
    try:
        s3.upload_file(tmp_path, S3_BUCKET, S3_SQLITE_KEY)
        logger.info(f"stocks.db をアップロード: s3://{S3_BUCKET}/{S3_SQLITE_KEY}")
    except Exception as e:
        logger.error(f"stocks.db アップロード失敗 (次回バッチで補完): {e}")
        return 0
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

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
