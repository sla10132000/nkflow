"""portfolio.db の S3 同期と接続管理

stocks.db (読み取り専用) とは異なり、portfolio.db はユーザーが書き込む。
- S3 キー: data/portfolio.db
- ローカルパス: /tmp/portfolio.db (Lambda エフェメラルストレージ)

書き込みフロー:
  1. S3 から最新 portfolio.db をダウンロード
  2. 書き込み操作を実行
  3. S3 にアップロード

読み取りフロー:
  - /tmp/portfolio.db が存在し TTL 以内ならキャッシュ使用
  - それ以外は S3 からダウンロード
"""
import logging
import os
import sqlite3
import time
from contextlib import contextmanager
from typing import Generator

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

S3_PORTFOLIO_KEY = "data/portfolio.db"
_PORTFOLIO_CACHE_TTL = 3600  # 読み取り用キャッシュの有効期間 (秒)
_last_read_download_time: float = 0.0


def get_portfolio_db_path() -> str:
    return os.environ.get("PORTFOLIO_DB_PATH", "/tmp/portfolio.db")


# ──────────────────────────────────────────────
# 内部: S3 ダウンロード / アップロード
# ──────────────────────────────────────────────

def _download_portfolio(db_path: str) -> None:
    """S3 から portfolio.db をダウンロードする。存在しない場合は空スキーマを作成する。"""
    from scripts.migrate_phase15 import init_portfolio_db

    bucket = os.environ["S3_BUCKET"]
    s3 = boto3.client("s3")
    try:
        s3.download_file(bucket, S3_PORTFOLIO_KEY, db_path)
        logger.info("portfolio.db を S3 からダウンロードしました")
    except ClientError as e:
        if e.response["Error"]["Code"] in ("NoSuchKey", "404"):
            logger.info("portfolio.db が S3 に存在しません — 新規作成します")
            init_portfolio_db(db_path)
        else:
            raise


def _upload_portfolio(db_path: str) -> None:
    """portfolio.db を S3 にアップロードする。"""
    if not os.path.exists(db_path):
        logger.warning("portfolio.db が存在しないためアップロードをスキップします")
        return

    bucket = os.environ["S3_BUCKET"]
    s3 = boto3.client("s3")
    s3.upload_file(db_path, bucket, S3_PORTFOLIO_KEY)
    logger.info("portfolio.db を S3 にアップロードしました")


# ──────────────────────────────────────────────
# 読み取り用接続 (FastAPI Depends で使用)
# ──────────────────────────────────────────────

def ensure_portfolio_db() -> str:
    """読み取り用に portfolio.db を /tmp に用意する (TTL キャッシュあり)。"""
    global _last_read_download_time

    db_path = get_portfolio_db_path()
    now = time.time()

    if os.path.exists(db_path) and (now - _last_read_download_time) < _PORTFOLIO_CACHE_TTL:
        return db_path

    _download_portfolio(db_path)
    _last_read_download_time = now
    return db_path


def get_portfolio_connection() -> sqlite3.Connection:
    """読み取り専用 portfolio.db 接続を返す (FastAPI Depends 用)。"""
    db_path = ensure_portfolio_db()
    uri = f"file:{db_path}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


# ──────────────────────────────────────────────
# 書き込み用接続 (コンテキストマネージャ)
# ──────────────────────────────────────────────

@contextmanager
def writable_portfolio_connection() -> Generator[sqlite3.Connection, None, None]:
    """
    書き込み可能な portfolio.db 接続を提供するコンテキストマネージャ。

    - S3 から最新 portfolio.db をダウンロード
    - yield でコネクションを渡す
    - 正常終了時: commit → S3 アップロード → キャッシュ TTL をリセット
    - 例外時: rollback (S3 アップロードはスキップ)
    """
    global _last_read_download_time

    db_path = get_portfolio_db_path()
    _download_portfolio(db_path)

    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
        _upload_portfolio(db_path)
        _last_read_download_time = 0.0  # キャッシュを無効化して次回読み取り時に再ダウンロード
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
