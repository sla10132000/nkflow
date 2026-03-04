"""
バッチ Lambda のエントリポイント。
EventBridge Scheduler から呼び出される。

実行順序:
  0. fetch_news.normalize_news() - S3 raw ニュース → SQLite 正規化 (Phase 18)
  1. storage.get_credentials()   - SSM から J-Quants クレデンシャル取得
  2. storage.download()          - S3 から SQLite / KùzuDB を復元
  3. fetch.fetch_daily()         - J-Quants から当日 OHLCV を取得
  4. compute.compute_all()       - DuckDB 計算 (騰落率・相関)
  5. statistics.run_all()        - 統計分析 (グレンジャー・リードラグ・資金フロー)
  6. graph.update_and_query()    - KùzuDB グラフ更新・探索
  7. storage.upload()            - S3 へ永続化 (必ず実行)

エラーハンドリング:
  - 各ステップを try/except で囲む
  - 失敗しても upload() は finally で必ず実行
  - 取引日でない場合は fetch で早期リターン
  - CloudWatch Logs に自動出力
"""
import logging
import os
import sqlite3
import sys
from datetime import date, datetime, timedelta, timezone
from typing import Any

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


def handler(event: dict, context: Any) -> dict:
    """
    Lambda ハンドラ。EventBridge Scheduler から呼び出される。

    Returns:
        Lambda レスポンス dict
    """
    from src.config import JQUANTS_PLAN, KUZU_PATH, SQLITE_PATH
    from src.batch import compute, fetch, fetch_external, fetch_news, graph, notifier, sector_rotation, statistics, storage

    # 処理対象日の決定
    target_date: str | None = event.get("target_date") or os.environ.get("TARGET_DATE")

    if target_date is None:
        jst = timezone(timedelta(hours=9))
        target_date = datetime.now(jst).date().isoformat()
        # free プランは 12週遅延のため処理日を自動調整し、土日は直前の金曜に戻す
        if JQUANTS_PLAN == "free":
            adjusted = date.fromisoformat(target_date) - timedelta(weeks=12)
            while adjusted.weekday() >= 5:  # 5=土, 6=日
                adjusted -= timedelta(days=1)
            logger.info(f"freeプラン: 12週遅延のため処理日を {target_date} → {adjusted} に調整")
            target_date = adjusted.isoformat()

    logger.info(f"{'=' * 60}")
    logger.info(f"バッチ処理開始: {target_date}")
    logger.info(f"{'=' * 60}")

    errors: list[str] = []
    stocks_updated = 0

    # ── 1. SSM から API キー取得 ──────────────────────────────────
    try:
        storage.get_api_key()
    except Exception as e:
        logger.error(f"[FATAL] get_api_key 失敗: {e}")
        return {"statusCode": 500, "body": {"error": str(e)}}

    # ── 2. S3 から復元 ────────────────────────────────────────────
    try:
        storage.download(SQLITE_PATH, KUZU_PATH)
    except Exception as e:
        logger.error(f"[FATAL] download 失敗: {e}")
        return {"statusCode": 500, "body": {"error": str(e)}}

    conn = sqlite3.connect(SQLITE_PATH)

    try:
        # ── 0. ニュース正規化 (Phase 18, 非ブロッキング) ──────────
        try:
            news_count = fetch_news.normalize_news(conn, target_date)
            logger.info(f"fetch_news.normalize_news: {news_count} 件")
        except Exception as e:
            logger.error(f"fetch_news.normalize_news 失敗 (処理は継続): {e}")
            errors.append(f"fetch_news: {e}")

        # ── 3. データ取得 ─────────────────────────────────────────
        try:
            stocks_updated = fetch.fetch_daily(conn, target_date)
        except Exception as e:
            logger.error(f"fetch_daily 失敗: {e}")
            errors.append(f"fetch: {e}")
            return {
                "statusCode": 500,
                "body": {"date": target_date, "stocks_updated": 0,
                         "signals_generated": 0, "errors": errors},
            }

        if stocks_updated == 0:
            logger.info(f"{target_date} は取引日ではありません — 処理をスキップします")
            return {
                "statusCode": 200,
                "body": {"date": target_date, "stocks_updated": 0, "errors": []},
            }

        logger.info(f"fetch_daily: {stocks_updated} 件取得")

        # ── 3.5. 外部データ取得 (Phase 13) ───────────────────────
        try:
            fx_rows = fetch_external.fetch_exchange_rates(conn, target_date)
            logger.info(f"fetch_exchange_rates: {fx_rows} 行")
        except Exception as e:
            logger.error(f"fetch_exchange_rates 失敗 (処理は継続): {e}")
            errors.append(f"fetch_exchange_rates: {e}")

        try:
            fetch_external.fetch_nikkei_close(conn, target_date)
        except Exception as e:
            logger.error(f"fetch_nikkei_close 失敗 (処理は継続): {e}")
            errors.append(f"fetch_nikkei_close: {e}")

        try:
            margin_rows = fetch_external.fetch_margin_balance(conn, target_date)
            logger.info(f"fetch_margin_balance: {margin_rows} 行")
        except Exception as e:
            logger.error(f"fetch_margin_balance 失敗 (処理は継続): {e}")
            errors.append(f"fetch_margin_balance: {e}")

        # ── 3.6. 米国株指数・VIX取得 (Phase 20/21) ───────────────
        try:
            us_result = fetch_external.fetch_us_indices(SQLITE_PATH)
            logger.info(f"fetch_us_indices: {us_result}")
        except Exception as e:
            logger.error(f"fetch_us_indices 失敗 (処理は継続): {e}")
            errors.append(f"fetch_us_indices: {e}")

        # ── 3.7. BTC Fear & Greed 取得 (Phase 21) ────────────────
        try:
            fng_rows = fetch_external.fetch_crypto_fear_greed(SQLITE_PATH)
            logger.info(f"fetch_crypto_fear_greed: {fng_rows} 行")
        except Exception as e:
            logger.error(f"fetch_crypto_fear_greed 失敗 (処理は継続): {e}")
            errors.append(f"fetch_crypto_fear_greed: {e}")

        # ── 4. DuckDB 計算 ────────────────────────────────────────
        try:
            compute.compute_all(SQLITE_PATH, target_date)
        except Exception as e:
            logger.error(f"compute_all 失敗 (処理は継続): {e}")
            errors.append(f"compute: {e}")

        # ── 5. 統計分析 ───────────────────────────────────────────
        try:
            statistics.run_all(SQLITE_PATH, target_date)
        except Exception as e:
            logger.error(f"run_all 失敗 (処理は継続): {e}")
            errors.append(f"statistics: {e}")

        # ── 6. グラフ更新・探索 ───────────────────────────────────
        graph_results: dict = {}
        try:
            graph_results = graph.update_and_query(KUZU_PATH, SQLITE_PATH, target_date)
        except Exception as e:
            logger.error(f"update_and_query 失敗 (処理は継続): {e}")
            errors.append(f"graph: {e}")

        # ── 7. セクターローテーション分析 (Phase 17) ─────────────
        try:
            sector_rotation.run_all(SQLITE_PATH, target_date)
        except Exception as e:
            logger.error(f"sector_rotation.run_all 失敗 (処理は継続): {e}")
            errors.append(f"sector_rotation: {e}")

    finally:
        conn.close()

        # ── 8. S3 へ永続化 (必ず実行) ────────────────────────────
        try:
            storage.upload(SQLITE_PATH, KUZU_PATH)
        except Exception as e:
            logger.error(f"upload 失敗: {e}")
            errors.append(f"upload: {e}")

        # ── 9. SNS に日次レポートを通知 (Phase 12) ───────────────
        try:
            notifier.publish(
                SQLITE_PATH,
                target_date,
                {
                    "stocks_updated": stocks_updated,
                    "errors": errors,
                },
            )
        except Exception as e:
            logger.error(f"notifier.publish 失敗 (処理は継続): {e}")
            errors.append(f"notifier: {e}")

    logger.info(f"{'=' * 60}")
    logger.info(f"バッチ処理完了: {target_date}")
    logger.info(f"{'=' * 60}")

    status_code = 200 if not errors else 207
    return {
        "statusCode": status_code,
        "body": {
            "date": target_date,
            "stocks_updated": stocks_updated,
            "errors": errors,
        },
    }
