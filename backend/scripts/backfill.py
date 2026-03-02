#!/usr/bin/env python3
"""過去データをバックフィルするスクリプト。

J-Quantsから指定期間の全銘柄OHLCVを一括取得し、
全計算パイプライン (騰落率・相関・統計・グラフ) を実行する。

使用例:
    python scripts/backfill.py
    python scripts/backfill.py --years 1
    python scripts/backfill.py --days 2 --skip-stats --skip-graph
    python scripts/backfill.py --sqlite /tmp/stocks.db --kuzu /tmp/kuzu_db
    python scripts/backfill.py --years 2 --skip-graph
"""
import argparse
import logging
import sqlite3
import sys
import time
from datetime import date, timedelta
from pathlib import Path

# プロジェクトルートをパスに追加
sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# ヘルパー関数
# ─────────────────────────────────────────────────────────────────────────────

def _generate_monthly_ranges(start_date: date, end_date: date) -> list[tuple[str, str]]:
    """
    start_date から end_date を月単位に分割した (from, to) のリストを返す。
    例: 2024-01-01 〜 2024-03-15 → [("20240101","20240131"), ("20240201","20240229"), ("20240301","20240315")]
    """
    ranges = []
    current = date(start_date.year, start_date.month, 1)
    while current <= end_date:
        month_end = date(current.year, current.month + 1, 1) - timedelta(days=1) \
                    if current.month < 12 \
                    else date(current.year, 12, 31)
        chunk_start = max(current, start_date)
        chunk_end = min(month_end, end_date)
        ranges.append((
            chunk_start.strftime("%Y%m%d"),
            chunk_end.strftime("%Y%m%d"),
        ))
        if current.month == 12:
            current = date(current.year + 1, 1, 1)
        else:
            current = date(current.year, current.month + 1, 1)
    return ranges


def _fetch_historical(
    sqlite_path: str,
    client,
    start_date: date,
    end_date: date,
    rate_limit_sec: float = 0.0,
) -> int:
    """
    J-Quantsから指定期間の価格データを取得してSQLiteに保存する。

    - v2 ClientV2: 月単位チャンク (from/to) を試み、400 の場合は日次ループにフォールバック
    - v1 Client: 月単位チャンク (from/to)
    - rate_limit_sec: APIコール間のスリープ秒数

    Returns:
        保存した行数の合計
    """
    import pandas as pd

    conn = sqlite3.connect(sqlite_path)
    registered = set(
        pd.read_sql("SELECT code FROM stocks", conn)["code"].tolist()
    )
    conn.close()

    if not registered:
        logger.error("銘柄マスタが空です。先に sync_stock_master を実行してください。")
        return 0

    import jquantsapi as _jq
    is_v2 = isinstance(client, _jq.ClientV2)

    # v2 で範囲指定が利用可能か 1 回テストして判断
    use_daily_loop = False
    if is_v2:
        probe_d = end_date.strftime("%Y%m%d")
        probe_start = (end_date.replace(day=1)).strftime("%Y%m%d")
        try:
            client.get_eq_bars_daily(from_yyyymmdd=probe_start, to_yyyymmdd=probe_d)
        except Exception:
            use_daily_loop = True
            logger.info("  範囲指定 (from/to) が利用不可 → 日次ループモードで取得します")

    if use_daily_loop:
        return _fetch_historical_daily(sqlite_path, client, start_date, end_date, registered, rate_limit_sec)

    # ── 月単位チャンク ──────────────────────────────────────────────
    monthly_ranges = _generate_monthly_ranges(start_date, end_date)
    total_rows = 0

    for i, (from_d, to_d) in enumerate(monthly_ranges, 1):
        logger.info(f"  [{i}/{len(monthly_ranges)}] {from_d[:4]}-{from_d[4:6]} を取得中...")

        try:
            if is_v2:
                df = client.get_eq_bars_daily(from_yyyymmdd=from_d, to_yyyymmdd=to_d)
            else:
                df = client.get_prices_daily_quotes(from_yyyymmdd=from_d, to_yyyymmdd=to_d)
        except Exception as e:
            logger.warning(f"  API エラー ({from_d}〜{to_d}): {e} — スキップ")
            if rate_limit_sec > 0:
                time.sleep(rate_limit_sec)
            continue

        if rate_limit_sec > 0:
            time.sleep(rate_limit_sec)

        if df is None or df.empty:
            logger.info(f"  {from_d}〜{to_d}: データなし")
            continue

        saved = _save_price_df(df, is_v2, registered, sqlite_path)
        total_rows += saved
        logger.info(f"    → {saved} 行保存")

    logger.info(f"  合計: {total_rows} 行取得・保存")
    return total_rows


def _save_price_df(df, is_v2: bool, registered: set, sqlite_path: str) -> int:
    """DataFrame を正規化して SQLite に保存し、保存行数を返す。"""
    import pandas as pd

    if is_v2:
        col_map = {"Code": "code", "Date": "date",
                   "O": "open", "H": "high", "L": "low", "C": "close", "Vo": "volume"}
    else:
        col_map = {"Code": "code", "Date": "date",
                   "Open": "open", "High": "high",
                   "Low": "low", "Close": "close", "Volume": "volume"}

    available = {k: v for k, v in col_map.items() if k in df.columns}
    df = df[list(available.keys())].rename(columns=available)
    df["code"] = df["code"].astype(str).str.replace(r"0$", "", regex=True).str.zfill(4)
    df = df[df["code"].isin(registered)].copy()
    if df.empty:
        return 0

    df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
    for col in ["return_rate", "price_range", "range_pct", "relative_strength"]:
        df[col] = None

    cols = ["code", "date", "open", "high", "low", "close", "volume",
            "return_rate", "price_range", "range_pct", "relative_strength"]
    df = df.reindex(columns=cols)
    rows = [tuple(r) for r in df.itertuples(index=False, name=None)]

    conn = sqlite3.connect(sqlite_path)
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
    conn.close()
    return len(rows)


def _fetch_historical_daily(
    sqlite_path: str,
    client,
    start_date: date,
    end_date: date,
    registered: set,
    rate_limit_sec: float,
) -> int:
    """
    日次ループで価格データを取得する (from/to 範囲指定が使えない場合のフォールバック)。
    平日のみ API を呼び出し、0件の日 (休場) はスキップする。
    """
    total_rows = 0
    current = start_date
    weekdays = []
    while current <= end_date:
        if current.weekday() < 5:
            weekdays.append(current)
        current += timedelta(days=1)

    import jquantsapi as _jq
    is_v2 = isinstance(client, _jq.ClientV2)
    n = len(weekdays)
    logger.info(f"  日次ループ: 平日 {n} 日分を取得します (概算 {n * rate_limit_sec / 60:.0f} 分)")

    for i, d in enumerate(weekdays, 1):
        date_str = d.strftime("%Y%m%d")
        try:
            if is_v2:
                df = client.get_eq_bars_daily(date_yyyymmdd=date_str)
            else:
                df = client.get_prices_daily_quotes(date=d.isoformat())
        except Exception as e:
            logger.warning(f"  [{i}/{n}] {date_str} エラー: {e} — スキップ")
            if rate_limit_sec > 0:
                time.sleep(rate_limit_sec)
            continue

        if rate_limit_sec > 0:
            time.sleep(rate_limit_sec)

        if df is None or df.empty:
            continue  # 休場日

        saved = _save_price_df(df, is_v2, registered, sqlite_path)
        total_rows += saved
        if saved > 0 and (i % 20 == 0 or i == n):
            logger.info(f"  [{i}/{n}] {date_str} 完了 (累計 {total_rows} 行)")

    return total_rows


def _get_trading_dates(sqlite_path: str, start_date: str, end_date: str) -> list[str]:
    """SQLite に保存されている取引日リストを昇順で返す"""
    conn = sqlite3.connect(sqlite_path)
    rows = conn.execute(
        """
        SELECT DISTINCT date FROM daily_prices
        WHERE date >= ? AND date <= ?
        ORDER BY date
        """,
        (start_date, end_date),
    ).fetchall()
    conn.close()
    return [r[0] for r in rows]


# ─────────────────────────────────────────────────────────────────────────────
# メイン処理
# ─────────────────────────────────────────────────────────────────────────────

def backfill(
    sqlite_path: str,
    kuzu_path: str,
    years: int = 2,
    run_stats: bool = True,
    run_graph: bool = True,
    plan: str = "free",
    days: int = 0,
    start_date_str: str = "",
    end_date_str: str = "",
) -> None:
    """
    過去 `years` 年分のデータをバックフィルして全パイプラインを実行する。

    処理順序:
      1. SQLite / KùzuDB スキーマ初期化
      2. J-Quants 銘柄マスタ同期
      3. 過去データ一括取得 (月単位チャンク)
      4. 騰落率・値幅・値幅率を全期間一括計算
      5. 各取引日の対日経225相対強度・セクター集計
      6. 最新日の相関行列計算
      7. 最新日の統計分析 (--skip-stats で省略可)
      8. 最新日のグラフ構築・探索 (--skip-graph で省略可)

    free プランの制限:
      - 過去2年分のみ取得可 (years は自動的に 2 に制限)
      - 直近12週間は取得不可 (end_date を自動調整)
      - API レート: 5 req/min → APIコール間に 12 秒スリープ

    days > 0 の場合: years を無視し、end_date から遡った N 平日分のみ取得する。
    start_date_str / end_date_str (YYYY-MM-DD): 指定時は自動計算を上書きする。
    """
    from scripts.init_sqlite import init_sqlite
    from scripts.init_kuzu import init_kuzu
    from src.batch import fetch, compute, statistics, graph

    # free プランの制限を適用
    rate_limit_sec = 0.0
    today = date.today()
    if plan == "free":
        if years > 2:
            logger.warning(f"freeプランは過去2年分のみ取得可能なため years={years} → 2 に制限します")
            years = 2
        rate_limit_sec = 25.0  # 内部ページネーション込みで余裕を持たせる

        # end_date を直近12週前の直近平日に調整
        end_date = today - timedelta(weeks=12)
        while end_date.weekday() >= 5:  # 土=5, 日=6
            end_date -= timedelta(days=1)
        logger.info(f"freeプラン: end_date を直近12週前の {end_date} に設定")

        # start_date は「今日 - 2年」(end_dateではなく今日基準)
        try:
            start_date = date(today.year - years, today.month, today.day)
        except ValueError:
            start_date = date(today.year - years, today.month, 28)
        logger.info(f"freeプラン: start_date を今日基準の2年前 {start_date} に設定")
    else:
        end_date = today
        try:
            start_date = date(end_date.year - years, end_date.month, end_date.day)
        except ValueError:
            start_date = date(end_date.year - years, end_date.month, 28)

    # --days が指定された場合は years より優先して start_date を短縮する
    if days > 0:
        # N 平日分をカバーするカレンダー日数 (ceil(N * 7/5) + 3 日のバッファ)
        cal_days = int(days * 7 / 5) + 3
        start_date = end_date - timedelta(days=cal_days)
        logger.info(f"--days {days}: start_date を {start_date} に短縮 (約 {days} 平日分)")

    # --start-date / --end-date が指定された場合は自動計算を上書きする
    if start_date_str:
        start_date = date.fromisoformat(start_date_str)
        logger.info(f"--start-date 指定: start_date = {start_date}")
    if end_date_str:
        end_date = date.fromisoformat(end_date_str)
        logger.info(f"--end-date 指定: end_date = {end_date}")

    logger.info("=" * 60)
    logger.info(f"バックフィル開始: {start_date} 〜 {end_date}")
    logger.info(f"  SQLite    : {sqlite_path}")
    logger.info(f"  KùzuDB    : {kuzu_path}")
    logger.info(f"  プラン    : {plan}")
    logger.info(f"  統計分析  : {'有効' if run_stats else '無効'}")
    logger.info(f"  グラフ    : {'有効' if run_graph else '無効'}")
    if rate_limit_sec > 0:
        logger.info(f"  レート制限: {rate_limit_sec:.0f} 秒/リクエスト (5 req/min)")
    logger.info("=" * 60)

    # ── 1. スキーマ初期化 ────────────────────────────────────────
    logger.info("[1/8] スキーマ初期化...")
    init_sqlite(sqlite_path)
    init_kuzu(kuzu_path)
    logger.info("  完了")

    # ── 2. 銘柄マスタ同期 ────────────────────────────────────────
    logger.info("[2/8] 銘柄マスタ同期 (J-Quants)...")
    conn = sqlite3.connect(sqlite_path)
    client = fetch._get_client()
    n_stocks = fetch.sync_stock_master(conn, client)
    conn.close()
    logger.info(f"  銘柄マスタ: {n_stocks} 件登録")
    if rate_limit_sec > 0:
        # eq_master はページネーションで複数コールを消費するため長めに待機
        wait = rate_limit_sec * 3
        logger.info(f"  レート制限: {wait:.0f} 秒待機中 (ページネーション考慮)...")
        time.sleep(wait)

    # ── 3. 過去データ一括取得 ────────────────────────────────────
    logger.info(f"[3/8] 過去データ取得 ({start_date} 〜 {end_date})...")
    total_rows = _fetch_historical(sqlite_path, client, start_date, end_date, rate_limit_sec)
    logger.info(f"  合計: {total_rows} 行取得・保存")

    if total_rows == 0:
        logger.error("  取得データが 0 件です。API 設定を確認してください。")
        return

    # ── 4. 騰落率・値幅・値幅率 (全期間一括) ────────────────────
    logger.info("[4/8] 騰落率・値幅を計算中...")
    n_updated = compute.compute_returns(sqlite_path)
    logger.info(f"  {n_updated} 行更新")

    # ── 5. 各取引日の相対強度・セクター集計 ─────────────────────
    trading_dates = _get_trading_dates(
        sqlite_path, start_date.isoformat(), end_date.isoformat()
    )
    n_days = len(trading_dates)
    logger.info(f"[5/8] 取引日ごとの計算 ({n_days} 日分)...")

    for i, d in enumerate(trading_dates, 1):
        compute.compute_relative_strength(sqlite_path, d)
        compute.compute_sector_summary(sqlite_path, d)
        statistics.run_fund_flow(sqlite_path, d)
        if i % 50 == 0 or i == n_days:
            logger.info(f"  {i}/{n_days} 日完了 (最新: {d})")

    # ── 6. 最新日の相関行列 ──────────────────────────────────────
    if not trading_dates:
        logger.warning("取引日が見つかりませんでした。以降の処理をスキップします。")
        return

    last_date = trading_dates[-1]
    logger.info(f"[6/8] 相関行列計算 (基準日: {last_date})...")
    n_corr = compute.compute_correlations(sqlite_path, last_date)
    logger.info(f"  相関エッジ: {n_corr} 件")

    # ── 7. 統計分析 ──────────────────────────────────────────────
    if run_stats:
        logger.info(f"[7/8] 統計分析 (最新日: {last_date})...")
        logger.info("  グレンジャー因果 / リードラグ / 資金フロー / レジーム判定を実行中...")
        logger.info("  ※ 全銘柄ペアの検定は数分かかる場合があります")
        statistics.run_all(sqlite_path, last_date)
        logger.info("  統計分析完了")
    else:
        logger.info("[7/8] 統計分析 — スキップ (--skip-stats)")

    # ── 8. グラフ構築・探索 ──────────────────────────────────────
    if run_graph:
        logger.info(f"[8/8] グラフ構築・探索 (最新日: {last_date})...")
        result = graph.update_and_query(kuzu_path, sqlite_path, last_date)
        n_chains = len(result.get("chains", []))
        n_flows  = len(result.get("fund_flow_paths", []))
        logger.info(f"  因果連鎖: {n_chains} チェーン / 資金フロー経路: {n_flows} 件")
    else:
        logger.info("[8/8] グラフ構築 — スキップ (--skip-graph)")

    logger.info("=" * 60)
    logger.info("バックフィル完了!")
    logger.info(f"  期間       : {start_date} 〜 {end_date} ({n_days} 取引日)")
    logger.info(f"  取得行数   : {total_rows}")
    logger.info(f"  最終処理日 : {last_date}")
    logger.info("=" * 60)


# ─────────────────────────────────────────────────────────────────────────────
# CLI エントリポイント
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="日経225 過去データのバックフィル",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
例:
  python scripts/backfill.py
  python scripts/backfill.py --years 1
  python scripts/backfill.py --sqlite /data/stocks.db --kuzu /data/kuzu_db
  python scripts/backfill.py --skip-stats --skip-graph  # データ取得のみ
        """,
    )
    parser.add_argument(
        "--sqlite",
        default=None,
        help="SQLite ファイルパス (省略時は SQLITE_PATH 環境変数または /tmp/stocks.db)",
    )
    parser.add_argument(
        "--kuzu",
        default=None,
        help="KùzuDB ディレクトリパス (省略時は KUZU_PATH 環境変数または /tmp/kuzu_db)",
    )
    parser.add_argument(
        "--years",
        type=int,
        default=2,
        help="バックフィルする年数 (デフォルト: 2)",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=0,
        help="取得する最近の平日数 (例: --days 2 で最新2日分のみ。指定時は --years を無視)",
    )
    parser.add_argument(
        "--skip-stats",
        action="store_true",
        help="統計分析 (グレンジャー因果・リードラグ等) をスキップする",
    )
    parser.add_argument(
        "--skip-graph",
        action="store_true",
        help="KùzuDB グラフ構築・探索をスキップする",
    )
    parser.add_argument(
        "--start-date",
        default="",
        help="取得開始日 (YYYY-MM-DD)。指定時は --years / --days を上書き",
    )
    parser.add_argument(
        "--end-date",
        default="",
        help="取得終了日 (YYYY-MM-DD)。指定時はfreeプランの自動調整を上書き",
    )
    args = parser.parse_args()

    # パスの解決 (引数 > 環境変数 > デフォルト)
    import os
    sqlite_path = args.sqlite or os.environ.get("SQLITE_PATH", "/tmp/stocks.db")
    kuzu_path   = args.kuzu   or os.environ.get("KUZU_PATH",   "/tmp/kuzu_db")
    plan        = os.environ.get("JQUANTS_PLAN", "free")

    backfill(
        sqlite_path=sqlite_path,
        kuzu_path=kuzu_path,
        years=args.years,
        run_stats=not args.skip_stats,
        run_graph=not args.skip_graph,
        plan=plan,
        days=args.days,
        start_date_str=args.start_date,
        end_date_str=args.end_date,
    )


if __name__ == "__main__":
    main()
