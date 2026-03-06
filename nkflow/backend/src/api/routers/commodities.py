"""GET /api/commodities — コモディティ先物 (Phase 26)"""
from sqlite3 import Connection

from fastapi import APIRouter, Depends, Query

from src.api.storage import get_connection

# コモディティティッカー一覧 (表示名マッピング)
_COMMODITY_TICKERS = ("GC=F", "CL=F", "SI=F", "HG=F", "NG=F", "ZW=F", "ZC=F")
_COMMODITY_NAMES: dict[str, str] = {
    "GC=F": "Gold Futures",
    "CL=F": "WTI Crude Oil",
    "SI=F": "Silver Futures",
    "HG=F": "Copper Futures",
    "NG=F": "Natural Gas",
    "ZW=F": "Wheat Futures",
    "ZC=F": "Corn Futures",
}
_COMMODITY_LABELS: dict[str, str] = {
    "GC=F": "金",
    "CL=F": "原油 (WTI)",
    "SI=F": "銀",
    "HG=F": "銅",
    "NG=F": "天然ガス",
    "ZW=F": "小麦",
    "ZC=F": "コーン",
}
_COMMODITY_PLACEHOLDERS = ",".join(f"'{t}'" for t in _COMMODITY_TICKERS)

router = APIRouter()


@router.get("/commodities")
def get_commodities(
    symbol: str = Query(default="GC=F", description="コモディティシンボル"),
    days: int = Query(default=90, ge=1, le=1825),
    conn: Connection = Depends(get_connection),
):
    """
    指定コモディティの時系列 OHLCV を返す (昇順)。

    Args:
        symbol: コモディティシンボル (例: GC=F, CL=F, SI=F, HG=F)
        days:   取得日数 (デフォルト 90)
    """
    rows = conn.execute(
        """
        SELECT date, ticker AS symbol, name, open, high, low, close, volume,
               ROUND((close - LAG(close) OVER (ORDER BY date))
                     / LAG(close) OVER (ORDER BY date) * 100, 4)
               AS change_pct
        FROM (
            SELECT date, ticker, name, open, high, low, close, volume
            FROM us_indices
            WHERE ticker = ?
            ORDER BY date DESC
            LIMIT ?
        ) sub
        ORDER BY date ASC
        """,
        (symbol.upper(), days),
    ).fetchall()

    return [dict(row) for row in rows]


@router.get("/commodities/summary")
def get_commodities_summary(conn: Connection = Depends(get_connection)):
    """
    全コモディティの最新価格・前日比を返す。
    """
    rows = conn.execute(
        f"""
        WITH latest AS (
            SELECT ui.ticker, ui.name, ui.date, ui.close
            FROM us_indices ui
            INNER JOIN (
                SELECT ticker, MAX(date) AS max_date
                FROM us_indices
                WHERE ticker IN ({_COMMODITY_PLACEHOLDERS})
                GROUP BY ticker
            ) m ON ui.ticker = m.ticker AND ui.date = m.max_date
        ),
        prev AS (
            SELECT ui.ticker, ui.close AS prev_close
            FROM us_indices ui
            INNER JOIN (
                SELECT ticker, MAX(date) AS prev_date
                FROM us_indices
                WHERE ticker IN ({_COMMODITY_PLACEHOLDERS})
                  AND date < (
                      SELECT MAX(date) FROM us_indices
                      WHERE ticker IN ({_COMMODITY_PLACEHOLDERS})
                  )
                GROUP BY ticker
            ) p ON ui.ticker = p.ticker AND ui.date = p.prev_date
        )
        SELECT
            l.ticker AS symbol,
            l.name,
            l.date,
            l.close,
            ROUND((l.close - p.prev_close) / p.prev_close * 100, 4) AS change_pct
        FROM latest l
        LEFT JOIN prev p ON l.ticker = p.ticker
        ORDER BY l.ticker
        """
    ).fetchall()

    result = []
    for row in rows:
        d = dict(row)
        d["label"] = _COMMODITY_LABELS.get(d["symbol"], d["symbol"])
        result.append(d)
    return result
