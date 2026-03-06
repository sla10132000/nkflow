"""GET/POST/DELETE /api/properties — 物件 CRUD"""
import sqlite3
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from lib.hazard.geocoding import geocode_address
from src.api.storage import get_connection, writable_connection

router = APIRouter()


class PropertyCreate(BaseModel):
    address: str = Field(..., min_length=1, description="住所")
    property_name: Optional[str] = Field(None, description="物件名")
    notes: Optional[str] = Field(None, description="メモ")
    company_id: Optional[str] = Field(None, description="会社ID")
    created_by: Optional[str] = Field(None, description="作成者プロファイルID")
    # 緯度経度は住所から自動取得するが、手動上書きも可能
    latitude: Optional[float] = Field(None, description="緯度 (省略時は住所から自動取得)")
    longitude: Optional[float] = Field(None, description="経度 (省略時は住所から自動取得)")


@router.get("/properties")
def list_properties(
    company_id: Optional[str] = None,
    limit: int = Query(default=50, ge=1, le=200),
    conn: sqlite3.Connection = Depends(get_connection),
):
    """物件一覧を返す。company_id でフィルタ可能。"""
    query = """
        SELECT id, company_id, created_by, address, latitude, longitude,
               property_name, notes, created_at
        FROM properties
        WHERE 1=1
    """
    params: list = []

    if company_id:
        query += " AND company_id = ?"
        params.append(company_id)

    query += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)

    rows = conn.execute(query, params).fetchall()
    return [dict(row) for row in rows]


@router.get("/properties/{property_id}")
def get_property(property_id: str, conn: sqlite3.Connection = Depends(get_connection)):
    """物件詳細を返す。"""
    row = conn.execute(
        """
        SELECT id, company_id, created_by, address, latitude, longitude,
               property_name, notes, created_at
        FROM properties WHERE id = ?
        """,
        (property_id,),
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail=f"property not found: {property_id}")
    return dict(row)


@router.post("/properties", status_code=201)
async def create_property(body: PropertyCreate):
    """
    物件を登録する。

    緯度経度が省略された場合は国土地理院ジオコーダー API で自動取得する。
    ジオコーディング失敗時は lat/lon = NULL のまま登録する。
    """
    lat = body.latitude
    lon = body.longitude
    geocoded_address = body.address

    # 緯度経度が未指定の場合はジオコーディング
    if lat is None or lon is None:
        geo = await geocode_address(body.address)
        if geo:
            lat = geo["latitude"]
            lon = geo["longitude"]
            geocoded_address = geo.get("display_name", body.address)

    with writable_connection() as conn:
        conn.execute(
            """
            INSERT INTO properties
                (address, latitude, longitude, property_name, notes, company_id, created_by)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (geocoded_address, lat, lon, body.property_name, body.notes,
             body.company_id, body.created_by),
        )
        row = conn.execute(
            """
            SELECT id, company_id, created_by, address, latitude, longitude,
                   property_name, notes, created_at
            FROM properties WHERE rowid = last_insert_rowid()
            """
        ).fetchone()

    return dict(row)


@router.delete("/properties/{property_id}", status_code=200)
def delete_property(property_id: str):
    """物件を削除する (関連するハザードレポートも削除)。"""
    with writable_connection() as conn:
        # ハザードレポートも削除
        conn.execute(
            "DELETE FROM hazard_reports WHERE property_id = ?", (property_id,)
        )
        result = conn.execute(
            "DELETE FROM properties WHERE id = ?", (property_id,)
        )
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail=f"property not found: {property_id}")

    return {"property_id": property_id, "status": "deleted"}
