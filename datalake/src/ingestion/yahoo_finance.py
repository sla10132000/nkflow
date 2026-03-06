"""
Phase 13: 外部データ取得モジュール

- 信用残高 (週次): J-Quants API /markets/weekly_margin_interest
- 為替レート (日次): Yahoo Finance REST API (認証不要)
"""
import logging
import sqlite3
from datetime import date, datetime, timedelta, timezone
from typing import Optional

import pandas as pd
import requests

logger = logging.getLogger(__name__)

# Yahoo Finance API (追加ライブラリ不要)
_YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
_YAHOO_HEADERS = {"User-Agent": "Mozilla/5.0"}

# 取得する通貨ペア: (Yahooシンボル, DBのpair名)
FX_PAIRS = [
    ("USDJPY=X", "USDJPY"),
    ("EURUSD=X", "EURUSD"),
]


# ─────────────────────────────────────────────────────────────────────────────
# 為替レート
# ─────────────────────────────────────────────────────────────────────────────

def _fetch_yahoo_ohlcv(
    symbol: str,
    *,
    days: Optional[int] = None,
    range_str: Optional[str] = None,
    start_date: Optional[str] = None,
    include_volume: bool = False,
    timeout: int = 10,
) -> pd.DataFrame:
    """
    Yahoo Finance から指定シンボルの日次 OHLCV を取得する。

    期間指定は以下のいずれか (排他):
      - days: 直近 N 日分 (range パラメータ)
      - range_str: Yahoo Finance range 文字列 (例: "5y")
      - start_date: 'YYYY-MM-DD' 以降を period1/period2 で取得

    Args:
        symbol: Yahoo Finance シンボル (例: "USDJPY=X", "^GSPC")
        include_volume: True なら volume カラムを含める
        timeout: HTTP タイムアウト秒

    Returns:
        columns=[date, open, high, low, close(, volume)] の DataFrame。取得失敗時は空
    """
    url = _YAHOO_CHART_URL.format(symbol=symbol)

    if start_date is not None:
        start_ts = int(datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp())
        end_ts = int(datetime.now(timezone.utc).timestamp())
        params: dict = {"interval": "1d", "period1": start_ts, "period2": end_ts}
    elif range_str is not None:
        params = {"interval": "1d", "range": range_str}
    else:
        params = {"interval": "1d", "range": f"{days or 30}d"}

    try:
        resp = requests.get(url, params=params, headers=_YAHOO_HEADERS, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logger.warning(f"Yahoo Finance 取得失敗 ({symbol}): {e}")
        return pd.DataFrame()

    try:
        result = data["chart"]["result"][0]
        timestamps = result["timestamp"]
        ohlcv = result["indicators"]["quote"][0]

        cols: dict = {
            "date":  [datetime.fromtimestamp(t, tz=timezone.utc).strftime("%Y-%m-%d") for t in timestamps],
            "open":  ohlcv.get("open",  [None] * len(timestamps)),
            "high":  ohlcv.get("high",  [None] * len(timestamps)),
            "low":   ohlcv.get("low",   [None] * len(timestamps)),
            "close": ohlcv.get("close", [None] * len(timestamps)),
        }
        if include_volume:
            cols["volume"] = ohlcv.get("volume", [None] * len(timestamps))

        df = pd.DataFrame(cols)
        return df.dropna(subset=["close"])
    except (KeyError, IndexError, TypeError) as e:
        logger.warning(f"Yahoo Finance レスポンス解析失敗 ({symbol}): {e}")
        return pd.DataFrame()


def fetch_nikkei_close(conn: sqlite3.Connection, target_date: Optional[str] = None) -> bool:
    """
    Yahoo Finance から日経225 (^N225) の終値を取得し daily_summary に保存する。
    また、OHLC を us_indices テーブルにも保存する (ローソク足チャート用)。

    Args:
        conn: SQLite 接続
        target_date: 'YYYY-MM-DD'。省略時は今日

    Returns:
        更新できた場合 True
    """
    if target_date is None:
        target_date = date.today().isoformat()

    df = _fetch_yahoo_ohlcv("^N225", days=5)
    if df.empty:
        logger.warning("日経225: データ取得できませんでした")
        return False

    row = df[df["date"] <= target_date].sort_values("date").tail(1)
    if row.empty:
        logger.warning(f"日経225: {target_date} 以前のデータなし")
        return False

    close_val = float(row["close"].iloc[0])
    conn.execute(
        """
        INSERT INTO daily_summary (date, nikkei_close)
        VALUES (?, ?)
        ON CONFLICT(date) DO UPDATE SET nikkei_close = excluded.nikkei_close
        """,
        (target_date, close_val),
    )

    # OHLC を us_indices にも保存 (ローソク足チャート用)
    for _, r in df.iterrows():
        if r["date"] > target_date:
            continue
        try:
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
                (r["date"], r["open"], r["high"], r["low"], r["close"]),
            )
        except Exception as e:
            logger.warning(f"日経225 us_indices 保存失敗 ({r['date']}): {e}")

    conn.commit()
    logger.info(f"日経225終値: {target_date} = {close_val}")
    return True


def fetch_exchange_rates(
    conn: sqlite3.Connection,
    target_date: Optional[str] = None,
) -> int:
    """
    FX レートを取得して exchange_rates テーブルに INSERT OR REPLACE する。
    ma20 は DBに保存済みの過去データから計算する。

    Args:
        conn: SQLite 接続
        target_date: 'YYYY-MM-DD'。省略時は今日

    Returns:
        挿入・更新した行数
    """
    if target_date is None:
        target_date = date.today().isoformat()

    total_rows = 0

    for yahoo_symbol, pair_name in FX_PAIRS:
        df = _fetch_yahoo_ohlcv(yahoo_symbol, days=30)
        if df.empty:
            logger.warning(f"{pair_name}: データ取得できませんでした")
            continue

        # 当日以前のデータのみに絞る
        df = df[df["date"] <= target_date].copy()
        if df.empty:
            continue

        # 変化率 (前日比)
        df = df.sort_values("date").reset_index(drop=True)
        df["change_rate"] = df["close"].pct_change()

        # ma20: DBの過去データと結合して計算
        past = pd.read_sql(
            "SELECT date, close FROM exchange_rates WHERE pair = ? AND date < ? "
            "ORDER BY date DESC LIMIT 19",
            conn,
            params=(pair_name, df["date"].min()),
        )
        if not past.empty:
            combined = pd.concat([past[["date", "close"]], df[["date", "close"]]], ignore_index=True)
            combined = combined.sort_values("date").reset_index(drop=True)
            combined["ma20"] = combined["close"].rolling(20).mean()
            # 新規取得分のma20のみ df にマージ
            ma_map = combined.set_index("date")["ma20"].to_dict()
            df["ma20"] = df["date"].map(ma_map)
        else:
            df["ma20"] = df["close"].rolling(20).mean()

        df["pair"] = pair_name

        rows = [
            (
                row.date, row.pair,
                row.open, row.high, row.low, row.close,
                row.change_rate if pd.notna(row.change_rate) else None,
                row.ma20 if pd.notna(row.ma20) else None,
            )
            for row in df.itertuples(index=False)
        ]

        conn.executemany(
            """
            INSERT OR REPLACE INTO exchange_rates
                (date, pair, open, high, low, close, change_rate, ma20)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        conn.commit()
        total_rows += len(rows)
        logger.info(f"exchange_rates: {pair_name} {len(rows)} 行挿入")

    return total_rows


# ─────────────────────────────────────────────────────────────────────────────
# 米国主要株価指数
# ─────────────────────────────────────────────────────────────────────────────

def _fetch_index_ohlcv(symbol: str, start_date: Optional[str] = None) -> pd.DataFrame:
    """Yahoo Finance から指数の OHLCV+volume を取得する (_fetch_yahoo_ohlcv のラッパー)。"""
    from src.config import US_INDEX_INITIAL_PERIOD

    if start_date is not None:
        return _fetch_yahoo_ohlcv(symbol, start_date=start_date, include_volume=True, timeout=15)
    return _fetch_yahoo_ohlcv(symbol, range_str=US_INDEX_INITIAL_PERIOD, include_volume=True, timeout=15)


def fetch_us_indices(db_path: str) -> dict:
    """
    米国主要株価指数と恐怖指数の OHLCV を取得し SQLite の us_indices テーブルに保存する。

    - 差分更新: テーブル内の最新日付以降のみ取得
    - 初回: 直近5年分を一括取得
    - 取引日のみ保存 (NaN 行はスキップ)
    - エラー時も他ティッカーの処理は継続
    - 対象: US_INDEX_TICKERS + FEAR_INDEX_TICKERS (VIX 等)

    Args:
        db_path: SQLite ファイルパス

    Returns:
        {"status": "ok", "rows_inserted": N, "tickers": [...]}
    """
    from src.config import FEAR_INDEX_TICKERS, US_INDEX_TICKERS, US_SECTOR_ETF_TICKERS

    # 米国株価指数 + 恐怖指数 + セクター ETF を同じテーブルに保存
    combined_tickers: dict[str, str] = {
        **US_INDEX_TICKERS,
        **FEAR_INDEX_TICKERS,
        **{k: v["name"] for k, v in US_SECTOR_ETF_TICKERS.items()},
    }

    conn = sqlite3.connect(db_path)
    total_rows = 0
    tickers_done: list[str] = []

    try:
        for ticker, name in combined_tickers.items():
            try:
                latest = conn.execute(
                    "SELECT MAX(date) FROM us_indices WHERE ticker = ?", (ticker,)
                ).fetchone()[0]

                if latest is None:
                    df = _fetch_index_ohlcv(ticker)
                else:
                    start = (date.fromisoformat(latest) + timedelta(days=1)).isoformat()
                    df = _fetch_index_ohlcv(ticker, start_date=start)

                if df.empty:
                    logger.info(f"us_indices: {ticker} データなし")
                    tickers_done.append(ticker)
                    continue

                # 最新日以降のみに絞る (差分更新の重複防止)
                if latest is not None:
                    df = df[df["date"] > latest].copy()

                if df.empty:
                    logger.info(f"us_indices: {ticker} 新規データなし (最新: {latest})")
                    tickers_done.append(ticker)
                    continue

                rows = [
                    (
                        row.date, ticker, name,
                        row.open   if pd.notna(row.open)   else None,
                        row.high   if pd.notna(row.high)   else None,
                        row.low    if pd.notna(row.low)    else None,
                        row.close,
                        int(row.volume) if row.volume is not None and pd.notna(row.volume) else None,
                    )
                    for row in df.itertuples(index=False)
                ]

                conn.executemany(
                    """
                    INSERT OR REPLACE INTO us_indices
                        (date, ticker, name, open, high, low, close, volume)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    rows,
                )
                conn.commit()
                total_rows += len(rows)
                tickers_done.append(ticker)
                logger.info(f"us_indices: {ticker} {len(rows)} 行挿入")

            except Exception as e:
                logger.error(f"us_indices: {ticker} 処理失敗 (継続): {e}")

    finally:
        conn.close()

    return {"status": "ok", "rows_inserted": total_rows, "tickers": tickers_done}


# ─────────────────────────────────────────────────────────────────────────────
# BTC Fear & Greed Index (Phase 21)
# ─────────────────────────────────────────────────────────────────────────────

def fetch_crypto_fear_greed(db_path: str, days: int = 30) -> int:
    """
    Alternative.me の Bitcoin Fear & Greed Index を取得し
    SQLite の crypto_fear_greed テーブルに保存する。

    - 差分更新: 既存の最新日以降のみ挿入
    - エラー時は 0 を返す

    Args:
        db_path: SQLite ファイルパス
        days: 取得日数 (デフォルト 30)

    Returns:
        挿入・更新した行数
    """
    from src.config import ALTERNATIVE_ME_FNG_URL

    try:
        resp = requests.get(
            ALTERNATIVE_ME_FNG_URL,
            params={"limit": days, "format": "json"},
            headers=_YAHOO_HEADERS,
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logger.warning(f"BTC Fear & Greed 取得失敗: {e}")
        return 0

    records = data.get("data", [])
    if not records:
        logger.info("BTC Fear & Greed: データなし")
        return 0

    conn = sqlite3.connect(db_path)
    rows_inserted = 0
    try:
        for record in records:
            try:
                ts = int(record["timestamp"])
                date_str = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
                value = int(record["value"])
                classification = record["value_classification"]
                created_at = datetime.now(timezone.utc).isoformat()

                conn.execute(
                    """
                    INSERT OR REPLACE INTO crypto_fear_greed
                        (date, value, value_classification, created_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (date_str, value, classification, created_at),
                )
                rows_inserted += 1
            except (KeyError, ValueError, TypeError) as e:
                logger.warning(f"BTC Fear & Greed レコード解析失敗: {e}")
                continue

        conn.commit()
        logger.info(f"crypto_fear_greed: {rows_inserted} 行挿入")
    finally:
        conn.close()

    return rows_inserted


# ─────────────────────────────────────────────────────────────────────────────
# 信用残高
# ─────────────────────────────────────────────────────────────────────────────

def fetch_margin_balance(
    conn: sqlite3.Connection,
    target_date: Optional[str] = None,
    client=None,
) -> int:
    """
    J-Quants API から信用取引週次残高を取得して margin_balances に保存する。

    週次データなので target_date を含む週のデータを取得する。
    J-Quants の weekly_margin_interest は発表日ベースで約1週間遅延がある。

    Args:
        conn: SQLite 接続
        target_date: 'YYYY-MM-DD'。省略時は今日
        client: J-Quants APIクライアント (省略時は自動生成)

    Returns:
        挿入・更新した行数
    """
    if target_date is None:
        target_date = date.today().isoformat()

    if client is None:
        from src.ingestion.jquants import _get_client
        client = _get_client()

    # 直近の月曜〜対象日の範囲で取得 (週次データは発表週の金曜が基準)
    target_dt = date.fromisoformat(target_date)

    # 既存データが少ない場合は過去180日分を遡及取得 (初回バックフィル)
    existing_weeks = conn.execute(
        "SELECT COUNT(DISTINCT week_date) FROM margin_balances"
    ).fetchone()[0]
    lookback_days = 180 if existing_weeks < 8 else 14

    from_dt = target_dt - timedelta(days=lookback_days)
    from_str = from_dt.strftime("%Y%m%d")
    to_str = target_dt.strftime("%Y%m%d")

    logger.info(f"信用残高取得: {from_str} 〜 {to_str}")

    try:
        import jquantsapi as _jq
        if isinstance(client, _jq.ClientV2):
            # v2 API: get_mkt_margin_interest_range (from/to パラメータは400エラーになるため range メソッドを使う)
            df = client.get_mkt_margin_interest_range(
                start_dt=from_str,
                end_dt=to_str,
            )
        else:
            # v1 API: get_weekly_margin_interest (名称が異なる)
            df = client.get_weekly_margin_interest(
                from_yyyymmdd=from_str,
                to_yyyymmdd=to_str,
            )
    except AttributeError:
        logger.warning("margin interest API が利用できません (プランを確認してください)")
        return 0
    except Exception as e:
        logger.warning(f"信用残高取得失敗: {e}")
        return 0

    if df is None or df.empty:
        logger.info("信用残高データなし")
        return 0

    # カラム名の正規化 (v2 実際のカラム名: LongVol/ShrtVol)
    col_map = {
        "Code": "code",
        "Date": "week_date",
        "LongVol": "margin_buy",    # 信用買残高
        "ShrtVol": "margin_sell",   # 信用売残高
        # v1 のカラム名 (fallback)
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

    # 信用倍率 (margin_ratio = buy / sell)
    df["margin_ratio"] = df.apply(
        lambda r: round(r["margin_buy"] / r["margin_sell"], 4)
        if r["margin_sell"] and r["margin_sell"] > 0
        else None,
        axis=1,
    )

    # 前週比変化率を計算
    df = df.sort_values(["code", "week_date"]).reset_index(drop=True)
    df["buy_change"] = df.groupby("code")["margin_buy"].pct_change()
    df["sell_change"] = df.groupby("code")["margin_sell"].pct_change()

    # stocks テーブルに存在する銘柄のみに絞る
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
    logger.info(f"margin_balances: {len(rows)} 行挿入")
    return len(rows)
