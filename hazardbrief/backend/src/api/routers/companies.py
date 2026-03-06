"""GET/POST /api/companies — 会社（テナント）管理"""
import sqlite3

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from src.api.storage import get_connection, writable_connection

router = APIRouter()


class CompanyCreate(BaseModel):
    name: str = Field(..., min_length=1, description="会社名")
    plan: str = Field("free", description="プラン (free/standard/enterprise)")


@router.get("/companies")
def list_companies(conn: sqlite3.Connection = Depends(get_connection)):
    """会社一覧を返す。"""
    rows = conn.execute(
        "SELECT id, name, plan, created_at FROM companies ORDER BY created_at DESC"
    ).fetchall()
    return [dict(row) for row in rows]


@router.get("/companies/{company_id}")
def get_company(company_id: str, conn: sqlite3.Connection = Depends(get_connection)):
    """指定会社の詳細を返す。"""
    row = conn.execute(
        "SELECT id, name, plan, created_at FROM companies WHERE id = ?",
        (company_id,),
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail=f"company not found: {company_id}")
    return dict(row)


@router.post("/companies", status_code=201)
def create_company(body: CompanyCreate):
    """会社を新規登録する。"""
    if body.plan not in ("free", "standard", "enterprise"):
        raise HTTPException(status_code=400, detail="plan must be free/standard/enterprise")

    with writable_connection() as conn:
        conn.execute(
            "INSERT INTO companies (name, plan) VALUES (?, ?)",
            (body.name, body.plan),
        )
        row = conn.execute(
            "SELECT id, name, plan, created_at FROM companies WHERE rowid = last_insert_rowid()"
        ).fetchone()

    return dict(row)
