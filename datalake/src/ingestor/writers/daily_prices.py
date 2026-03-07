"""
daily_prices writer — raw envelope のデータを daily_prices テーブルに書き込む。

対象 envelope: category="market", source="jquants", data_type="daily_prices"
S3 キー例: raw/market/equity/jquants/daily_prices/2026-03-06.json

既存の jquants.py fetch_daily() の INSERT ロジックを ingestor 向けに切り出したもの。
"""
import logging
import sqlite3
from typing import Any

import pandas as pd

from src.ingestor.dispatcher import register

logger = logging.getLogger(__name__)

# v2 API (get_eq_bars_daily) と v1 API (get_prices_daily_quotes) 両方のカラム名に対応
_COL_MAP_V2 = {"Code": "code", "Date": "date", "O": "open", "H": "high", "L": "low", "C": "close", "Vo": "volume"}
_COL_MAP_V1 = {"Code": "code", "Date": "date", "Open": "open", "High": "high", "Low": "low", "Close": "close", "Volume": "volume"}


@register("market", "jquants", "daily_prices")
def write(conn: sqlite3.Connection, date_str: str, data: Any) -> int:
    """daily_prices テーブルへ INSERT OR REPLACE する。

    Args:
        conn: SQLite 接続
        date_str: 対象日 (YYYY-MM-DD)
        data: raw envelope の data フィールド (list of dict)

    Returns:
        挿入・更新した行数
    """
    if not data:
        logger.info(f"data が空 — スキップ ({date_str})")
        return 0

    df = pd.DataFrame(data)
    if df.empty:
        logger.info(f"DataFrame が空 — スキップ ({date_str})")
        return 0

    # v2 / v1 どちらのカラム名かを判定して正規化
    if "O" in df.columns:
        col_map = _COL_MAP_V2
    else:
        col_map = _COL_MAP_V1

    available = {k: v for k, v in col_map.items() if k in df.columns}
    df = df[list(available.keys())].rename(columns=available)

    # code の末尾 "0" を除去して 4 桁ゼロ埋め
    df["code"] = df["code"].astype(str).str.replace(r"0$", "", regex=True).str.zfill(4)

    # stocks テーブルに登録済みの銘柄のみ対象 (外部キー制約)
    registered = pd.read_sql("SELECT code FROM stocks", conn)["code"].tolist()
    df = df[df["code"].isin(registered)].copy()

    if df.empty:
        logger.info(f"stocks マスタ登録済みの銘柄がなし — スキップ ({date_str})")
        return 0

    # date カラムを 'YYYY-MM-DD' 文字列に統一
    df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")

    # 計算カラムは compute.py で後から埋めるため NULL で挿入
    for col in ["return_rate", "price_range", "range_pct", "relative_strength"]:
        df[col] = None

    cols = ["code", "date", "open", "high", "low", "close", "volume",
            "return_rate", "price_range", "range_pct", "relative_strength"]
    df = df.reindex(columns=cols)

    rows = [tuple(r) for r in df.itertuples(index=False, name=None)]
    conn.executemany(
        """
        INSERT OR REPLACE INTO daily_prices
            (code, date, open, high, low, close, volume,
             return_rate, price_range, range_pct, relative_strength)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    logger.info(f"daily_prices 挿入: {len(rows)} 件 ({date_str})")
    return len(rows)
