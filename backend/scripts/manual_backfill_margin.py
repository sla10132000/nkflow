#!/usr/bin/env python3
"""手動 信用残高バックフィルスクリプト

1. /tmp/stocks.db を使用 (make pull で取得済みであること)
2. J-Quants API から過去2年分の信用残高を取得して margin_balances に保存
3. 全週の market_pressure を再計算して margin_trading_weekly / market_pressure_daily を更新
4. stocks.db を S3 にアップロード

使い方:
    cd backend
    S3_BUCKET=nkflow-data-XXXXXXXX .venv/bin/python scripts/manual_backfill_margin.py

    # 期間を指定する場合
    S3_BUCKET=nkflow-data-XXXXXXXX .venv/bin/python scripts/manual_backfill_margin.py \\
        --from-date 2024-01-01 --to-date 2026-03-03
"""
import argparse
import logging
import os
import sqlite3
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)

S3_BUCKET = os.environ.get("S3_BUCKET", "nkflow-data-268914462689")
SQLITE_PATH = os.environ.get("SQLITE_PATH", "/tmp/stocks.db")
# 2年分のデフォルト取得期間
DEFAULT_LOOKBACK_DAYS = 730


def _get_jquants_client():
    """J-Quants API クライアントを返す。SSM または環境変数から認証情報を取得。"""
    api_key = os.environ.get("JQUANTS_API_KEY", "")
    if api_key:
        import jquantsapi
        return jquantsapi.ClientV2(api_key=api_key)

    # SSM から取得を試みる
    try:
        import boto3
        ssm = boto3.client("ssm", region_name="ap-northeast-1")
        resp = ssm.get_parameter(Name="/nkflow/jquants-api-key", WithDecryption=True)
        api_key = resp["Parameter"]["Value"]
        import jquantsapi
        return jquantsapi.ClientV2(api_key=api_key)
    except Exception as e:
        logger.error(f"J-Quants API キー取得失敗: {e}")
        sys.exit(1)


def _fetch_one_date(client, date_str: str):
    """J-Quants API を1日分呼び出して DataFrame を返す。失敗時は None。

    /v2/markets/margin-interest は date パラメータのみ受け付ける。
    from/to による範囲取得は 400 エラーになる。
    _range メソッドは全日付を並列リクエストするためレート制限に触れやすく使わない。
    """
    import time
    import jquantsapi as _jq

    for attempt in range(4):
        try:
            if isinstance(client, _jq.ClientV2):
                return client.get_mkt_margin_interest(date_yyyymmdd=date_str)
            else:
                return client.get_weekly_margin_interest(date_yyyymmdd=date_str)
        except AttributeError:
            logger.warning("margin interest API が利用できません (プランを確認してください)")
            return None
        except Exception as e:
            if "429" in str(e) and attempt < 3:
                wait = 60 * (attempt + 1)
                logger.warning(f"レート制限 (429)、{wait}秒待機してリトライ ({attempt+1}/4)")
                time.sleep(wait)
            else:
                logger.warning(f"信用残高取得失敗 ({date_str}): {e}")
                return None
    return None


def fetch_margin_balance_range(
    conn: sqlite3.Connection,
    client,
    from_date: str,
    to_date: str,
    interval_sec: float = 8.0,
) -> int:
    """
    指定期間の信用残高を J-Quants API から取得して margin_balances に挿入する。

    信用残高は週次データ (金曜日締め) なので、金曜日のみ API を呼び出す。
    interval_sec 秒間隔で順次取得してレート制限を回避する。

    Args:
        conn: SQLite 接続
        client: J-Quants API クライアント
        from_date: 'YYYY-MM-DD'
        to_date: 'YYYY-MM-DD'
        interval_sec: API コール間の待機秒数

    Returns:
        挿入行数
    """
    import time
    import pandas as pd

    start = date.fromisoformat(from_date)
    end = date.fromisoformat(to_date)
    all_dfs = []

    # 金曜日 (weekday=4) のみ API を呼び出す
    # 最初の金曜日を求める
    days_until_friday = (4 - start.weekday()) % 7
    first_friday = start + timedelta(days=days_until_friday)

    fridays = []
    d = first_friday
    while d <= end:
        fridays.append(d)
        d += timedelta(days=7)

    logger.info(f"対象金曜日: {len(fridays)} 件 ({fridays[0].isoformat()} 〜 {fridays[-1].isoformat()})")

    for i, friday in enumerate(fridays):
        date_str = friday.strftime("%Y-%m-%d")
        logger.info(f"  [{i+1}/{len(fridays)}] 取得: {date_str}")
        df_day = _fetch_one_date(client, date_str)

        if df_day is not None and not df_day.empty:
            all_dfs.append(df_day)
            logger.info(f"    → {len(df_day)} 行取得")
        else:
            logger.info("    → データなし (非営業日 or 発表なし)")

        if i < len(fridays) - 1:
            time.sleep(interval_sec)

    if not all_dfs:
        logger.info("信用残高データなし (全期間)")
        return 0

    df = pd.concat(all_dfs, ignore_index=True).drop_duplicates()
    logger.info(f"合計 {len(df)} 行取得 (重複除去後)")

    if df is None or df.empty:
        logger.info("信用残高データなし")
        return 0

    col_map = {
        "Code": "code",
        "Date": "week_date",
        "LongVol": "margin_buy",
        "ShrtVol": "margin_sell",
        "StockCode": "code",
        "WeekDate": "week_date",
        "LongMargin": "margin_buy",
        "ShortMargin": "margin_sell",
    }
    df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})

    required = {"code", "week_date", "margin_buy", "margin_sell"}
    if not required.issubset(df.columns):
        logger.warning(f"信用残高: 必要カラムが不足 — {df.columns.tolist()}")
        return 0

    df["code"] = df["code"].astype(str).str.replace(r"0$", "", regex=True).str.zfill(4)
    df["week_date"] = pd.to_datetime(df["week_date"]).dt.strftime("%Y-%m-%d")
    df["margin_buy"] = pd.to_numeric(df["margin_buy"], errors="coerce")
    df["margin_sell"] = pd.to_numeric(df["margin_sell"], errors="coerce")

    df["margin_ratio"] = df.apply(
        lambda r: round(r["margin_buy"] / r["margin_sell"], 4)
        if r["margin_sell"] and r["margin_sell"] > 0
        else None,
        axis=1,
    )

    df = df.sort_values(["code", "week_date"]).reset_index(drop=True)
    df["buy_change"] = df.groupby("code")["margin_buy"].pct_change()
    df["sell_change"] = df.groupby("code")["margin_sell"].pct_change()

    registered = set(
        r[0] for r in conn.execute("SELECT code FROM stocks").fetchall()
    )
    df = df[df["code"].isin(registered)].copy()

    if df.empty:
        logger.info("信用残高: 登録済み銘柄なし")
        return 0

    rows = [
        (
            row.code, row.week_date,
            row.margin_buy if pd.notna(row.margin_buy) else None,
            row.margin_sell if pd.notna(row.margin_sell) else None,
            row.margin_ratio if pd.notna(getattr(row, "margin_ratio", None)) else None,
            row.buy_change if pd.notna(row.buy_change) else None,
            row.sell_change if pd.notna(row.sell_change) else None,
        )
        for row in df.itertuples(index=False)
    ]

    conn.executemany(
        """
        INSERT OR REPLACE INTO margin_balances
            (code, week_date, margin_buy, margin_sell, margin_ratio, buy_change, sell_change)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    conn.commit()

    weeks = df["week_date"].nunique()
    logger.info(f"margin_balances: {len(rows)} 行挿入 ({weeks} 週分)")
    return len(rows)


def recalc_market_pressure(conn: sqlite3.Connection) -> int:
    """
    margin_balances の全 week_date に対して run_market_pressure を実行する。

    Returns:
        処理した週数
    """
    from src.batch.statistics import run_market_pressure

    weeks = conn.execute(
        "SELECT DISTINCT week_date FROM margin_balances ORDER BY week_date"
    ).fetchall()

    if not weeks:
        logger.warning("margin_balances にデータがありません")
        return 0

    logger.info(f"market_pressure を {len(weeks)} 週分再計算します")
    success = 0
    for (week_date,) in weeks:
        n = run_market_pressure(SQLITE_PATH, week_date)
        if n > 0:
            success += 1
            logger.info(f"  {week_date}: OK")
        else:
            logger.debug(f"  {week_date}: スキップ (データ不足)")

    logger.info(f"market_pressure 再計算完了: {success}/{len(weeks)} 週")
    return success


def main() -> None:
    parser = argparse.ArgumentParser(description="信用残高バックフィル")
    parser.add_argument("--from-date", default=None, help="取得開始日 YYYY-MM-DD")
    parser.add_argument("--to-date", default=None, help="取得終了日 YYYY-MM-DD")
    parser.add_argument("--no-upload", action="store_true", help="S3 アップロードをスキップ")
    args = parser.parse_args()

    to_date = args.to_date or date.today().isoformat()
    from_date = args.from_date or (
        date.fromisoformat(to_date) - timedelta(days=DEFAULT_LOOKBACK_DAYS)
    ).isoformat()

    logger.info(f"=== 信用残高バックフィル: {from_date} 〜 {to_date} ===")
    logger.info(f"DB: {SQLITE_PATH}")

    # Step 1: J-Quants クライアント取得
    logger.info("=== Step 1: J-Quants クライアント初期化 ===")
    client = _get_jquants_client()

    # Step 2: margin_balances バックフィル
    logger.info("=== Step 2: 信用残高取得 ===")
    conn = sqlite3.connect(SQLITE_PATH)
    conn.row_factory = sqlite3.Row

    rows_inserted = fetch_margin_balance_range(conn, client, from_date, to_date)
    logger.info(f"挿入行数: {rows_inserted}")

    if rows_inserted == 0:
        logger.error("データが取得できませんでした。API キーとプランを確認してください。")
        conn.close()
        sys.exit(1)

    # Step 3: 現在の margin_balances の週数を確認
    weeks_in_db = conn.execute(
        "SELECT COUNT(DISTINCT week_date) FROM margin_balances"
    ).fetchone()[0]
    logger.info(f"margin_balances: {weeks_in_db} 週分")

    conn.close()

    # Step 4: market_pressure 再計算
    logger.info("=== Step 3: market_pressure 再計算 ===")
    conn = sqlite3.connect(SQLITE_PATH)
    conn.row_factory = sqlite3.Row
    weeks_done = recalc_market_pressure(conn)
    conn.close()

    # Step 5: 結果確認
    conn = sqlite3.connect(SQLITE_PATH)
    mtw_count = conn.execute(
        "SELECT COUNT(*) FROM margin_trading_weekly WHERE market_code = 'ALL'"
    ).fetchone()[0]
    mpd_count = conn.execute(
        "SELECT COUNT(*) FROM market_pressure_daily"
    ).fetchone()[0]
    conn.close()

    logger.info(f"margin_trading_weekly (ALL): {mtw_count} 件")
    logger.info(f"market_pressure_daily: {mpd_count} 件")

    # Step 6: アップロード前に WAL チェックポイント + integrity_check
    logger.info("=== Step 5: DB 整合性確認 ===")
    conn = sqlite3.connect(SQLITE_PATH)
    try:
        # WAL を main ファイルに書き戻す (SHM/WAL ファイル不要な状態にする)
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        result = conn.execute("PRAGMA integrity_check").fetchone()
        if result and result[0] != "ok":
            logger.error(f"integrity_check 失敗: {result[0]}")
            conn.close()
            sys.exit(1)
        logger.info("integrity_check: ok")
    finally:
        conn.close()

    # Step 7: S3 アップロード
    if args.no_upload:
        logger.info("=== S3 アップロードをスキップ (--no-upload) ===")
    else:
        logger.info("=== Step 6: stocks.db を S3 にアップロード ===")
        subprocess.run(
            ["aws", "s3", "cp", SQLITE_PATH, f"s3://{S3_BUCKET}/data/stocks.db"],
            check=True,
        )
        logger.info("アップロード完了")

    logger.info(
        f"=== 完了: margin_trading_weekly {mtw_count} 週, "
        f"market_pressure_daily {mpd_count} 件 ==="
    )


if __name__ == "__main__":
    main()
