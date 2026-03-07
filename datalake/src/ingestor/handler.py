"""
datalake-raw-ingestor Lambda エントリポイント。

SQS (← S3 PutObject 通知) に届いた raw JSON を処理し、stocks.db に反映する。
reservedConcurrentExecutions: 1 により同時実行が防止されているため、
stocks.db への書き込み競合は発生しない。

フロー:
  1. SQS レコードから S3 key を抽出
  2. S3 から raw JSON envelope を読み取り
  3. S3 から stocks.db をダウンロード
  4. dispatcher で適切な writer に振り分け
  5. WAL checkpoint
  6. stocks.db を S3 にアップロード
"""
import json
import logging
import os
import sqlite3
import sys
from typing import Any

import boto3
from botocore.exceptions import ClientError

# writer モジュールをインポートしてレジストリに登録する
import src.ingestor.writers.daily_prices  # noqa: F401

from src.ingestor.dispatcher import dispatch

logging.basicConfig(level=logging.INFO, stream=sys.stdout)
logger = logging.getLogger(__name__)

S3_BUCKET = os.environ["S3_BUCKET"]
SQLITE_PATH = "/tmp/stocks.db"
S3_SQLITE_KEY = "data/stocks.db"


def handler(event: dict, context: Any) -> dict:
    """SQS トリガーハンドラ。batchSize=1 のため常に 1 レコード処理。"""
    records = event.get("Records", [])
    if not records:
        logger.info("Records が空 — スキップ")
        return {"statusCode": 200, "body": "no records"}

    record = records[0]

    # SQS メッセージ本体は S3 イベント通知の JSON
    body = json.loads(record["body"])
    s3_event_records = body.get("Records", [])
    if not s3_event_records:
        logger.info("S3 イベントレコードが空 — スキップ (テスト通知等)")
        return {"statusCode": 200, "body": "empty s3 event"}

    s3_record = s3_event_records[0]
    s3_key = s3_record["s3"]["object"]["key"]
    logger.info(f"処理対象: s3://{S3_BUCKET}/{s3_key}")

    s3_client = boto3.client("s3")

    # ── raw JSON envelope を読み取り ──────────────────────────────
    try:
        obj = s3_client.get_object(Bucket=S3_BUCKET, Key=s3_key)
        envelope = json.loads(obj["Body"].read())
    except ClientError as e:
        logger.error(f"raw ファイル読み取り失敗: {e}")
        raise

    category = envelope.get("category", "")
    source = envelope.get("source", "")
    data_type = envelope.get("data_type", "")
    date_str = envelope.get("date", "")
    data = envelope.get("data", [])
    logger.info(f"envelope: category={category}, source={source}, data_type={data_type}, date={date_str}")

    # ── stocks.db をダウンロード ──────────────────────────────────
    try:
        s3_client.download_file(S3_BUCKET, S3_SQLITE_KEY, SQLITE_PATH)
        logger.info("stocks.db ダウンロード完了")
    except ClientError as e:
        logger.error(f"stocks.db ダウンロード失敗: {e}")
        raise

    # ── dispatch → writer ─────────────────────────────────────────
    conn = sqlite3.connect(SQLITE_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")

    rows_written = 0
    try:
        rows_written = dispatch(conn, category, source, data_type, date_str, data)
        conn.commit()
    except Exception as e:
        logger.error(f"dispatch 失敗: {e}")
        conn.rollback()
        raise
    finally:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        conn.close()

    # ── stocks.db をアップロード ──────────────────────────────────
    try:
        s3_client.upload_file(SQLITE_PATH, S3_BUCKET, S3_SQLITE_KEY)
        logger.info("stocks.db アップロード完了")
    except ClientError as e:
        logger.error(f"stocks.db アップロード失敗: {e}")
        raise

    return {
        "statusCode": 200,
        "body": {"key": s3_key, "rows_written": rows_written},
    }
