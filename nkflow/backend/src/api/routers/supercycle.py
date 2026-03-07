"""GET /api/supercycle — コモディティ・スーパーサイクル分析 (Phase 27)"""
from sqlite3 import Connection

from fastapi import APIRouter, Depends, HTTPException, Query

from src.api.storage import get_connection
from src.api.supercycle_config import (
    COMMODITY_LABELS,
    CONFIG_UPDATED,
    CORRELATIONS,
    PHASES,
    SCENARIOS,
    SECTOR_PHASES,
    COMMODITY_PHASES,
)
from src.config import SUPERCYCLE_SECTORS

router = APIRouter()

# スーパーサイクル対象の全ティッカー (セクターから収集)
_ALL_SC_TICKERS: tuple[str, ...] = tuple(
    t for sector in SUPERCYCLE_SECTORS.values() for t in sector["tickers"]
)
_SC_TICKERS_PLACEHOLDERS = ",".join(f"'{t}'" for t in _ALL_SC_TICKERS)


def _get_latest_prices(conn: Connection) -> dict[str, dict]:
    """us_indices テーブルから各ティッカーの最新 close / change_pct を取得する。"""
    rows = conn.execute(
        f"""
        WITH latest AS (
            SELECT ui.ticker, ui.date, ui.close
            FROM us_indices ui
            INNER JOIN (
                SELECT ticker, MAX(date) AS max_date
                FROM us_indices
                WHERE ticker IN ({_SC_TICKERS_PLACEHOLDERS})
                GROUP BY ticker
            ) m ON ui.ticker = m.ticker AND ui.date = m.max_date
        ),
        prev AS (
            SELECT ui.ticker, ui.close AS prev_close
            FROM us_indices ui
            INNER JOIN (
                SELECT ticker, MAX(date) AS prev_date
                FROM us_indices
                WHERE ticker IN ({_SC_TICKERS_PLACEHOLDERS})
                  AND date < (
                      SELECT MAX(date) FROM us_indices
                      WHERE ticker IN ({_SC_TICKERS_PLACEHOLDERS})
                  )
                GROUP BY ticker
            ) p ON ui.ticker = p.ticker AND ui.date = p.prev_date
        )
        SELECT
            l.ticker,
            l.date,
            l.close,
            ROUND((l.close - p.prev_close) / p.prev_close * 100, 4) AS change_pct
        FROM latest l
        LEFT JOIN prev p ON l.ticker = p.ticker
        """
    ).fetchall()
    return {row["ticker"]: dict(row) for row in rows}


@router.get("/supercycle/overview")
def get_supercycle_overview(conn: Connection = Depends(get_connection)):
    """
    スーパーサイクル分析のオーバービューを返す。

    - フェーズ定義 (4フェーズモデル)
    - セクター別フェーズ位置 + 配下コモディティの最新価格
    - シナリオ分析 (3シナリオ)
    - セクター間相関

    フェーズ位置は config 駆動 (エディトリアル判断)。
    """
    latest = _get_latest_prices(conn)

    sectors = []
    for sector_id, sector_cfg in SUPERCYCLE_SECTORS.items():
        sector_phase_info = SECTOR_PHASES.get(sector_id, {"phase": 2, "position": 2.0})

        commodities = []
        for ticker in sector_cfg["tickers"]:
            price_info = latest.get(ticker, {})
            # コモディティ個別のフェーズオーバーライドがあれば使用
            phase_info = COMMODITY_PHASES.get(ticker, sector_phase_info)
            commodities.append(
                {
                    "ticker": ticker,
                    "label": COMMODITY_LABELS.get(ticker, ticker),
                    "close": price_info.get("close"),
                    "date": price_info.get("date"),
                    "change_pct": price_info.get("change_pct"),
                    "phase": phase_info["phase"],
                    "position": phase_info["position"],
                    "is_etf": not ticker.endswith("=F") and not ticker.startswith("^"),
                }
            )

        sectors.append(
            {
                "id": sector_id,
                "label": sector_cfg["label"],
                "phase": sector_phase_info["phase"],
                "position": sector_phase_info["position"],
                "commodities": commodities,
            }
        )

    return {
        "phases": {str(k): v for k, v in PHASES.items()},
        "sectors": sectors,
        "scenarios": SCENARIOS,
        "correlations": CORRELATIONS,
        "updated": CONFIG_UPDATED,
    }


@router.get("/supercycle/sector-returns")
def get_supercycle_sector_returns(
    sector: str = Query(..., description="セクターID (例: energy, base_metals)"),
    days: int = Query(default=1825, ge=30, le=3650),
    conn: Connection = Depends(get_connection),
):
    """
    指定セクターのコモディティ長期時系列を base-100 正規化して返す。

    各系列の最初の close を 100 として正規化する。
    """
    if sector not in SUPERCYCLE_SECTORS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown sector: {sector}. Valid: {list(SUPERCYCLE_SECTORS.keys())}",
        )

    sector_cfg = SUPERCYCLE_SECTORS[sector]
    tickers = sector_cfg["tickers"]
    placeholders = ",".join(f"'{t}'" for t in tickers)

    rows = conn.execute(
        f"""
        SELECT date, ticker, close
        FROM (
            SELECT date, ticker, close
            FROM us_indices
            WHERE ticker IN ({placeholders})
            ORDER BY date DESC
            LIMIT {len(tickers) * days}
        ) sub
        ORDER BY ticker, date ASC
        """
    ).fetchall()

    # ティッカーごとにグループ化して正規化
    from collections import defaultdict

    ticker_data: dict[str, list] = defaultdict(list)
    for row in rows:
        ticker_data[row["ticker"]].append({"date": row["date"], "close": row["close"]})

    series = []
    for ticker in tickers:
        data_points = ticker_data.get(ticker, [])
        if not data_points:
            series.append(
                {
                    "ticker": ticker,
                    "label": COMMODITY_LABELS.get(ticker, ticker),
                    "is_etf": not ticker.endswith("=F") and not ticker.startswith("^"),
                    "data": [],
                }
            )
            continue

        base_close = data_points[0]["close"]
        normalized = []
        if base_close and base_close != 0:
            for pt in data_points:
                if pt["close"] is not None:
                    normalized.append(
                        {"date": pt["date"], "value": round(pt["close"] / base_close * 100, 2)}
                    )

        series.append(
            {
                "ticker": ticker,
                "label": COMMODITY_LABELS.get(ticker, ticker),
                "is_etf": not ticker.endswith("=F") and not ticker.startswith("^"),
                "data": normalized,
            }
        )

    return {
        "sector": sector,
        "label": sector_cfg["label"],
        "base_date": series[0]["data"][0]["date"] if series and series[0]["data"] else None,
        "series": series,
    }


@router.get("/supercycle/performance")
def get_supercycle_performance(conn: Connection = Depends(get_connection)):
    """
    全スーパーサイクルコモディティのマルチホライズンリターンを返す。

    各コモディティについて 1M / 3M / 6M / 1Y / 3Y / 5Y のリターンを計算する。
    """
    # ホライズンごとの日数 (近似)
    horizons = {
        "1m": 21,
        "3m": 63,
        "6m": 126,
        "1y": 252,
        "3y": 756,
        "5y": 1260,
    }

    max_days = max(horizons.values()) + 5

    rows = conn.execute(
        f"""
        SELECT date, ticker, close
        FROM (
            SELECT date, ticker, close
            FROM us_indices
            WHERE ticker IN ({_SC_TICKERS_PLACEHOLDERS})
            ORDER BY date DESC
            LIMIT {len(_ALL_SC_TICKERS) * max_days}
        ) sub
        ORDER BY ticker, date DESC
        """
    ).fetchall()

    from collections import defaultdict

    ticker_data: dict[str, list] = defaultdict(list)
    for row in rows:
        ticker_data[row["ticker"]].append(
            {"date": row["date"], "close": row["close"]}
        )

    result = []
    for sector_id, sector_cfg in SUPERCYCLE_SECTORS.items():
        for ticker in sector_cfg["tickers"]:
            data_points = ticker_data.get(ticker, [])
            if not data_points:
                continue

            latest_close = data_points[0]["close"]
            returns: dict[str, float | None] = {}

            for horizon_key, n_days in horizons.items():
                if len(data_points) > n_days:
                    past_close = data_points[n_days]["close"]
                    if past_close and past_close != 0 and latest_close is not None:
                        returns[horizon_key] = round(
                            (latest_close - past_close) / past_close * 100, 2
                        )
                    else:
                        returns[horizon_key] = None
                else:
                    returns[horizon_key] = None

            result.append(
                {
                    "ticker": ticker,
                    "label": COMMODITY_LABELS.get(ticker, ticker),
                    "sector_id": sector_id,
                    "sector_label": sector_cfg["label"],
                    "is_etf": not ticker.endswith("=F") and not ticker.startswith("^"),
                    "latest_close": latest_close,
                    "latest_date": data_points[0]["date"],
                    "returns": returns,
                }
            )

    return result
