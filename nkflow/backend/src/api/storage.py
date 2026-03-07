"""API Lambda 用 SQLite ロード (S3 キャッシュ付き)"""
import logging
import os
import sqlite3
import time

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

# /tmp キャッシュの有効期間 (秒)
_CACHE_TTL = 600

# キャッシュ状態
_last_download_time: float = 0.0


def get_db_path() -> str:
    """SQLite ファイルパスを返す (環境変数 or デフォルト)。"""
    return os.environ.get("SQLITE_PATH", "/tmp/stocks.db")


def ensure_db() -> str:
    """
    SQLite を /tmp に用意する。キャッシュが有効ならダウンロードをスキップ。

    S3_BUCKET 未設定時はローカルファイルをそのまま使用する (ローカル開発モード)。

    Returns:
        SQLite ファイルパス
    """
    global _last_download_time

    db_path = get_db_path()
    now = time.time()

    # ローカル開発モード: S3_BUCKET 未設定ならローカルファイルをそのまま使用
    if not os.environ.get("S3_BUCKET"):
        if os.path.exists(db_path):
            return db_path
        raise FileNotFoundError(
            f"ローカルDBが見つかりません: {db_path}\n"
            "  → make pull でS3からダウンロードしてください"
        )

    if os.path.exists(db_path) and (now - _last_download_time) < _CACHE_TTL:
        return db_path

    _download_sqlite(db_path)
    _last_download_time = now
    return db_path


def _download_sqlite(db_path: str, max_retries: int = 3) -> None:
    """S3 から SQLite をダウンロードする。PreconditionFailed はリトライする。"""
    s3_bucket = os.environ["S3_BUCKET"]
    s3_key = "data/stocks.db"

    # ダウンロード中に旧ファイル + temp ファイルで /tmp 容量が 2x になるのを防ぐため
    # 先に旧ファイルを削除してからダウンロードする
    if os.path.exists(db_path):
        os.remove(db_path)
        logger.info(f"旧SQLiteを削除しました: {db_path}")

    s3 = boto3.client("s3")
    for attempt in range(1, max_retries + 1):
        try:
            s3.download_file(s3_bucket, s3_key, db_path)
            logger.info(f"SQLite を S3 からダウンロードしました: {db_path}")
            return
        except ClientError as e:
            code = e.response["Error"]["Code"]
            if code in ("NoSuchKey", "404"):
                logger.warning("SQLite が S3 に存在しません — 空のDBを使用します")
                return
            if code == "PreconditionFailed" and attempt < max_retries:
                # バッチが並行してアップロード中に ETag が変わる競合。少し待ってリトライ
                wait = attempt * 2
                logger.warning(
                    f"S3 PreconditionFailed (試行 {attempt}/{max_retries}) — "
                    f"{wait}秒後にリトライします"
                )
                if os.path.exists(db_path):
                    os.remove(db_path)
                time.sleep(wait)
                continue
            raise


def get_connection() -> sqlite3.Connection:
    """読み取り専用 SQLite 接続を返す。"""
    db_path = ensure_db()
    uri = f"file:{db_path}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn
