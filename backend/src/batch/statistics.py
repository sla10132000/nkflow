"""統計分析モジュール: グレンジャー因果・リードラグ・資金フロー・レジーム判定"""
import logging
import sqlite3
from datetime import date
from typing import Optional

import numpy as np
import pandas as pd
from joblib import Parallel, delayed
from statsmodels.tsa.stattools import grangercausalitytests

from src.config import GRANGER_MAX_LAG, GRANGER_P_THRESHOLD

logger = logging.getLogger(__name__)

# 分析ウィンドウ
GRANGER_WINDOW = 60     # グレンジャー検定に使う直近営業日数
LEAD_LAG_MAX = 5        # クロス相関の最大ラグ数
LEAD_LAG_THRESHOLD = 0.3  # クロス相関の最低閾値
FUND_FLOW_WINDOW = 20   # 資金フローの比較ベースライン日数
REGIME_SHORT_WINDOW = 5  # レジーム判定: 直近ボラ
REGIME_LONG_WINDOW = 20  # レジーム判定: 比較ベースボラ


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
                (source, target, best_lag, best_p, best_f, "60d", calc_date)
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
                source, target, actual_lag = a, b, lag
            else:
                source, target, actual_lag = b, a, -lag

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

    # ベースライン: 直近 FUND_FLOW_WINDOW 日の平均出来高
    baseline_df = pd.read_sql(
        f"""
        SELECT s.sector,
               AVG(dp.volume) AS avg_volume_base
        FROM daily_prices dp
        JOIN stocks s ON dp.code = s.code
        WHERE dp.date < '{target_date}'
          AND dp.date IN (
              SELECT DISTINCT date FROM daily_prices
              WHERE date < '{target_date}'
              ORDER BY date DESC
              LIMIT {FUND_FLOW_WINDOW}
          )
        GROUP BY s.sector
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

    logger.info("=== run_all 完了 ===")
