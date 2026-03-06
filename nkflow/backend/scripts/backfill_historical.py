"""
J-Quants から欠落している過去データをバックフィルするスクリプト。

対象期間: 2016-10-01 〜 2021-03-01 (自動検出)

使用方法:
    export JQUANTS_API_KEY=<your_key>
    export S3_BUCKET=nkflow-data-268914462689
    python backend/scripts/backfill_historical.py

    # ドライランで対象日を確認するだけ
    python backend/scripts/backfill_historical.py --dry-run

    # 開始/終了日を手動指定
    python backend/scripts/backfill_historical.py --start 2017-01-01 --end 2018-12-31
"""

import argparse
import logging
import os
import sqlite3
import sys
import time
from datetime import date, timedelta
from pathlib import Path

# プロジェクトの src を PYTHONPATH に追加
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def get_existing_dates(conn: sqlite3.Connection) -> set[str]:
    """daily_prices に既存の全日付を返す"""
    cur = conn.execute("SELECT DISTINCT date FROM daily_prices")
    return {row[0] for row in cur.fetchall()}


def detect_missing_range(conn: sqlite3.Connection) -> tuple[date, date]:
    """
    daily_prices の最古・最新日付から欠落範囲を自動検出する。
    最古日の翌日〜最新日の2ヶ月前を対象とする。
    """
    cur = conn.execute("SELECT MIN(date), MAX(date) FROM daily_prices")
    row = cur.fetchone()
    oldest = date.fromisoformat(row[0])
    newest = date.fromisoformat(row[1])

    # 既存データの年別分布で大きなギャップを探す
    cur = conn.execute(
        "SELECT strftime('%Y', date) as yr, MIN(date), MAX(date), COUNT(DISTINCT date) "
        "FROM daily_prices GROUP BY yr ORDER BY yr"
    )
    years = cur.fetchall()
    logger.info("既存データ年別分布:")
    for yr, mn, mx, cnt in years:
        logger.info(f"  {yr}: {mn} 〜 {mx} ({cnt} 日)")

    # 連続する年の最大日と次の年の最小日の間のギャップを検出
    gap_start = None
    gap_end = None
    for i in range(len(years) - 1):
        yr1, _, max1, _ = years[i]
        yr2, min2, _, _ = years[i + 1]
        d1 = date.fromisoformat(max1)
        d2 = date.fromisoformat(min2)
        gap_days = (d2 - d1).days
        if gap_days > 60:  # 2ヶ月以上の空白
            logger.info(f"  ギャップ検出: {d1} 〜 {d2} ({gap_days} 日)")
            if gap_start is None or d1 < gap_start:
                gap_start = d1 + timedelta(days=1)
            if gap_end is None or d2 > gap_end:
                gap_end = d2 - timedelta(days=1)

    if gap_start and gap_end:
        return gap_start, gap_end

    # ギャップが見つからなければ最古の翌日〜最新の前日
    return oldest + timedelta(days=1), newest - timedelta(days=1)


def fetch_and_insert(
    conn: sqlite3.Connection,
    client,
    target_date: date,
    registered_codes: set[str],
) -> int:
    """指定日のデータを取得して INSERT OR REPLACE し、挿入行数を返す"""
    import pandas as pd
    import requests as _req

    date_nodash = target_date.strftime("%Y%m%d")
    date_iso = target_date.isoformat()

    try:
        df = client.get_eq_bars_daily(date_yyyymmdd=date_nodash)
    except _req.exceptions.HTTPError as e:
        if e.response is not None and e.response.status_code == 400:
            logger.debug(f"{date_iso}: 取引日ではありません (400)")
            return 0
        raise

    if df is None or df.empty:
        logger.debug(f"{date_iso}: データなし")
        return 0

    col_map = {
        "Code": "code", "Date": "date",
        "O": "open", "H": "high", "L": "low", "C": "close", "Vo": "volume",
    }
    available = {k: v for k, v in col_map.items() if k in df.columns}
    df = df[list(available.keys())].rename(columns=available)

    df["code"] = df["code"].astype(str).str.replace(r"0$", "", regex=True).str.zfill(4)
    df = df[df["code"].isin(registered_codes)].copy()

    if df.empty:
        return 0

    df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")

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
    conn.commit()
    return len(rows)


def main():
    parser = argparse.ArgumentParser(description="J-Quants 過去データ バックフィル")
    parser.add_argument("--db", default="/tmp/stocks_new.db", help="SQLite DB パス")
    parser.add_argument("--start", help="開始日 YYYY-MM-DD (省略時: 自動検出)")
    parser.add_argument("--end", help="終了日 YYYY-MM-DD (省略時: 自動検出)")
    parser.add_argument("--dry-run", action="store_true", help="取得せず対象日数のみ表示")
    parser.add_argument("--commit-every", type=int, default=10, help="何日ごとにログ出力するか")
    args = parser.parse_args()

    api_key = os.environ.get("JQUANTS_API_KEY", "")
    if not api_key:
        logger.error("JQUANTS_API_KEY が設定されていません")
        sys.exit(1)

    import jquantsapi
    client = jquantsapi.ClientV2(api_key=api_key)

    conn = sqlite3.connect(args.db)

    # 欠落範囲を検出
    if args.start and args.end:
        start = date.fromisoformat(args.start)
        end = date.fromisoformat(args.end)
    else:
        start, end = detect_missing_range(conn)

    logger.info(f"バックフィル対象: {start} 〜 {end}")

    # 既存日付を取得
    existing = get_existing_dates(conn)

    # 対象日リストを生成 (カレンダー日で iterate、非取引日は API が 0 を返す)
    target_dates = []
    d = start
    while d <= end:
        if d.isoformat() not in existing:
            target_dates.append(d)
        d += timedelta(days=1)

    logger.info(f"未取得日数 (カレンダー): {len(target_dates)} 日")

    if args.dry_run:
        logger.info("--dry-run モード: 取得は行いません")
        conn.close()
        return

    # 銘柄コード一覧を取得
    registered_codes = set(
        row[0] for row in conn.execute("SELECT code FROM stocks").fetchall()
    )
    logger.info(f"登録済み銘柄数: {len(registered_codes)}")

    # バックフィル実行
    total_rows = 0
    trading_days = 0
    skipped = 0
    start_time = time.time()

    for i, d in enumerate(target_dates):
        try:
            n = fetch_and_insert(conn, client, d, registered_codes)
            if n > 0:
                total_rows += n
                trading_days += 1
            else:
                skipped += 1

            if (i + 1) % args.commit_every == 0 or (i + 1) == len(target_dates):
                elapsed = time.time() - start_time
                pct = (i + 1) / len(target_dates) * 100
                logger.info(
                    f"進捗: {i+1}/{len(target_dates)} 日 ({pct:.1f}%) "
                    f"| 取引日: {trading_days} | 挿入行: {total_rows:,} "
                    f"| 経過: {elapsed:.0f}s"
                )

        except Exception as e:
            logger.error(f"{d}: エラー - {e}")
            # エラーでも継続
            time.sleep(1)

    logger.info(
        f"完了: 取引日 {trading_days} 日, 挿入 {total_rows:,} 行, "
        f"非取引日スキップ {skipped} 日"
    )
    conn.close()


if __name__ == "__main__":
    main()
