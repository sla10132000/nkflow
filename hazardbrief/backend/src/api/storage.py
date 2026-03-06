"""API Lambda 用 SQLite ロード (S3 キャッシュ付き)"""
import logging
import os
import sqlite3
import time

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

# /tmp キャッシュの有効期間 (秒): 10分
_CACHE_TTL = 600

# キャッシュ状態
_last_download_time: float = 0.0


def get_db_path() -> str:
    """SQLite ファイルパスを返す (環境変数 or デフォルト)。"""
    return os.environ.get("SQLITE_PATH", "/tmp/hazardbrief.db")


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
        # ローカル DB がなければ初期化して返す
        _init_new_db(db_path)
        return db_path

    if os.path.exists(db_path) and (now - _last_download_time) < _CACHE_TTL:
        return db_path

    _download_sqlite(db_path)
    _last_download_time = now
    return db_path


def _init_new_db(db_path: str) -> None:
    """空の DB を初期化する。"""
    import sys
    # Lambda: /var/task/scripts/  ローカル: backend/scripts/
    scripts_dir = os.path.join(os.path.dirname(__file__), "../..")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    from scripts.init_sqlite import init_sqlite
    init_sqlite(db_path)


def _download_sqlite(db_path: str) -> None:
    """S3 から SQLite をダウンロードする。"""
    from src.config import S3_SQLITE_KEY
    s3_bucket = os.environ["S3_BUCKET"]

    s3 = boto3.client("s3")
    try:
        s3.download_file(s3_bucket, S3_SQLITE_KEY, db_path)
        logger.info(f"SQLite を S3 からダウンロードしました: {db_path}")
    except ClientError as e:
        if e.response["Error"]["Code"] in ("NoSuchKey", "404"):
            logger.warning("SQLite が S3 に存在しません — 空のDBを初期化します")
            # 初回デプロイ時はスクリプトで初期化
            import sys
            sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))
            from scripts.init_sqlite import init_sqlite
            init_sqlite(db_path)
        else:
            raise


def upload_sqlite() -> None:
    """SQLite を S3 にアップロードする (書き込み後に呼び出す)。"""
    from src.config import S3_SQLITE_KEY
    s3_bucket = os.environ.get("S3_BUCKET", "")
    if not s3_bucket:
        return
    db_path = get_db_path()
    s3 = boto3.client("s3")
    s3.upload_file(db_path, s3_bucket, S3_SQLITE_KEY)
    logger.info(f"SQLite を S3 へアップロードしました: {S3_SQLITE_KEY}")


def get_connection() -> sqlite3.Connection:
    """読み取り専用 SQLite 接続を返す。"""
    db_path = ensure_db()
    uri = f"file:{db_path}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def writable_connection():
    """
    書き込み可能な SQLite 接続を返すコンテキストマネージャ。

    Usage:
        with writable_connection() as conn:
            conn.execute(...)
    """
    import contextlib

    @contextlib.contextmanager
    def _ctx():
        db_path = ensure_db()
        conn = sqlite3.connect(db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
        # 書き込み後にS3へ同期
        try:
            upload_sqlite()
        except Exception as e:
            logger.warning(f"S3 アップロード失敗 (無視): {e}")

    return _ctx()
