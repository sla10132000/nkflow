"""API Lambda 用 SQLite ロード (S3 キャッシュ付き)"""
import logging
import os
import sqlite3
import time

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

# /tmp キャッシュの有効期間 (秒)
_CACHE_TTL = 3600

# キャッシュ状態
_last_download_time: float = 0.0


def get_db_path() -> str:
    """SQLite ファイルパスを返す (環境変数 or デフォルト)。"""
    return os.environ.get("SQLITE_PATH", "/tmp/stocks.db")


def ensure_db() -> str:
    """
    SQLite を /tmp に用意する。キャッシュが有効ならダウンロードをスキップ。

    Returns:
        SQLite ファイルパス
    """
    global _last_download_time

    db_path = get_db_path()
    now = time.time()

    if os.path.exists(db_path) and (now - _last_download_time) < _CACHE_TTL:
        return db_path

    _download_sqlite(db_path)
    _last_download_time = now
    return db_path


def _download_sqlite(db_path: str) -> None:
    """S3 から SQLite をダウンロードする。"""
    s3_bucket = os.environ["S3_BUCKET"]
    s3_key = "data/stocks.db"

    s3 = boto3.client("s3")
    try:
        s3.download_file(s3_bucket, s3_key, db_path)
        logger.info(f"SQLite を S3 からダウンロードしました: {db_path}")
    except ClientError as e:
        if e.response["Error"]["Code"] in ("NoSuchKey", "404"):
            logger.warning("SQLite が S3 に存在しません — 空のDBを使用します")
        else:
            raise


def get_connection() -> sqlite3.Connection:
    """読み取り専用 SQLite 接続を返す。"""
    db_path = ensure_db()
    uri = f"file:{db_path}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn
