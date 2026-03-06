"""統計分析モジュール: グレンジャー因果・リードラグ・資金フロー・レジーム判定・市場圧力"""
import json
import logging
import sqlite3
from datetime import date
from typing import Optional

import numpy as np
import pandas as pd
from joblib import Parallel, delayed
from scipy.stats import linregress
from statsmodels.tsa.stattools import grangercausalitytests

from src.config import (
    FUND_FLOW_WINDOW,
    GRANGER_MAX_LAG,
    GRANGER_P_THRESHOLD,
    GRANGER_WINDOW,
    LEAD_LAG_MAX,
    LEAD_LAG_THRESHOLD,
    MAX_GRANGER_STOCKS,
    REGIME_LONG_WINDOW,
    REGIME_SHORT_WINDOW,
)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# グレンジャー因果検定
# ─────────────────────────────────────────────────────────────────────────────

def _granger_one_pair(
    returns_a: np.ndarray,
    returns_b: np.ndarray,
    code_a: str,
    code_b: str,
    calc_date: str,
) -> list[tuple]:
    """
    1ペアに対してグレンジャー因果検定を双方向で実行する。
    joblib から呼ばれるため、モジュールトップレベルの関数として定義。

    A→B の検定: data = [B, A] (statsmodels 規約: data[:,0] が被予測変数)

    Returns:
        [(source, target, lag_days, p_value, f_stat, period, calc_date), ...]
    """
    results = []
    directions = [
        (code_a, code_b, returns_b, returns_a),  # A → B (Aが先行してBを予測)
        (code_b, code_a, returns_a, returns_b),  # B → A
    ]

    for source, target, y, x in directions:
        data = np.column_stack([y, x])
        try:
            gc = grangercausalitytests(data, maxlag=GRANGER_MAX_LAG, verbose=False)
        except Exception:
            continue

        best_lag, best_p, best_f = None, 1.0, 0.0
        for lag, tests in gc.items():
            p = tests[0]["ssr_ftest"][1]
            f = tests[0]["ssr_ftest"][0]
            if p < best_p:
                best_lag, best_p, best_f = lag, p, f

        if best_p < GRANGER_P_THRESHOLD:
            results.append(
                (source, target, int(best_lag), float(best_p), float(best_f), "60d", calc_date)
            )

    return results


def run_granger(db_path: str, calc_date: str, n_jobs: int = -1) -> int:
    """
    グレンジャー因果検定を全銘柄ペアに実行して graph_causality に保存する。

    - 直近 GRANGER_WINDOW 営業日のリターンを使用
    - joblib で並列化 (n_jobs=-1 で全コア使用)
    - p_value < GRANGER_P_THRESHOLD のペアのみ保存

    Args:
        db_path: SQLite ファイルパス
        calc_date: 'YYYY-MM-DD'
        n_jobs: joblib の並列数 (-1 = 全コア)
    Returns:
        保存した因果エッジ数
    """
    conn = sqlite3.connect(db_path)
    df = pd.read_sql(
        f"""
        SELECT code, date, return_rate FROM daily_prices
        WHERE date <= '{calc_date}' AND return_rate IS NOT NULL
        ORDER BY date
        """,
        conn,
    )
    conn.close()

    if df.empty:
        return 0

    dates = sorted(df["date"].unique())[-GRANGER_WINDOW:]
    df = df[df["date"].isin(dates)]

    # 全銘柄揃っている行だけを使う (欠損は除外)
    pivot = df.pivot(index="date", columns="code", values="return_rate").dropna(axis=1)
    codes = list(pivot.columns)

    if len(codes) < 2:
        logger.warning("グレンジャー検定: 銘柄数が不足しています")
        return 0

    # 直近出来高上位 MAX_GRANGER_STOCKS 銘柄に絞る (タイムアウト防止)
    if len(codes) > MAX_GRANGER_STOCKS:
        conn2 = sqlite3.connect(db_path)
        vol_df = pd.read_sql(
            f"""
            SELECT code, SUM(volume) AS total_vol FROM daily_prices
            WHERE date IN ({",".join(f"'{d}'" for d in dates)}) AND code IN ({",".join(f"'{c}'" for c in codes)})
            GROUP BY code ORDER BY total_vol DESC LIMIT {MAX_GRANGER_STOCKS}
            """,
            conn2,
        )
        conn2.close()
        top_codes = set(vol_df["code"].tolist())
        codes = [c for c in codes if c in top_codes]
        pivot = pivot[codes]
        logger.info(f"グレンジャー検定: {MAX_GRANGER_STOCKS} 銘柄に絞り込み")

    # 全ペアを生成
    pairs = [
        (codes[i], codes[j])
        for i in range(len(codes))
        for j in range(i + 1, len(codes))
    ]
    logger.info(f"グレンジャー検定: {len(pairs)} ペアを処理中 (n_jobs={n_jobs})")

    results_nested = Parallel(n_jobs=n_jobs)(
        delayed(_granger_one_pair)(
            pivot[a].values, pivot[b].values, a, b, calc_date
        )
        for a, b in pairs
    )

    rows = [r for sublist in results_nested for r in sublist]

    if not rows:
        logger.info("グレンジャー検定: 有意なペアなし")
        return 0

    conn = sqlite3.connect(db_path)
    conn.executemany(
        """
        INSERT OR REPLACE INTO graph_causality
            (source, target, lag_days, p_value, f_stat, period, calc_date)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    conn.commit()
    conn.close()

    logger.info(f"グレンジャー因果エッジを保存: {len(rows)} 件")
    return len(rows)


# ─────────────────────────────────────────────────────────────────────────────
# リードラグ分析 (クロス相関)
# ─────────────────────────────────────────────────────────────────────────────

def _cross_corr_best_lag(
    a: np.ndarray,
    b: np.ndarray,
    max_lag: int,
) -> tuple[int, float]:
    """
    標準化されたクロス相関を計算し、lag ≠ 0 の中で絶対値最大のラグと係数を返す。

    正のラグ (lag > 0) は「a が b に lag 日先行する」を意味する。
    実装: corr[k] = E[a(t) * b(t+k)] / (std_a * std_b * n)
    """
    n = len(a)
    a_norm = (a - a.mean()) / (a.std() + 1e-10)
    b_norm = (b - b.mean()) / (b.std() + 1e-10)

    # np.correlate(b_norm, a_norm) にすることで、正のラグが「a が b に先行」を意味する
    # c[n-1+lag] = sum_n b[n+lag]*a[n] = max when b[t] = a[t-lag] (a leads by lag)
    full_corr = np.correlate(b_norm, a_norm, mode="full") / n
    center = n - 1

    best_lag, best_corr = 0, 0.0
    for lag in range(-max_lag, max_lag + 1):
        if lag == 0:
            continue
        idx = center + lag
        if 0 <= idx < len(full_corr):
            c = full_corr[idx]
            if abs(c) > abs(best_corr):
                best_lag, best_corr = lag, c

    return best_lag, best_corr


def run_lead_lag(db_path: str, calc_date: str) -> int:
    """
    クロス相関によるリードラグ分析を実行して graph_causality (LEADS) に保存する。

    - ラグ範囲: -LEAD_LAG_MAX ~ +LEAD_LAG_MAX (0 除く)
    - 最大クロス相関のラグが 0 でなく、|cross_corr| > LEAD_LAG_THRESHOLD のペアを保存
    - 正ラグ: source が target より lag_days 先行する
    - 直近 GRANGER_WINDOW 日のデータを使用

    Returns:
        保存したリードラグエッジ数
    """
    conn = sqlite3.connect(db_path)
    df = pd.read_sql(
        f"""
        SELECT code, date, return_rate FROM daily_prices
        WHERE date <= '{calc_date}' AND return_rate IS NOT NULL
        ORDER BY date
        """,
        conn,
    )
    conn.close()

    if df.empty:
        return 0

    dates = sorted(df["date"].unique())[-GRANGER_WINDOW:]
    df = df[df["date"].isin(dates)]

    pivot = df.pivot(index="date", columns="code", values="return_rate").dropna(axis=1)
    codes = list(pivot.columns)

    if len(codes) < 2:
        return 0

    # 直近出来高上位 MAX_GRANGER_STOCKS 銘柄に絞る (タイムアウト防止)
    if len(codes) > MAX_GRANGER_STOCKS:
        conn2 = sqlite3.connect(db_path)
        vol_df = pd.read_sql(
            f"""
            SELECT code, SUM(volume) AS total_vol FROM daily_prices
            WHERE date IN ({",".join(f"'{d}'" for d in dates)}) AND code IN ({",".join(f"'{c}'" for c in codes)})
            GROUP BY code ORDER BY total_vol DESC LIMIT {MAX_GRANGER_STOCKS}
            """,
            conn2,
        )
        conn2.close()
        top_codes = set(vol_df["code"].tolist())
        codes = [c for c in codes if c in top_codes]
        pivot = pivot[codes]
        logger.info(f"リードラグ: {MAX_GRANGER_STOCKS} 銘柄に絞り込み")

    rows = []
    for i in range(len(codes)):
        for j in range(i + 1, len(codes)):
            a, b = codes[i], codes[j]
            lag, corr = _cross_corr_best_lag(
                pivot[a].values, pivot[b].values, LEAD_LAG_MAX
            )
            if abs(corr) < LEAD_LAG_THRESHOLD:
                continue

            # lag > 0: a が b より lag 日先行
            # lag < 0: b が a より |lag| 日先行
            if lag > 0:
                source, target, actual_lag = a, b, int(lag)
            else:
                source, target, actual_lag = b, a, int(-lag)

            rows.append(
                (source, target, actual_lag, float(corr), "60d", calc_date)
            )

    if not rows:
        logger.info("リードラグ: 有意なペアなし")
        return 0

    conn = sqlite3.connect(db_path)
    # graph_causality テーブルに lead_lag タイプとして書き込む
    # (KùzuDB の LEADS エッジへの投入は graph.py で実施)
    conn.executemany(
        """
        INSERT OR REPLACE INTO graph_causality
            (source, target, lag_days, p_value, f_stat, period, calc_date)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (source, target, lag_days, 1.0 - abs(corr), abs(corr), period, calc_date)
            for source, target, lag_days, corr, period, calc_date in rows
        ],
    )
    conn.commit()
    conn.close()

    logger.info(f"リードラグエッジを保存: {len(rows)} 件")
    return len(rows)


# ─────────────────────────────────────────────────────────────────────────────
# セクター間資金フロー推定
# ─────────────────────────────────────────────────────────────────────────────

def run_fund_flow(db_path: str, target_date: str) -> int:
    """
    セクター別の出来高変化率と騰落率からセクター間資金フローを推定し、
    graph_fund_flows テーブルに保存する。

    判定ロジック:
      - 出来高変化率 < -10% かつ avg_return < -0.5% → outflow
      - 出来高変化率 > +10% かつ avg_return > +0.5% → inflow
    outflow セクター → inflow セクターへの FUND_FLOW エッジを作成。

    Args:
        db_path: SQLite ファイルパス
        target_date: 'YYYY-MM-DD'
    Returns:
        保存したフローエッジ数
    """
    conn = sqlite3.connect(db_path)

    # 当日のセクター別集計
    today_df = pd.read_sql(
        f"""
        SELECT s.sector,
               AVG(dp.return_rate) AS avg_return,
               SUM(dp.volume)      AS total_volume
        FROM daily_prices dp
        JOIN stocks s ON dp.code = s.code
        WHERE dp.date = '{target_date}'
          AND dp.return_rate IS NOT NULL
        GROUP BY s.sector
        """,
        conn,
    )

    if today_df.empty:
        conn.close()
        return 0

    # ベースライン: 直近 FUND_FLOW_WINDOW 日の1日あたりセクター合計出来高の平均
    # (today_df の SUM(volume) と比較するため、同じ集計単位を使う)
    baseline_df = pd.read_sql(
        f"""
        SELECT sector, AVG(daily_total) AS avg_volume_base
        FROM (
            SELECT s.sector, dp.date, SUM(dp.volume) AS daily_total
            FROM daily_prices dp
            JOIN stocks s ON dp.code = s.code
            WHERE dp.date < '{target_date}'
              AND dp.date IN (
                  SELECT DISTINCT date FROM daily_prices
                  WHERE date < '{target_date}'
                  ORDER BY date DESC
                  LIMIT {FUND_FLOW_WINDOW}
              )
            GROUP BY s.sector, dp.date
        )
        GROUP BY sector
        """,
        conn,
    )
    conn.close()

    if baseline_df.empty:
        logger.info("資金フロー: ベースラインデータ不足")
        return 0

    merged = today_df.merge(baseline_df, on="sector", how="inner")
    merged["volume_delta_pct"] = (
        (merged["total_volume"] - merged["avg_volume_base"])
        / merged["avg_volume_base"].replace(0, np.nan)
    )

    outflow = merged[
        (merged["volume_delta_pct"] < -0.10) & (merged["avg_return"] < -0.005)
    ]["sector"].tolist()

    inflow = merged[
        (merged["volume_delta_pct"] > 0.10) & (merged["avg_return"] > 0.005)
    ]["sector"].tolist()

    if not outflow or not inflow:
        logger.info(
            f"資金フロー: outflow={len(outflow)} セクター, inflow={len(inflow)} セクター"
        )
        return 0

    # outflow × inflow のすべての組み合わせでエッジを作成
    rows = []
    for src in outflow:
        for dst in inflow:
            if src == dst:
                continue
            src_row = merged[merged["sector"] == src].iloc[0]
            dst_row = merged[merged["sector"] == dst].iloc[0]
            return_spread = float(dst_row["avg_return"] - src_row["avg_return"])
            volume_delta = float(src_row["volume_delta_pct"])
            rows.append(
                (src, dst, float(volume_delta), return_spread, target_date)
            )

    if not rows:
        return 0

    conn = sqlite3.connect(db_path)
    conn.executemany(
        """
        INSERT OR REPLACE INTO graph_fund_flows
            (sector_from, sector_to, volume_delta, return_spread, date)
        VALUES (?, ?, ?, ?, ?)
        """,
        rows,
    )
    conn.commit()
    conn.close()

    logger.info(f"資金フローエッジを保存: {len(rows)} 件")
    return len(rows)


# ─────────────────────────────────────────────────────────────────────────────
# マーケットレジーム判定
# ─────────────────────────────────────────────────────────────────────────────

def determine_regime(db_path: str, target_date: str) -> str:
    """
    日経225 (近似: 全銘柄等加重平均リターン) の直近ボラティリティとリターンで
    マーケットレジームを判定し、daily_summary を更新する。

    判定ロジック:
      - 当日リターン > 0 かつ 直近5日ボラ < 直近20日ボラ → 'risk_on'
      - 当日リターン < 0 かつ 直近5日ボラ > 直近20日ボラ → 'risk_off'
      - それ以外                                          → 'neutral'

    Args:
        db_path: SQLite ファイルパス
        target_date: 'YYYY-MM-DD'
    Returns:
        レジーム文字列 ('risk_on' | 'risk_off' | 'neutral')
    """
    conn = sqlite3.connect(db_path)
    df = pd.read_sql(
        f"""
        SELECT date, AVG(return_rate) AS avg_return
        FROM daily_prices
        WHERE date <= '{target_date}' AND return_rate IS NOT NULL
        GROUP BY date
        ORDER BY date DESC
        LIMIT {REGIME_LONG_WINDOW + 1}
        """,
        conn,
    )
    conn.close()

    if df.empty or len(df) < REGIME_SHORT_WINDOW:
        regime = "neutral"
    else:
        df = df.sort_values("date")
        returns = df["avg_return"].values

        today_return = float(returns[-1])
        short_vol = float(np.std(returns[-REGIME_SHORT_WINDOW:]))
        long_vol = float(np.std(returns[-REGIME_LONG_WINDOW:]) if len(returns) >= REGIME_LONG_WINDOW else short_vol)

        if today_return > 0 and short_vol < long_vol:
            regime = "risk_on"
        elif today_return < 0 and short_vol > long_vol:
            regime = "risk_off"
        else:
            regime = "neutral"

    # daily_summary に保存
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        INSERT INTO daily_summary (date, regime, nikkei_return)
        VALUES (?, ?, ?)
        ON CONFLICT(date) DO UPDATE SET
            regime = excluded.regime,
            nikkei_return = COALESCE(excluded.nikkei_return, nikkei_return)
        """,
        (
            target_date,
            regime,
            float(df["avg_return"].iloc[-1]) if not df.empty else None,
        ),
    )
    conn.commit()
    conn.close()

    logger.info(f"レジーム判定: {target_date} → {regime}")
    return regime


# ─────────────────────────────────────────────────────────────────────────────
# 市場圧力指標 (Phase 16)
# ─────────────────────────────────────────────────────────────────────────────

def _calc_pl_zone(pl_ratio: float) -> str:
    """
    評価損益率から市場圧力ゾーンを返す。

    +15% 以上  → 'ceiling'   (天井警戒)
    +5% 以上   → 'overheat'  (過熱)
    0% 以上    → 'neutral'   (中立)
    -10% 以上  → 'weak'      (弱含み)
    -15% 以上  → 'sellin'    (投げ売り圏)
    -15% 未満  → 'bottom'    (大底圏)
    """
    if pl_ratio >= 0.15:
        return "ceiling"
    if pl_ratio >= 0.05:
        return "overheat"
    if pl_ratio >= 0.0:
        return "neutral"
    if pl_ratio >= -0.10:
        return "weak"
    if pl_ratio >= -0.15:
        return "sellin"
    return "bottom"


def run_market_pressure(db_path: str, target_date: str) -> int:
    """
    市場レベルの信用圧力指標を計算して margin_trading_weekly / market_pressure_daily に保存する。

    処理:
      1. 直近の week_date を margin_balances から取得
      2. SUM(margin_buy), SUM(margin_sell) を集計 → margin_trading_weekly に保存
      3. pl_ratio_proxy = 直近4週 daily_prices の return_rate を margin_buy で加重平均 × 4
      4. buy_growth_4w = (現在 - 4週前) / 4週前
      5. margin_ratio_trend = 直近4エントリの margin_ratio 傾き (linregress)
      6. market_pressure_daily に INSERT OR REPLACE

    Args:
        db_path: SQLite ファイルパス
        target_date: 'YYYY-MM-DD'
    Returns:
        書き込んだ行数 (1 = 成功、0 = データ不足でスキップ)
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    try:
        # 直近の信用残高週次データを取得
        latest_week = conn.execute(
            "SELECT MAX(week_date) FROM margin_balances WHERE week_date <= ?",
            (target_date,),
        ).fetchone()[0]

        if not latest_week:
            logger.info("run_market_pressure: margin_balances データなし — スキップ")
            return 0

        # 市場合計集計
        agg = conn.execute(
            """
            SELECT SUM(margin_buy)  AS total_buy,
                   SUM(margin_sell) AS total_sell
            FROM margin_balances
            WHERE week_date = ?
            """,
            (latest_week,),
        ).fetchone()

        total_buy = float(agg["total_buy"] or 0)
        total_sell = float(agg["total_sell"] or 0)
        margin_ratio = total_buy / total_sell if total_sell > 0 else None

        # pl_ratio_proxy: 直近4週の日次リターンを margin_buy で加重平均 × 4
        # margin_buy は週次なので直近週のデータを代用
        pl_ratio_proxy = _calc_pl_ratio_proxy(conn, latest_week, target_date)

        # margin_trading_weekly に保存
        conn.execute(
            """
            INSERT OR REPLACE INTO margin_trading_weekly
                (week_date, market_code, margin_buy_balance, margin_sell_balance,
                 margin_ratio, pl_ratio_proxy)
            VALUES (?, 'ALL', ?, ?, ?, ?)
            """,
            (latest_week, total_buy, total_sell, margin_ratio, pl_ratio_proxy),
        )

        # 4週前の buy_balance を取得
        prev_4w = conn.execute(
            """
            SELECT margin_buy_balance FROM margin_trading_weekly
            WHERE market_code = 'ALL' AND week_date < ?
            ORDER BY week_date DESC
            LIMIT 1
            OFFSET 3
            """,
            (latest_week,),
        ).fetchone()

        buy_growth_4w: Optional[float] = None
        if prev_4w and prev_4w[0] and float(prev_4w[0]) != 0:
            buy_growth_4w = (total_buy - float(prev_4w[0])) / float(prev_4w[0])

        # margin_ratio_trend: 直近4エントリの傾き (最低2件あれば計算)
        recent_ratios = conn.execute(
            """
            SELECT margin_ratio FROM margin_trading_weekly
            WHERE market_code = 'ALL' AND margin_ratio IS NOT NULL
            ORDER BY week_date DESC
            LIMIT 4
            """,
        ).fetchall()

        margin_ratio_trend: Optional[float] = None
        if len(recent_ratios) >= 2:
            ys = [float(r[0]) for r in reversed(recent_ratios)]
            xs = list(range(len(ys)))
            slope, *_ = linregress(xs, ys)
            margin_ratio_trend = float(slope)

        # pl_zone と signal_flags
        pl_zone = _calc_pl_zone(pl_ratio_proxy) if pl_ratio_proxy is not None else "neutral"
        # 信用過熱: 過熱/天井ゾーン かつ 信用倍率が高水準 (>= 6.0)
        credit_overheating = (
            pl_zone in ("ceiling", "overheat")
            and margin_ratio is not None
            and margin_ratio >= 6.0
        )
        signal_flags = json.dumps({"credit_overheating": credit_overheating})

        # market_pressure_daily に保存 (週次値を当日に伝播)
        conn.execute(
            """
            INSERT OR REPLACE INTO market_pressure_daily
                (date, pl_ratio, pl_zone, buy_growth_4w, margin_ratio,
                 margin_ratio_trend, signal_flags)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                target_date,
                pl_ratio_proxy,
                pl_zone,
                buy_growth_4w,
                margin_ratio,
                margin_ratio_trend,
                signal_flags,
            ),
        )
        conn.commit()

    finally:
        conn.close()

    logger.info(f"市場圧力指標を保存: {target_date}, pl_zone={pl_zone}")
    return 1


def _backfill_market_pressure(db_path: str) -> int:
    """
    margin_balances に存在するが market_pressure_daily にない週のデータをバックフィルする。
    初回導入時や長期間バッチが停止していた場合に履歴データを補完する。

    Returns:
        補完した行数
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        missing_weeks = conn.execute(
            """
            SELECT DISTINCT mb.week_date
            FROM margin_balances mb
            WHERE NOT EXISTS (
                SELECT 1 FROM market_pressure_daily mpd
                WHERE mpd.date = mb.week_date
            )
            ORDER BY mb.week_date
            """
        ).fetchall()
    finally:
        conn.close()

    if not missing_weeks:
        return 0

    filled = 0
    for row in missing_weeks:
        filled += run_market_pressure(db_path, row["week_date"])

    if filled:
        logger.info(f"市場圧力バックフィル: {filled} 週分補完")
    return filled


def _calc_pl_ratio_proxy(
    conn: sqlite3.Connection,
    latest_week: str,
    target_date: str,
) -> Optional[float]:
    """
    信用評価損益率の近似値を返す。

    計算方法:
      - 最新の信用残高報告日 (latest_week) 以降の累積リターンを margin_buy で加重平均
      - 「信用残高が公表された時点から今日まで、含み損益はどれだけか」を近似
      - margin_buy が大きい銘柄ほど市場全体の含み損益に影響するため加重平均で算出
      - 報告日直後 (当日) は window が 0 のため、フォールバックとして直近20営業日窓を使用

    Args:
        conn: SQLite 接続
        latest_week: 最新の信用残高週次日付 ('YYYY-MM-DD')
        target_date: 集計対象日 ('YYYY-MM-DD')

    Returns:
        評価損益率 (小数、例: 0.05 = +5%) または None (データ不足)
    """
    # 一次計算: latest_week から target_date までの累積リターン
    rows = conn.execute(
        """
        SELECT mb.code,
               mb.margin_buy,
               SUM(dp.return_rate) AS cum_return,
               COUNT(dp.date)      AS n_days
        FROM margin_balances mb
        JOIN daily_prices dp ON mb.code = dp.code
        WHERE mb.week_date = ?
          AND dp.date > ?
          AND dp.date <= ?
          AND dp.return_rate IS NOT NULL
          AND mb.margin_buy > 0
        GROUP BY mb.code
        """,
        (latest_week, latest_week, target_date),
    ).fetchall()

    # latest_week と target_date が同日、またはデータが不足している場合は
    # フォールバック: 直近20営業日窓 (従来の計算方式)
    if not rows or sum(r[3] for r in rows) == 0:
        cutoff = conn.execute(
            """
            SELECT date FROM (
                SELECT DISTINCT date FROM daily_prices WHERE date <= ?
            ) ORDER BY date DESC
            LIMIT 1
            OFFSET 19
            """,
            (target_date,),
        ).fetchone()
        if not cutoff:
            return None
        cutoff_date = cutoff[0]
        rows = conn.execute(
            """
            SELECT mb.code,
                   mb.margin_buy,
                   SUM(dp.return_rate) AS cum_return,
                   COUNT(dp.date)      AS n_days
            FROM margin_balances mb
            JOIN daily_prices dp ON mb.code = dp.code
            WHERE mb.week_date = ?
              AND dp.date > ?
              AND dp.date <= ?
              AND dp.return_rate IS NOT NULL
              AND mb.margin_buy > 0
            GROUP BY mb.code
            HAVING COUNT(dp.date) >= 5
            """,
            (latest_week, cutoff_date, target_date),
        ).fetchall()
        if not rows:
            return None

    total_weight = sum(float(r[1]) for r in rows)
    if total_weight == 0:
        return None

    weighted_sum = sum(float(r[1]) * float(r[2]) for r in rows)
    return weighted_sum / total_weight


# ─────────────────────────────────────────────────────────────────────────────
# エントリポイント
# ─────────────────────────────────────────────────────────────────────────────

def run_all(
    db_path: str,
    target_date: Optional[str] = None,
    n_jobs: int = -1,
) -> None:
    """
    全統計分析を実行する。

    実行順序:
      1. マーケットレジーム判定
      2. グレンジャー因果検定
      3. リードラグ分析
      4. セクター間資金フロー推定

    Args:
        db_path: SQLite ファイルパス
        target_date: 'YYYY-MM-DD'。省略時は今日
        n_jobs: グレンジャー検定の並列数
    """
    if target_date is None:
        target_date = date.today().isoformat()

    logger.info(f"=== run_all 開始: {target_date} ===")

    regime = determine_regime(db_path, target_date)
    logger.info(f"レジーム: {regime}")

    n_granger = run_granger(db_path, target_date, n_jobs=n_jobs)
    logger.info(f"グレンジャー因果: {n_granger} 件")

    n_lead_lag = run_lead_lag(db_path, target_date)
    logger.info(f"リードラグ: {n_lead_lag} 件")

    n_flow = run_fund_flow(db_path, target_date)
    logger.info(f"資金フロー: {n_flow} 件")

    n_pressure = run_market_pressure(db_path, target_date)
    logger.info(f"市場圧力: {n_pressure} 件")

    # market_pressure_daily が少ない場合に過去週をバックフィル
    _backfill_market_pressure(db_path)

    logger.info("=== run_all 完了 ===")
