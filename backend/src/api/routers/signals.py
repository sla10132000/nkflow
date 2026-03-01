"""GET /api/signals"""
import json
from typing import Optional
from sqlite3 import Connection

from fastapi import APIRouter, Depends

from src.api.storage import get_connection

router = APIRouter()


@router.get("/signals")
def get_signals(
    date: Optional[str] = None,
    type: Optional[str] = None,
    direction: Optional[str] = None,
    min_confidence: Optional[float] = None,
    conn: Connection = Depends(get_connection),
):
    """シグナル一覧を返す。各フィールドでフィルタ可能。"""
    query = """
        SELECT id, date, signal_type, code, sector, direction, confidence, reasoning
        FROM signals
        WHERE 1=1
    """
    params: list = []

    if date:
        query += " AND date = ?"
        params.append(date)
    if type:
        query += " AND signal_type = ?"
        params.append(type)
    if direction:
        query += " AND direction = ?"
        params.append(direction)
    if min_confidence is not None:
        query += " AND confidence >= ?"
        params.append(min_confidence)

    query += " ORDER BY date DESC, confidence DESC LIMIT 200"

    rows = conn.execute(query, params).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        if item["reasoning"]:
            try:
                item["reasoning"] = json.loads(item["reasoning"])
            except (json.JSONDecodeError, TypeError):
                pass
        result.append(item)

    return result
