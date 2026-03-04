"""GET /api/fear-indices — 恐怖指数 (Phase 21)"""
from sqlite3 import Connection
from typing import Optional

from fastapi import APIRouter, Depends

from src.api.storage import get_connection

router = APIRouter()


@router.get("/fear-indices/latest")
def get_fear_indices_latest(conn: Connection = Depends(get_connection)):
    """
    最新の恐怖指数を返す。

    Returns:
        {
            "vix": { "value": 21.58, "change_pct": -1.2, "date": "2026-03-04" } | null,
            "btc_fear_greed": { "value": 45, "classification": "Fear", "date": "2026-03-04" } | null,
        }
    """
    # VIX: us_indices テーブルから最新2件取得し変化率を計算
    vix: Optional[dict] = None
    try:
        vix_rows = conn.execute(
            """
            SELECT date, close
            FROM us_indices
            WHERE ticker = '^VIX'
            ORDER BY date DESC
            LIMIT 2
            """
        ).fetchall()
        if vix_rows:
            latest = dict(vix_rows[0])
            if len(vix_rows) >= 2:
                prev_close = vix_rows[1]["close"]
                change_pct = round((latest["close"] - prev_close) / prev_close * 100, 4) if prev_close else None
            else:
                change_pct = None
            vix = {
                "value": round(latest["close"], 2),
                "change_pct": change_pct,
                "date": latest["date"],
            }
    except Exception:
        pass  # テーブル未作成時は null を返す

    # BTC Fear & Greed: crypto_fear_greed テーブルから最新を取得
    # テーブルが存在しない場合 (マイグレーション未実行) は None を返す
    btc_fear_greed: Optional[dict] = None
    try:
        fng_row = conn.execute(
            """
            SELECT date, value, value_classification
            FROM crypto_fear_greed
            ORDER BY date DESC
            LIMIT 1
            """
        ).fetchone()
        if fng_row:
            btc_fear_greed = {
                "value": fng_row["value"],
                "classification": fng_row["value_classification"],
                "date": fng_row["date"],
            }
    except Exception:
        pass  # テーブル未作成時は null を返す

    return {
        "vix": vix,
        "btc_fear_greed": btc_fear_greed,
    }
