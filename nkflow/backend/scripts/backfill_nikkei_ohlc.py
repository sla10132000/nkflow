"""
日経225 (^N225) の OHLC データを us_indices テーブルにバックフィルする。

使い方:
    cd backend
    SQLITE_PATH=/tmp/stocks.db .venv/bin/python scripts/backfill_nikkei_ohlc.py [--days 500]
"""
import argparse
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import requests

_YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/^N225"
_YAHOO_HEADERS = {"User-Agent": "Mozilla/5.0"}


def fetch_nikkei_ohlc(days: int):
    params = {"interval": "1d", "range": f"{days}d"}
    resp = requests.get(_YAHOO_CHART_URL, params=params, headers=_YAHOO_HEADERS, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    result = data["chart"]["result"][0]
    timestamps = result["timestamp"]
    ohlcv = result["indicators"]["quote"][0]
    rows = []
    for i, ts in enumerate(timestamps):
        d = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
        o = ohlcv["open"][i]
        h = ohlcv["high"][i]
        l = ohlcv["low"][i]
        c = ohlcv["close"][i]
        if c is None:
            continue
        rows.append((d, o, h, l, c))
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=500, help="取得日数 (デフォルト 500)")
    args = parser.parse_args()

    db_path = os.environ.get("SQLITE_PATH", "/tmp/stocks.db")
    print(f"DB: {db_path}")
    print(f"取得日数: {args.days}")

    print("Yahoo Finance から日経225 OHLC を取得中...")
    rows = fetch_nikkei_ohlc(args.days)
    print(f"取得件数: {len(rows)}")

    conn = sqlite3.connect(db_path)
    inserted = 0
    for date, o, h, l, c in rows:
        conn.execute(
            """
            INSERT INTO us_indices (date, ticker, name, open, high, low, close, volume)
            VALUES (?, '^N225', '日経225', ?, ?, ?, ?, 0)
            ON CONFLICT(date, ticker) DO UPDATE SET
                open  = excluded.open,
                high  = excluded.high,
                low   = excluded.low,
                close = excluded.close
            """,
            (date, o, h, l, c),
        )
        inserted += 1

    conn.commit()
    conn.execute("PRAGMA wal_checkpoint(PASSIVE)")
    conn.close()
    print(f"保存完了: {inserted} 件")


if __name__ == "__main__":
    main()
