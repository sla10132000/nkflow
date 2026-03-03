"""GET/POST/DELETE /api/portfolio/* — ポートフォリオ連携 (Phase 15)

エンドポイント一覧:
  GET    /api/portfolio/holdings               保有銘柄一覧 (現在価格・含み損益付き)
  POST   /api/portfolio/holdings               保有銘柄追加/更新
  DELETE /api/portfolio/holdings/{code}        保有銘柄削除
  GET    /api/portfolio/transactions           取引履歴
  POST   /api/portfolio/transactions           取引登録 (avg_cost/quantity を自動更新)
  GET    /api/portfolio/performance            評価額推移 (日次スナップショット)
  GET    /api/portfolio/signals                保有銘柄に関連するシグナル
"""
import json
import sqlite3
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from src.api.auth import require_auth
from src.api.portfolio_storage import get_portfolio_connection, writable_portfolio_connection
from src.api.storage import get_connection as get_stocks_connection

# ポートフォリオ全エンドポイントに認証を必須化
router = APIRouter(dependencies=[Depends(require_auth)])


# ─────────────────────────────────────────────
# Pydantic スキーマ
# ─────────────────────────────────────────────

class HoldingUpsert(BaseModel):
    code: str = Field(..., description="銘柄コード")
    quantity: float = Field(..., gt=0, description="保有株数")
    avg_cost: float = Field(..., gt=0, description="平均取得単価 (円)")
    entry_date: str = Field(..., description="初回取得日 (YYYY-MM-DD)")
    note: Optional[str] = Field(None, description="メモ")


class TransactionCreate(BaseModel):
    code: str = Field(..., description="銘柄コード")
    date: str = Field(..., description="取引日 (YYYY-MM-DD)")
    action: str = Field(..., pattern="^(buy|sell)$", description="'buy' または 'sell'")
    quantity: float = Field(..., gt=0, description="株数")
    price: float = Field(..., gt=0, description="取引単価 (円)")
    fee: float = Field(0.0, ge=0, description="手数料 (円)")
    note: Optional[str] = Field(None, description="メモ")


# ─────────────────────────────────────────────
# Holdings (保有銘柄)
# ─────────────────────────────────────────────

@router.get("/portfolio/holdings")
def list_holdings(
    portfolio_conn: sqlite3.Connection = Depends(get_portfolio_connection),
    stocks_conn: sqlite3.Connection = Depends(get_stocks_connection),
):
    """
    保有銘柄一覧を返す。stocks.db の直近終値を参照して現在評価額と含み損益を付与する。
    """
    holdings = portfolio_conn.execute(
        "SELECT code, quantity, avg_cost, entry_date, note, updated_at FROM portfolio_holdings"
    ).fetchall()

    if not holdings:
        return []

    codes = [h["code"] for h in holdings]
    placeholders = ",".join("?" * len(codes))

    # 各銘柄の直近終値を stocks.db から取得
    latest_prices: dict[str, float] = {}
    latest_names: dict[str, str] = {}
    latest_sectors: dict[str, str] = {}

    price_rows = stocks_conn.execute(
        f"""
        SELECT dp.code, dp.close, s.name, s.sector
        FROM daily_prices dp
        JOIN stocks s ON dp.code = s.code
        WHERE dp.code IN ({placeholders})
          AND dp.date = (
              SELECT MAX(date) FROM daily_prices dp2 WHERE dp2.code = dp.code
          )
        """,
        codes,
    ).fetchall()

    for row in price_rows:
        latest_prices[row["code"]] = row["close"]
        latest_names[row["code"]] = row["name"]
        latest_sectors[row["code"]] = row["sector"]

    result = []
    for h in holdings:
        code = h["code"]
        qty = h["quantity"]
        avg_cost = h["avg_cost"]
        current_price = latest_prices.get(code)

        item = {
            "code": code,
            "name": latest_names.get(code, ""),
            "sector": latest_sectors.get(code, ""),
            "quantity": qty,
            "avg_cost": avg_cost,
            "entry_date": h["entry_date"],
            "note": h["note"],
            "updated_at": h["updated_at"],
            "current_price": current_price,
            "valuation": round(current_price * qty, 2) if current_price else None,
            "cost_basis": round(avg_cost * qty, 2),
            "unrealized_pnl": round((current_price - avg_cost) * qty, 2) if current_price else None,
            "unrealized_pnl_pct": round((current_price / avg_cost - 1) * 100, 2) if current_price else None,
        }
        result.append(item)

    return result


@router.post("/portfolio/holdings", status_code=201)
def upsert_holding(body: HoldingUpsert):
    """
    保有銘柄を追加または更新する (UPSERT)。
    avg_cost / quantity / entry_date / note を上書きする。
    """
    with writable_portfolio_connection() as conn:
        conn.execute(
            """
            INSERT INTO portfolio_holdings (code, quantity, avg_cost, entry_date, note, updated_at)
            VALUES (?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(code) DO UPDATE SET
                quantity   = excluded.quantity,
                avg_cost   = excluded.avg_cost,
                entry_date = excluded.entry_date,
                note       = excluded.note,
                updated_at = datetime('now')
            """,
            (body.code, body.quantity, body.avg_cost, body.entry_date, body.note),
        )
    return {"code": body.code, "status": "upserted"}


@router.delete("/portfolio/holdings/{code}", status_code=200)
def delete_holding(code: str):
    """保有銘柄を削除する。"""
    with writable_portfolio_connection() as conn:
        result = conn.execute(
            "DELETE FROM portfolio_holdings WHERE code = ?", (code,)
        )
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail=f"holding not found: {code}")
    return {"code": code, "status": "deleted"}


# ─────────────────────────────────────────────
# Transactions (取引履歴)
# ─────────────────────────────────────────────

@router.get("/portfolio/transactions")
def list_transactions(
    code: Optional[str] = None,
    action: Optional[str] = None,
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    conn: sqlite3.Connection = Depends(get_portfolio_connection),
):
    """取引履歴を返す。code / action でフィルタ可能。"""
    query = "SELECT * FROM portfolio_transactions WHERE 1=1"
    params: list = []

    if code:
        query += " AND code = ?"
        params.append(code)
    if action:
        if action not in ("buy", "sell"):
            raise HTTPException(status_code=400, detail="action must be 'buy' or 'sell'")
        query += " AND action = ?"
        params.append(action)

    query += " ORDER BY date DESC, id DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    rows = conn.execute(query, params).fetchall()
    return [dict(row) for row in rows]


@router.post("/portfolio/transactions", status_code=201)
def add_transaction(body: TransactionCreate):
    """
    取引を登録し、portfolio_holdings の avg_cost と quantity を自動更新する。

    buy:
      - holdings が存在する場合: 加重平均で avg_cost を更新し quantity を加算
      - holdings が存在しない場合: 新規追加
    sell:
      - quantity を減算。0 以下になる場合は 400 エラー
      - quantity が 0 になる場合は holdings を削除
    """
    with writable_portfolio_connection() as conn:
        # 取引履歴に追記
        conn.execute(
            """
            INSERT INTO portfolio_transactions
                (code, date, action, quantity, price, fee, note)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (body.code, body.date, body.action, body.quantity, body.price, body.fee, body.note),
        )

        # holdings を更新
        holding = conn.execute(
            "SELECT quantity, avg_cost, entry_date FROM portfolio_holdings WHERE code = ?",
            (body.code,),
        ).fetchone()

        if body.action == "buy":
            if holding:
                old_qty = holding["quantity"]
                old_cost = holding["avg_cost"]
                new_qty = old_qty + body.quantity
                new_avg = (old_qty * old_cost + body.quantity * body.price) / new_qty
                conn.execute(
                    """
                    UPDATE portfolio_holdings
                    SET quantity = ?, avg_cost = ?, updated_at = datetime('now')
                    WHERE code = ?
                    """,
                    (new_qty, new_avg, body.code),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO portfolio_holdings
                        (code, quantity, avg_cost, entry_date, updated_at)
                    VALUES (?, ?, ?, ?, datetime('now'))
                    """,
                    (body.code, body.quantity, body.price, body.date),
                )

        else:  # sell
            if not holding:
                raise HTTPException(status_code=400, detail=f"holding not found: {body.code}")
            remaining = holding["quantity"] - body.quantity
            if remaining < 0:
                raise HTTPException(
                    status_code=400,
                    detail=f"売却数量が保有数量を超えています: 保有={holding['quantity']}, 売却={body.quantity}",
                )
            if remaining == 0:
                conn.execute("DELETE FROM portfolio_holdings WHERE code = ?", (body.code,))
            else:
                conn.execute(
                    """
                    UPDATE portfolio_holdings
                    SET quantity = ?, updated_at = datetime('now')
                    WHERE code = ?
                    """,
                    (remaining, body.code),
                )

    return {"status": "created", "code": body.code, "action": body.action}


# ─────────────────────────────────────────────
# Performance (評価額推移)
# ─────────────────────────────────────────────

@router.get("/portfolio/performance")
def get_performance(
    days: int = Query(default=90, ge=1, le=730),
    conn: sqlite3.Connection = Depends(get_portfolio_connection),
):
    """
    ポートフォリオの日次評価額推移を返す。

    portfolio_snapshots を使用。スナップショットは毎営業日のバッチ処理で更新される。
    日次で全保有銘柄の valuation を合計してポートフォリオ全体の時系列を構成する。
    """
    rows = conn.execute(
        """
        SELECT date,
               SUM(valuation)      AS total_valuation,
               SUM(cost_basis)     AS total_cost_basis,
               SUM(unrealized_pnl) AS total_unrealized_pnl
        FROM (
            SELECT date, code, valuation,
                   quantity * (
                       SELECT avg_cost FROM portfolio_holdings h WHERE h.code = ps.code
                   ) AS cost_basis,
                   unrealized_pnl
            FROM portfolio_snapshots ps
        )
        WHERE date >= date('now', ? || ' days')
        GROUP BY date
        ORDER BY date DESC
        LIMIT ?
        """,
        (f"-{days}", days),
    ).fetchall()

    return [dict(row) for row in rows]


# ─────────────────────────────────────────────
# Portfolio Signals (保有銘柄関連シグナル)
# ─────────────────────────────────────────────

@router.get("/portfolio/signals")
def get_portfolio_signals(
    days: int = Query(default=7, ge=1, le=90),
    portfolio_conn: sqlite3.Connection = Depends(get_portfolio_connection),
    stocks_conn: sqlite3.Connection = Depends(get_stocks_connection),
):
    """
    保有銘柄に関連するシグナルを stocks.db の signals テーブルから返す。

    保有銘柄コード一覧を portfolio.db から取得し、
    stocks.db の signals テーブルを code でフィルタする。
    """
    holding_codes = [
        row["code"]
        for row in portfolio_conn.execute(
            "SELECT code FROM portfolio_holdings"
        ).fetchall()
    ]

    if not holding_codes:
        return []

    placeholders = ",".join("?" * len(holding_codes))
    rows = stocks_conn.execute(
        f"""
        SELECT id, date, signal_type, code, sector, direction, confidence, reasoning
        FROM signals
        WHERE code IN ({placeholders})
          AND date >= date('now', ? || ' days')
        ORDER BY date DESC, confidence DESC
        """,
        holding_codes + [f"-{days}"],
    ).fetchall()

    result = []
    for row in rows:
        item = dict(row)
        if item.get("reasoning"):
            try:
                item["reasoning"] = json.loads(item["reasoning"])
            except (json.JSONDecodeError, TypeError):
                pass
        result.append(item)

    return result
