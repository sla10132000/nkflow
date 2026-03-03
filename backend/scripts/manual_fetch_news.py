#!/usr/bin/env python3
"""手動 RSS ニュース取得・登録スクリプト

1. RSS フィードを取得
2. S3 に news/raw/{date}.json として保存
3. S3 から stocks.db をダウンロード
4. normalize_news() で SQLite に登録
5. stocks.db を S3 にアップロード
"""
import json
import logging
import sqlite3
import subprocess
import sys
from datetime import date

import boto3

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)

S3_BUCKET = "nkflow-data-268914462689"
SQLITE_PATH = "/tmp/stocks.db"
today = date.today().isoformat()


def main() -> None:
    target_date = sys.argv[1] if len(sys.argv) > 1 else today
    logger.info(f"対象日: {target_date}")

    # 1. RSS フィード取得
    logger.info("=== Step 1: RSS フィード取得 ===")
    from src.news.rss import fetch_feeds
    articles = fetch_feeds()
    logger.info(f"取得記事数: {len(articles)}")

    if not articles:
        logger.error("記事が0件です。フィードの状態を確認してください。")
        sys.exit(1)

    # 2. S3 に raw JSON 保存
    logger.info("=== Step 2: S3 に raw JSON 保存 ===")
    s3_key = f"news/raw/{target_date}.json"
    s3 = boto3.client("s3")
    s3.put_object(
        Bucket=S3_BUCKET,
        Key=s3_key,
        Body=json.dumps(articles, ensure_ascii=False),
        ContentType="application/json; charset=utf-8",
    )
    logger.info(f"保存完了: s3://{S3_BUCKET}/{s3_key}")

    # 3. S3 から stocks.db ダウンロード
    logger.info("=== Step 3: stocks.db ダウンロード ===")
    subprocess.run(
        ["aws", "s3", "cp", f"s3://{S3_BUCKET}/data/stocks.db", SQLITE_PATH],
        check=True,
    )
    logger.info(f"ダウンロード完了: {SQLITE_PATH}")

    # 4. normalize_news() で SQLite に登録
    logger.info("=== Step 4: SQLite に記事登録 ===")
    from src.batch.fetch_news import normalize_news
    conn = sqlite3.connect(SQLITE_PATH)
    try:
        count = normalize_news(conn, target_date)
        logger.info(f"登録件数: {count}")
    finally:
        conn.close()

    # 5. stocks.db を S3 にアップロード
    logger.info("=== Step 5: stocks.db を S3 にアップロード ===")
    subprocess.run(
        ["aws", "s3", "cp", SQLITE_PATH, f"s3://{S3_BUCKET}/data/stocks.db"],
        check=True,
    )
    logger.info("アップロード完了")

    logger.info(f"=== 完了: {count} 件の記事を {target_date} で登録しました ===")


if __name__ == "__main__":
    main()
