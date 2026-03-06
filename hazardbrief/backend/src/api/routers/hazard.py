"""GET /api/hazard/{property_id} — ハザードデータ取得"""
import json
import logging
import sqlite3
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException

from lib.hazard import fetch_all_hazards
from src.api.storage import get_connection, writable_connection
from src.config import HAZARD_CACHE_TTL_SECONDS

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/hazard/{property_id}")
async def get_hazard(
    property_id: str,
    force_refresh: bool = False,
    conn: sqlite3.Connection = Depends(get_connection),
):
    """
    物件のハザードデータを取得する。

    キャッシュ (hazard_reports テーブル) が有効な場合はそれを返す。
    キャッシュが期限切れまたは存在しない場合は外部 API から再取得してキャッシュする。

    Args:
        property_id: 物件ID
        force_refresh: True の場合はキャッシュを無視して再取得
    """
    # 物件の存在確認と緯度経度取得
    prop = conn.execute(
        "SELECT id, address, latitude, longitude FROM properties WHERE id = ?",
        (property_id,),
    ).fetchone()

    if not prop:
        raise HTTPException(status_code=404, detail=f"property not found: {property_id}")

    lat = prop["latitude"]
    lon = prop["longitude"]

    if lat is None or lon is None:
        raise HTTPException(
            status_code=422,
            detail="この物件には緯度経度が設定されていません。先に住所を確認してください。",
        )

    # キャッシュ確認
    if not force_refresh:
        cached = conn.execute(
            """
            SELECT flood_risk, landslide_risk, tsunami_risk, ground_risk, risk_summary,
                   fetched_at, expires_at
            FROM hazard_reports
            WHERE property_id = ?
            ORDER BY fetched_at DESC
            LIMIT 1
            """,
            (property_id,),
        ).fetchone()

        if cached:
            expires_at = cached["expires_at"]
            if expires_at and datetime.fromisoformat(expires_at) > datetime.utcnow():
                logger.info(f"ハザードキャッシュヒット: {property_id}")
                return {
                    "property_id": property_id,
                    "flood_risk": json.loads(cached["flood_risk"] or "{}"),
                    "landslide_risk": json.loads(cached["landslide_risk"] or "{}"),
                    "tsunami_risk": json.loads(cached["tsunami_risk"] or "{}"),
                    "ground_risk": json.loads(cached["ground_risk"] or "{}"),
                    "risk_summary": json.loads(cached["risk_summary"] or "{}"),
                    "fetched_at": cached["fetched_at"],
                    "from_cache": True,
                }

    # 外部 API から取得
    logger.info(f"ハザードデータ取得開始: property_id={property_id}, lat={lat}, lon={lon}")
    hazard_data = await fetch_all_hazards(float(lat), float(lon))

    # キャッシュに保存
    expires_at = (datetime.utcnow() + timedelta(seconds=HAZARD_CACHE_TTL_SECONDS)).isoformat()
    fetched_at = datetime.utcnow().isoformat()

    with writable_connection() as wconn:
        wconn.execute(
            """
            INSERT INTO hazard_reports
                (property_id, flood_risk, landslide_risk, tsunami_risk, ground_risk,
                 risk_summary, fetched_at, expires_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                property_id,
                json.dumps(hazard_data["flood_risk"], ensure_ascii=False),
                json.dumps(hazard_data["landslide_risk"], ensure_ascii=False),
                json.dumps(hazard_data["tsunami_risk"], ensure_ascii=False),
                json.dumps(hazard_data["ground_risk"], ensure_ascii=False),
                json.dumps(hazard_data["risk_summary"], ensure_ascii=False),
                fetched_at,
                expires_at,
            ),
        )

    return {
        "property_id": property_id,
        **hazard_data,
        "fetched_at": fetched_at,
        "from_cache": False,
    }
