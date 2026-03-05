"""共通ヘルパー関数 — API routers で繰り返し使うパターンを集約。"""
import json
import logging
from sqlite3 import Connection

from fastapi import HTTPException

logger = logging.getLogger(__name__)


def require_stock(conn: Connection, code: str) -> dict:
    """銘柄の存在を確認し、見つからなければ HTTPException(404) を送出する。

    Returns:
        sqlite3.Row を dict 化した銘柄情報 (code, name, sector)。
    """
    stock = conn.execute(
        "SELECT code, name, sector FROM stocks WHERE code = ?", (code,)
    ).fetchone()
    if not stock:
        raise HTTPException(status_code=404, detail=f"銘柄 {code} が見つかりません")
    return dict(stock)


def safe_json_loads(raw: str | None, *, default=None):
    """JSON 文字列を安全にパースする。失敗時は default を返す。"""
    if raw is None:
        return default
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        logger.debug("JSON パース失敗: %.80s", raw)
        return default


def period_sql_expr(granularity: str) -> str:
    """week/month の粒度に応じた SQLite strftime 式を返す。

    不正な granularity の場合は HTTPException(400) を送出する。
    """
    if granularity == "week":
        return "strftime('%Y-W%W', date)"
    if granularity == "month":
        return "strftime('%Y-%m', date)"
    raise HTTPException(
        status_code=400,
        detail=f"granularity は week または month のいずれかです (got: {granularity})",
    )
