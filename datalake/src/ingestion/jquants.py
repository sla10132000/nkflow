"""J-Quants APIからデータを取得してSQLiteに保存する"""
import logging
import sqlite3
from datetime import date, datetime
from typing import Optional

import pandas as pd
import requests

logger = logging.getLogger(__name__)

# ── 投資主体別売買動向 investor_type マッピング ──────────────────────────────
_INVESTOR_TYPE_MAP = {
    "Foreigners":        "foreigners",
    "Individuals":       "individuals",
    "InvestmentTrusts":  "investment_trusts",
    "TrustBanks":        "trust_banks",
    "BusinessCompanies": "business_cos",
}

_JQUANTS_TRADES_SPEC_URL = "https://api.jquants.com/v1/markets/trades_spec"


def _get_client():
    """
    J-Quants APIクライアントを生成する (v2 ClientV2)。
    """
    import os
    import jquantsapi
    from src.config import JQUANTS_PLAN

    api_key = os.environ.get("JQUANTS_API_KEY", "")
    if not api_key:
        raise RuntimeError("JQUANTS_API_KEY が設定されていません")

    return jquantsapi.ClientV2(api_key=api_key)


def _is_trading_day(client, target_date: str) -> bool:
    """指定日が取引日かどうかを確認する"""
    try:
        df = client.get_prices_daily_quotes(date=target_date)
        return df is not None and not df.empty
    except Exception:
        return False


def sync_stock_master(conn: sqlite3.Connection, client=None) -> int:
    """
    J-Quants の listed_info から銘柄マスタを同期する。
    プライム市場の全銘柄を stocks テーブルに登録する。

    Returns:
        登録・更新された銘柄数
    """
    if client is None:
        client = _get_client()

    logger.info("銘柄マスタを取得中...")

    # ClientV2 (v2 API) と旧 Client (v1 API) でメソッド名・カラム名が異なる
    from src.pipeline.raw_store import save_raw

    import jquantsapi as _jq
    if isinstance(client, _jq.ClientV2):
        df = client.get_eq_master()
        if df is None or df.empty:
            logger.warning("eq_master が空でした")
            return 0
        save_raw("market", "equity", "jquants", "stock_master", date.today().isoformat(), df)
        # v2: Mkt == '0111' がプライム市場
        if "Mkt" in df.columns:
            df = df[df["Mkt"] == "0111"].copy()
        col_map = {"Code": "code", "CoName": "name", "S33Nm": "sector"}
        available = {k: v for k, v in col_map.items() if k in df.columns}
        df = df[list(available.keys())].rename(columns=available)
        if "sector" not in df.columns:
            df["sector"] = "その他"
    else:
        df = client.get_listed_info()
        if df is None or df.empty:
            logger.warning("listed_info が空でした")
            return 0
        save_raw("market", "equity", "jquants", "stock_master", date.today().isoformat(), df)
        # v1: MarketCode == '0111' がプライム市場
        if "MarketCode" in df.columns:
            df = df[df["MarketCode"] == "0111"].copy()
        col_map = {"Code": "code", "CompanyName": "name", "Sector33CodeName": "sector"}
        available = {k: v for k, v in col_map.items() if k in df.columns}
        df = df[list(available.keys())].rename(columns=available)
        if "sector" not in df.columns:
            if "Sector17CodeName" in df.columns:
                df["sector"] = df["Sector17CodeName"]
            else:
                df["sector"] = "その他"

    # code の末尾に付く "0" を除去 (J-Quants は 5桁コードを返す場合あり)
    df["code"] = df["code"].astype(str).str.replace(r"0$", "", regex=True).str.zfill(4)

    df = df[["code", "name", "sector"]].drop_duplicates(subset="code")

    rows = list(df.itertuples(index=False, name=None))
    conn.executemany(
        "INSERT OR REPLACE INTO stocks (code, name, sector) VALUES (?, ?, ?)",
        rows,
    )
    conn.commit()
    logger.info(f"銘柄マスタを登録: {len(rows)} 件")
    return len(rows)


def fetch_daily(
    conn: sqlite3.Connection,
    target_date: Optional[str] = None,
    client=None,
) -> int:
    """
    指定日の日次OHLCVを取得して daily_prices に INSERT OR REPLACE する。

    Args:
        conn: SQLite接続
        target_date: 'YYYY-MM-DD' 形式。省略時は今日
        client: J-Quants APIクライアント (省略時は自動生成)

    Returns:
        挿入された行数。取引日でない場合は 0
    """
    if target_date is None:
        target_date = date.today().isoformat()

    if client is None:
        client = _get_client()

    logger.info(f"日次データを取得中: {target_date}")

    # 銘柄マスタが空なら先に同期
    cur = conn.execute("SELECT COUNT(*) FROM stocks")
    if cur.fetchone()[0] == 0:
        logger.info("銘柄マスタが空のため同期します")
        sync_stock_master(conn, client)

    # 日次株価を取得 (v2 / v1 で API が異なる)
    import jquantsapi as _jq
    import requests as _requests
    date_nodash = target_date.replace("-", "")
    try:
        if isinstance(client, _jq.ClientV2):
            df = client.get_eq_bars_daily(date_yyyymmdd=date_nodash)
            col_map = {"Code": "code", "Date": "date",
                       "O": "open", "H": "high", "L": "low", "C": "close", "Vo": "volume"}
        else:
            df = client.get_prices_daily_quotes(date=target_date)
            col_map = {"Code": "code", "Date": "date",
                       "Open": "open", "High": "high", "Low": "low",
                       "Close": "close", "Volume": "volume"}
    except _requests.exceptions.HTTPError as e:
        if e.response is not None and e.response.status_code == 400:
            logger.info(f"{target_date} は取引日ではありません (400 Bad Request)")
            return 0
        raise

    if df is None or df.empty:
        logger.info(f"{target_date} は取引日ではありません (データなし)")
        return 0

    # Raw data save (正規化前の生データを保存)
    from src.pipeline.raw_store import save_raw
    save_raw("market", "equity", "jquants", "daily_prices", target_date, df)

    # カラム名の正規化
    available = {k: v for k, v in col_map.items() if k in df.columns}
    df = df[list(available.keys())].rename(columns=available)

    # code の末尾 "0" を除去
    df["code"] = df["code"].astype(str).str.replace(r"0$", "", regex=True).str.zfill(4)

    # stocks テーブルに存在する銘柄のみに絞る (外部キー制約)
    registered = pd.read_sql("SELECT code FROM stocks", conn)["code"].tolist()
    df = df[df["code"].isin(registered)].copy()

    if df.empty:
        logger.info("stocks マスタに登録済みの銘柄データがありませんでした")
        return 0

    # date カラムを 'YYYY-MM-DD' 文字列に統一
    df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")

    # 計算カラムは compute.py で埋めるため NULL で挿入
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
    logger.info(f"日次データを挿入: {len(rows)} 件 ({target_date})")
    return len(rows)


def fetch_investor_flows(
    conn: sqlite3.Connection,
    from_date: str,
    to_date: str,
    section: str = "TSEPrime",
    client=None,
) -> int:
    """
    J-Quants API から投資主体別売買動向を取得して investor_flow_weekly に保存する。

    エンドポイント: GET https://api.jquants.com/v1/markets/trades_spec
    認証: x-api-key ヘッダー (ClientV2 の _api_key を使用)

    レスポンスの各行を investor_type ごとに分解して保存する。
    API レスポンスの 1 行 = 1 週 × 複数投資主体 → DB では 1 行 = 1 週 × 1 投資主体。

    Args:
        conn: SQLite 接続
        from_date: 取得開始日 ('YYYY-MM-DD')
        to_date: 取得終了日 ('YYYY-MM-DD')
        section: 市場区分 (デフォルト: 'TSEPrime')
        client: J-Quants APIクライアント (省略時は自動生成)

    Returns:
        保存した行数 (週 × 投資主体の組み合わせ数)
    """
    if client is None:
        client = _get_client()

    api_key = client._api_key
    headers = {
        "x-api-key": api_key,
    }

    params: dict = {
        "section": section,
        "from": from_date.replace("-", ""),
        "to": to_date.replace("-", ""),
    }

    logger.info(f"投資主体別売買動向を取得中: {from_date} ~ {to_date} ({section})")

    try:
        resp = requests.get(
            _JQUANTS_TRADES_SPEC_URL,
            params=params,
            headers=headers,
            timeout=30,
        )
        resp.raise_for_status()
    except requests.exceptions.HTTPError as e:
        if e.response is not None and e.response.status_code == 400:
            logger.info(f"trades_spec: データなし ({from_date}~{to_date})")
            return 0
        raise

    data = resp.json()
    weekly_records = data.get("trades_spec", [])

    if not weekly_records:
        logger.info("trades_spec: レスポンスが空でした")
        return 0

    rows: list[tuple] = []
    for record in weekly_records:
        published_date: Optional[str] = record.get("PublishedDate")
        start_date: str = record.get("StartDate", "")
        end_date: str = record.get("EndDate", "")
        rec_section: str = record.get("Section", section)

        # 日付を YYYY-MM-DD 形式に統一 (API は YYYYMMDD で返す場合がある)
        start_date = _normalize_date(start_date)
        end_date = _normalize_date(end_date)
        if published_date:
            published_date = _normalize_date(published_date)

        if not start_date or not end_date:
            continue

        for api_prefix, investor_type in _INVESTOR_TYPE_MAP.items():
            sales_key = f"{api_prefix}Sales"
            purchases_key = f"{api_prefix}Purchases"
            balance_key = f"{api_prefix}Balance"

            sales = record.get(sales_key)
            purchases = record.get(purchases_key)
            balance = record.get(balance_key)

            # 少なくとも1つの値がある場合のみ保存
            if sales is None and purchases is None and balance is None:
                continue

            rows.append((
                start_date,
                end_date,
                rec_section,
                investor_type,
                float(sales) if sales is not None else None,
                float(purchases) if purchases is not None else None,
                float(balance) if balance is not None else None,
                published_date,
            ))

    if not rows:
        logger.info("trades_spec: 保存可能なレコードなし")
        return 0

    conn.executemany(
        """
        INSERT OR REPLACE INTO investor_flow_weekly
            (week_start, week_end, section, investor_type,
             sales, purchases, balance, published_date)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    conn.commit()
    logger.info(f"投資主体別売買動向を保存: {len(rows)} 件 ({from_date}~{to_date})")
    return len(rows)


def _normalize_date(date_str: str) -> str:
    """
    日付文字列を 'YYYY-MM-DD' 形式に統一する。
    YYYYMMDD および YYYY-MM-DD の両形式に対応。

    Args:
        date_str: 日付文字列

    Returns:
        'YYYY-MM-DD' 形式の文字列。変換不能な場合は空文字列。
    """
    if not date_str:
        return ""
    date_str = str(date_str).strip()
    if len(date_str) == 8 and date_str.isdigit():
        return f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}"
    if len(date_str) == 10 and date_str[4] == "-" and date_str[7] == "-":
        return date_str
    return ""
