"""GET /api/overview-snapshot — 概要ページ事前計算スナップショット"""
import json
from sqlite3 import Connection

from fastapi import APIRouter, Depends, HTTPException

from src.api.storage import get_connection

router = APIRouter()


@router.get("/overview-snapshot")
def get_overview_snapshot(conn: Connection = Depends(get_connection)):
    """
    バッチで事前計算した概要ページ用スナップショットを返す。

    含まれるデータ:
      - summary        : 最新日次サマリ (上昇/下落上位, レジームなど)
      - summary_history: 30日分の履歴 (チャート用)
      - news           : 最新 5 件のニュース
      - fear_indices   : VIX / BTC Fear & Greed
      - ytd_highs      : 年初来高値圏 銘柄
      - sector_performance: 日本・米国 全期間 (1d/1w/1m/3m)
      - nikkei_ohlcv   : 日経平均 OHLCV 60日分

    Returns:
        スナップショット dict, またはスナップショット未生成時は 404
    """
    row = conn.execute(
        "SELECT snapshot_json FROM overview_snapshot ORDER BY date DESC LIMIT 1"
    ).fetchone()

    if not row or not row[0]:
        raise HTTPException(
            status_code=404,
            detail="スナップショットが未生成です。バッチ処理の完了後に再度お試しください。",
        )

    return json.loads(row[0])
