"""SQLite の既存データから raw JSON ファイルを S3 にバックフィルする。

使い方:
    python scripts/backfill_raw.py --db-path /tmp/stocks.db
    python scripts/backfill_raw.py --db-path /tmp/stocks.db --source jquants/daily_prices
    python scripts/backfill_raw.py --db-path /tmp/stocks.db --dry-run
    python scripts/backfill_raw.py --db-path /tmp/stocks.db --limit 5
"""
import argparse
import logging
import sqlite3
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.pipeline.raw_store import save_raw

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# ソース別の設定: (category, subcategory, source, data_type, table, date_column, columns)
SOURCES = {
    "jquants/daily_prices": {
        "category": "market",
        "subcategory": "equity",
        "source": "jquants",
        "data_type": "daily_prices",
        "table": "daily_prices",
        "date_column": "date",
        "columns": ["code", "date", "open", "high", "low", "close", "volume"],
    },
    "yahoo_finance/us_indices": {
        "category": "market",
        "subcategory": "index",
        "source": "yahoo_finance",
        "data_type": "us_indices",
        "table": "us_indices",
        "date_column": "date",
        "columns": ["date", "ticker", "name", "open", "high", "low", "close", "volume"],
    },
    "yahoo_finance/exchange_rates": {
        "category": "market",
        "subcategory": "fx",
        "source": "yahoo_finance",
        "data_type": "exchange_rates",
        "table": "exchange_rates",
        "date_column": "date",
        "columns": ["date", "pair", "open", "high", "low", "close"],
    },
    "yahoo_finance/nikkei": {
        "category": "market",
        "subcategory": "index",
        "source": "yahoo_finance",
        "data_type": "nikkei",
        "table": "us_indices",
        "date_column": "date",
        "columns": ["date", "ticker", "name", "open", "high", "low", "close", "volume"],
        "filter": "ticker = '^N225'",
    },
    "jquants_margin/margin_balance": {
        "category": "market",
        "subcategory": "credit",
        "source": "jquants_margin",
        "data_type": "margin_balance",
        "table": "margin_balances",
        "date_column": "week_date",
        "columns": ["code", "week_date", "margin_buy", "margin_sell", "margin_ratio"],
    },
}


def _get_dates(conn: sqlite3.Connection, config: dict) -> list[str]:
    """テーブルからユニークな日付リストを取得する。"""
    table = config["table"]
    date_col = config["date_column"]
    where = f"WHERE {config['filter']}" if "filter" in config else ""
    query = f"SELECT DISTINCT {date_col} FROM {table} {where} ORDER BY {date_col}"
    return [row[0] for row in conn.execute(query).fetchall()]


def _get_records(conn: sqlite3.Connection, config: dict, date_str: str) -> list[dict]:
    """指定日のレコードをdictのリストとして取得する。"""
    table = config["table"]
    date_col = config["date_column"]
    columns = config["columns"]
    col_str = ", ".join(columns)
    where = f"{date_col} = ?"
    if "filter" in config:
        where += f" AND {config['filter']}"
    query = f"SELECT {col_str} FROM {table} WHERE {where}"
    rows = conn.execute(query, (date_str,)).fetchall()
    return [dict(zip(columns, row)) for row in rows]


def backfill(
    db_path: str,
    source_filter: str | None = None,
    dry_run: bool = False,
    limit: int | None = None,
) -> dict[str, int]:
    """SQLite からデータを読み出して raw JSON として S3 に保存する。

    Returns:
        {source_key: saved_count} の辞書
    """
    conn = sqlite3.connect(db_path)
    results: dict[str, int] = {}

    sources = SOURCES
    if source_filter:
        if source_filter not in SOURCES:
            logger.error(f"不明なソース: {source_filter}")
            logger.info(f"利用可能なソース: {', '.join(SOURCES.keys())}")
            return results
        sources = {source_filter: SOURCES[source_filter]}

    for source_key, config in sources.items():
        logger.info(f"=== {source_key} ===")
        dates = _get_dates(conn, config)
        logger.info(f"  SQLite に {len(dates)} 日分のデータ")

        if limit:
            dates = dates[:limit]

        saved = 0
        for date_str in dates:
            if dry_run:
                logger.info(f"  [DRY-RUN] {date_str}")
                saved += 1
                continue

            records = _get_records(conn, config, date_str)
            if not records:
                continue

            key = save_raw(
                config["category"],
                config["subcategory"],
                config["source"],
                config["data_type"],
                date_str,
                records,
                reconstructed=True,
            )
            if key:
                saved += 1

        results[source_key] = saved
        logger.info(f"  {source_key}: {saved} 日分{'(dry-run)' if dry_run else '保存完了'}")

    conn.close()
    return results


def main():
    parser = argparse.ArgumentParser(description="SQLite → raw S3 バックフィル")
    parser.add_argument("--db-path", required=True, help="SQLite ファイルパス")
    parser.add_argument("--source", default=None, help="対象ソース (例: jquants/daily_prices)")
    parser.add_argument("--dry-run", action="store_true", help="実際には保存しない")
    parser.add_argument("--limit", type=int, default=None, help="各ソースの最大日数")
    args = parser.parse_args()

    results = backfill(args.db_path, args.source, args.dry_run, args.limit)

    total = sum(results.values())
    logger.info(f"\n合計: {total} 日分")
    for k, v in results.items():
        logger.info(f"  {k}: {v}")


if __name__ == "__main__":
    main()
