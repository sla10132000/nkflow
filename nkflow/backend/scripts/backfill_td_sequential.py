"""
TD Sequential バックフィルスクリプト (Phase 22)

全銘柄・全日付の TD Sequential を計算して td_sequential テーブルに保存する。
初回デプロイ時やスキーマ変更後に実行する。

実行前に migrate_phase22_td_sequential.py でテーブルを作成しておくこと。

実行方法:
    # S3 から DB をダウンロード
    make pull

    # バックフィル実行
    cd backend
    .venv/bin/python scripts/backfill_td_sequential.py

    # S3 にアップロード
    make push-db
"""
import logging
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


if __name__ == "__main__":
    from src.batch.td_sequential import backfill_td_sequential
    from src.config import SQLITE_PATH

    db_path = os.environ.get("SQLITE_PATH", SQLITE_PATH)
    logger.info(f"バックフィル開始: {db_path}")

    total = backfill_td_sequential(db_path)
    logger.info(f"バックフィル完了: {total} 件")
