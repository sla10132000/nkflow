"""
dispatcher — raw envelope を適切な SQLite writer にルーティングする。

各 writer は @register デコレータで (category, source, data_type) に紐付けて登録する。
対応する writer が未登録の場合は skip (警告ログのみ)。
"""
import logging
import sqlite3
from typing import Any, Callable

logger = logging.getLogger(__name__)

# (category, source, data_type) → writer 関数
_REGISTRY: dict[tuple[str, str, str], Callable] = {}


def register(category: str, source: str, data_type: str) -> Callable:
    """writer 関数を登録するデコレータ。

    Example:
        @register("market", "jquants", "daily_prices")
        def _write_daily_prices(conn, date_str, data):
            ...
    """
    def decorator(fn: Callable) -> Callable:
        key = (category, source, data_type)
        _REGISTRY[key] = fn
        logger.debug(f"writer 登録: {key} -> {fn.__name__}")
        return fn
    return decorator


def dispatch(
    conn: sqlite3.Connection,
    category: str,
    source: str,
    data_type: str,
    date_str: str,
    data: Any,
) -> int:
    """登録済み writer があれば実行し、書き込んだ行数を返す。

    対応する writer が未登録の場合は 0 を返す (エラーにはしない)。
    """
    key = (category, source, data_type)
    writer = _REGISTRY.get(key)

    if writer is None:
        logger.info(f"writer 未登録のためスキップ: {key}")
        return 0

    rows = writer(conn, date_str, data)
    logger.info(f"writer 完了: {key} → {rows} 行")
    return rows
