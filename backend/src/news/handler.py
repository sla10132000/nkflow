"""news-fetch Lambda エントリポイント: GDELT → S3 raw JSON 保存"""
import json
import logging
import os
from datetime import date

import boto3

from src.news import gdelt

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

S3_BUCKET = os.environ["S3_BUCKET"]


def lambda_handler(event: dict, context) -> dict:
    """GDELT からニュースを取得し S3 に raw JSON として保存する。

    Event:
        date (str, optional): 対象日 YYYY-MM-DD。省略時は今日。

    Returns:
        {"statusCode": 200, "body": {"date": str, "articles": int}}
    """
    date_str = event.get("date") or date.today().isoformat()

    articles = gdelt.fetch_articles()

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

    return {
        "statusCode": 200,
        "body": {"date": date_str, "articles": len(articles)},
    }
