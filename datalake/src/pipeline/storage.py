"""永続化モジュール: S3 ダウンロード/アップロード + SSM クレデンシャル取得"""
import logging
import os
import sqlite3
import tarfile

import boto3
from botocore.exceptions import ClientError

from src.config import JQUANTS_API_KEY, KUZU_PATH, S3_BUCKET, S3_KUZU_KEY, S3_SQLITE_KEY, SQLITE_PATH

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# クレデンシャル取得
# ─────────────────────────────────────────────────────────────────────────────

def get_api_key() -> str:
    """
    SSM Parameter Store から J-Quants API キーを取得する。

    環境変数 JQUANTS_API_KEY が設定済みの場合は SSM をスキップ。

    Returns:
        API キー文字列
    """
    if JQUANTS_API_KEY:
        logger.info("J-Quants API キーを環境変数から取得しました")
        return JQUANTS_API_KEY

    logger.info("SSM Parameter Store から J-Quants API キーを取得中...")
    ssm = boto3.client("ssm")

    try:
        api_key = ssm.get_parameter(
            Name="/nkflow/jquants-api-key", WithDecryption=True
        )["Parameter"]["Value"]
    except ClientError as e:
        raise RuntimeError(f"SSM API キー取得失敗: {e}") from e

    os.environ["JQUANTS_API_KEY"] = api_key
    logger.info("SSM から J-Quants API キーを取得しました")
    return api_key


# ─────────────────────────────────────────────────────────────────────────────
# ダウンロード (S3 → /tmp)
# ─────────────────────────────────────────────────────────────────────────────

def download(
    sqlite_path: str = SQLITE_PATH,
    kuzu_path: str = KUZU_PATH,
) -> None:
    """
    Lambda 起動時に S3 から SQLite と KùzuDB を /tmp に復元する。

    - SQLite: S3 から直接ダウンロード。初回は存在しないためスキーマ初期化。
    - KùzuDB: S3 から tar.gz をダウンロードして展開。初回は空ディレクトリ。

    Args:
        sqlite_path: 復元先の SQLite ファイルパス
        kuzu_path: 復元先の KùzuDB ディレクトリパス
    """
    _download_sqlite(sqlite_path)
    _download_kuzu(kuzu_path)


def _download_sqlite(sqlite_path: str) -> None:
    """S3 から SQLite をダウンロードする。初回はスキーマ初期化。既存DBはマイグレーション適用。"""
    os.makedirs(os.path.dirname(sqlite_path) or ".", exist_ok=True)

    s3 = boto3.client("s3")
    try:
        s3.download_file(S3_BUCKET, S3_SQLITE_KEY, sqlite_path)
        logger.info(f"SQLite を S3 から復元しました: {sqlite_path}")
        # WAL モードを有効化
        conn = sqlite3.connect(sqlite_path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.close()
    except ClientError as e:
        if e.response["Error"]["Code"] in ("NoSuchKey", "404"):
            logger.warning("SQLite が S3 に存在しません (初回実行) — スキーマを初期化します")
        else:
            raise

    # CREATE TABLE IF NOT EXISTS のため冪等 — 新 Phase のテーブルを常に適用
    _init_sqlite_schema(sqlite_path)


def _init_sqlite_schema(sqlite_path: str) -> None:
    """スキーマ初期化スクリプトを呼び出す"""
    try:
        from scripts.init_sqlite import init_sqlite
        init_sqlite(sqlite_path)
        logger.info(f"SQLite スキーマを初期化しました: {sqlite_path}")
    except Exception as e:
        logger.error(f"SQLite スキーマ初期化失敗: {e}")
        raise


def _download_kuzu(kuzu_path: str) -> None:
    """S3 から KùzuDB tar.gz をダウンロードして展開する。初回はスキップ。"""
    import shutil

    tar_path = kuzu_path + ".tar.gz"
    parent_dir = os.path.dirname(kuzu_path) or "."

    s3 = boto3.client("s3")
    try:
        s3.download_file(S3_BUCKET, S3_KUZU_KEY, tar_path)
        logger.info("KùzuDB tar.gz を S3 からダウンロードしました")
    except ClientError as e:
        if e.response["Error"]["Code"] in ("NoSuchKey", "404"):
            logger.warning("KùzuDB が S3 に存在しません (初回実行) — 新規作成されます")
            if os.path.exists(kuzu_path):
                shutil.rmtree(kuzu_path)
            return
        else:
            raise

    # 既存ディレクトリを削除してから展開 (KùzuDB の制約: 既存ディレクトリ不可)
    if os.path.exists(kuzu_path):
        shutil.rmtree(kuzu_path)

    with tarfile.open(tar_path, "r:gz") as tar:
        tar.extractall(path=parent_dir)

    logger.info(f"KùzuDB を展開しました: {kuzu_path}")


# ─────────────────────────────────────────────────────────────────────────────
# アップロード (/tmp → S3)
# ─────────────────────────────────────────────────────────────────────────────

def upload(
    sqlite_path: str = SQLITE_PATH,
    kuzu_path: str = KUZU_PATH,
) -> None:
    """
    バッチ終了時に /tmp の SQLite と KùzuDB を S3 にアップロードする。

    1. SQLite: VACUUM でサイズ最小化してから S3 にアップロード
    2. KùzuDB: tar.gz に圧縮して S3 にアップロード

    Args:
        sqlite_path: SQLite ファイルパス
        kuzu_path: KùzuDB ディレクトリパス
    """
    _upload_sqlite(sqlite_path)
    _upload_kuzu(kuzu_path)


def _upload_sqlite(sqlite_path: str) -> None:
    """SQLite を VACUUM してから S3 にアップロードする。"""
    if not os.path.exists(sqlite_path):
        logger.warning(f"SQLite が存在しないためアップロードをスキップ: {sqlite_path}")
        return

    # WAL チェックポイントを実行 (VACUUM は /tmp disk full を引き起こすため省略)
    conn = sqlite3.connect(sqlite_path)
    try:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        conn.commit()
    finally:
        conn.close()

    s3 = boto3.client("s3")
    s3.upload_file(sqlite_path, S3_BUCKET, S3_SQLITE_KEY)
    logger.info(f"SQLite を S3 にアップロードしました: s3://{S3_BUCKET}/{S3_SQLITE_KEY}")


def _upload_kuzu(kuzu_path: str) -> None:
    """KùzuDB ディレクトリを tar.gz に圧縮して S3 にアップロードする。"""
    if not os.path.exists(kuzu_path):
        logger.warning(f"KùzuDB パスが存在しないためアップロードをスキップ: {kuzu_path}")
        return

    tar_path = kuzu_path + ".tar.gz"

    logger.info(f"KùzuDB を圧縮中: {tar_path}")
    with tarfile.open(tar_path, "w:gz") as tar:
        tar.add(kuzu_path, arcname=os.path.basename(kuzu_path))

    s3 = boto3.client("s3")
    s3.upload_file(tar_path, S3_BUCKET, S3_KUZU_KEY)
    logger.info(f"KùzuDB を S3 にアップロードしました: s3://{S3_BUCKET}/{S3_KUZU_KEY}")
