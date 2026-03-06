"""
Phase 14: バックテストエンジン

signals テーブルのシグナルを用いてシミュレーションを行い、
backtest_runs / backtest_trades / backtest_results テーブルに結果を保存する。

ルール:
  - エントリー: シグナル発生日の翌営業日の open 価格
  - イグジット: エントリーから holding_days 営業日後の close 価格
  - 勝敗判定:
      bullish シグナル → return_rate > 0 で hit
      bearish シグナル → return_rate < 0 で hit
"""
import logging
import math
import sqlite3
from datetime import date
from typing import Optional

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# 内部ユーティリティ
# ─────────────────────────────────────────────────────────────────────────────

def _trading_days(conn: sqlite3.Connection) -> list[str]:
    """daily_prices に存在する取引日一覧を昇順で返す (重複排除)。"""
    rows = conn.execute(
        "SELECT DISTINCT date FROM daily_prices ORDER BY date"
    ).fetchall()
    return [r[0] for r in rows]


def _nth_trading_day_after(trading_days: list[str], ref_date: str, n: int) -> Optional[str]:
    """
    ref_date より後の n 番目の取引日を返す。
    存在しない場合は None。
    """
    try:
        idx = trading_days.index(ref_date)
    except ValueError:
        # ref_date が取引日でなければ、それ以降の最初の取引日から数える
        later = [d for d in trading_days if d > ref_date]
        if not later:
            return None
        idx = trading_days.index(later[0]) - 1

    target_idx = idx + n
    if target_idx >= len(trading_days):
        return None
    return trading_days[target_idx]


def _price(conn: sqlite3.Connection, code: str, date_str: str, col: str) -> Optional[float]:
    """指定銘柄・日付の open または close を返す。"""
    row = conn.execute(
        f"SELECT {col} FROM daily_prices WHERE code = ? AND date = ?",
        (code, date_str),
    ).fetchone()
    if row is None or row[0] is None:
        return None
    return float(row[0])


def _calc_max_drawdown(returns: list[float]) -> float:
    """
    累積リターン系列から最大ドローダウンを計算する。
    returns: 各トレードのリターン (例: 0.02, -0.01, ...)
    """
    if not returns:
        return 0.0
    peak = 0.0
    cumulative = 0.0
    max_dd = 0.0
    for r in returns:
        cumulative += r
        if cumulative > peak:
            peak = cumulative
        dd = peak - cumulative
        if dd > max_dd:
            max_dd = dd
    return max_dd


def _calc_sharpe(returns: list[float], risk_free: float = 0.0) -> Optional[float]:
    """
    年次化シャープレシオを計算する。
    returns: 各トレードのリターン
    risk_free: 無リスク金利 (デフォルト 0)
    """
    n = len(returns)
    if n < 2:
        return None
    mean = sum(returns) / n
    variance = sum((r - mean) ** 2 for r in returns) / (n - 1)
    std = math.sqrt(variance)
    if std == 0:
        return None
    # 年間 252 営業日を仮定してスケール
    return round((mean - risk_free) / std * math.sqrt(252), 4)


# ─────────────────────────────────────────────────────────────────────────────
# トレードシミュレーション
# ─────────────────────────────────────────────────────────────────────────────

def simulate_trades(
    conn: sqlite3.Connection,
    run_id: int,
    signal_type: Optional[str],
    from_date: str,
    to_date: str,
    holding_days: int,
    direction_filter: Optional[str],
    min_confidence: float,
) -> list[dict]:
    """
    シグナルを取得してトレードをシミュレートし、backtest_trades に保存する。

    Returns:
        トレード dict のリスト (return_rate が None のものは除く)
    """
    # シグナル取得クエリ
    query = """
        SELECT id, date, code, direction, confidence
        FROM signals
        WHERE code IS NOT NULL
          AND date >= ? AND date <= ?
          AND confidence >= ?
    """
    params: list = [from_date, to_date, min_confidence]

    if signal_type:
        query += " AND signal_type = ?"
        params.append(signal_type)
    if direction_filter:
        query += " AND direction = ?"
        params.append(direction_filter)

    query += " ORDER BY date"
    signal_rows = conn.execute(query, params).fetchall()

    if not signal_rows:
        logger.info("simulate_trades: 対象シグナルなし")
        return []

    tdays = _trading_days(conn)
    trades = []

    for sig_id, sig_date, code, direction, confidence in signal_rows:
        # エントリー: シグナル翌営業日の open
        entry_date = _nth_trading_day_after(tdays, sig_date, 1)
        if entry_date is None:
            continue
        entry_price = _price(conn, code, entry_date, "open")
        if entry_price is None:
            continue

        # イグジット: エントリーから holding_days 後の close
        exit_date = _nth_trading_day_after(tdays, entry_date, holding_days)
        exit_price = _price(conn, code, exit_date, "close") if exit_date else None

        return_rate: Optional[float] = None
        if exit_price is not None and entry_price > 0:
            raw = (exit_price - entry_price) / entry_price
            # bearish シグナルの場合は空売り想定なのでリターンを反転
            return_rate = round(-raw if direction == "bearish" else raw, 6)

        trades.append({
            "run_id": run_id,
            "signal_id": sig_id,
            "code": code,
            "signal_date": sig_date,
            "entry_date": entry_date,
            "exit_date": exit_date,
            "entry_price": entry_price,
            "exit_price": exit_price,
            "return_rate": return_rate,
            "direction": direction,
        })

    if trades:
        conn.executemany(
            """
            INSERT INTO backtest_trades
                (run_id, signal_id, code, signal_date, entry_date, exit_date,
                 entry_price, exit_price, return_rate, direction)
            VALUES (:run_id, :signal_id, :code, :signal_date, :entry_date, :exit_date,
                    :entry_price, :exit_price, :return_rate, :direction)
            """,
            trades,
        )
        conn.commit()

    logger.info(f"simulate_trades: {len(trades)} 件シミュレーション")
    return trades


# ─────────────────────────────────────────────────────────────────────────────
# 集計
# ─────────────────────────────────────────────────────────────────────────────

def calc_metrics(
    conn: sqlite3.Connection,
    run_id: int,
) -> dict:
    """
    backtest_trades からメトリクスを計算して backtest_results に保存する。

    Returns:
        集計結果 dict
    """
    rows = conn.execute(
        "SELECT return_rate FROM backtest_trades WHERE run_id = ? AND return_rate IS NOT NULL",
        (run_id,),
    ).fetchall()

    returns = [float(r[0]) for r in rows]
    total = len(returns)

    if total == 0:
        result = {
            "run_id": run_id,
            "total_trades": 0,
            "winning_trades": 0,
            "win_rate": 0.0,
            "avg_return": 0.0,
            "total_return": 0.0,
            "max_drawdown": 0.0,
            "sharpe_ratio": None,
            "calc_date": date.today().isoformat(),
        }
    else:
        winning = sum(1 for r in returns if r > 0)
        avg_return = round(sum(returns) / total, 6)
        total_return = round(sum(returns), 6)
        max_dd = round(_calc_max_drawdown(returns), 6)
        sharpe = _calc_sharpe(returns)

        result = {
            "run_id": run_id,
            "total_trades": total,
            "winning_trades": winning,
            "win_rate": round(winning / total, 4),
            "avg_return": avg_return,
            "total_return": total_return,
            "max_drawdown": max_dd,
            "sharpe_ratio": sharpe,
            "calc_date": date.today().isoformat(),
        }

    conn.execute(
        """
        INSERT OR REPLACE INTO backtest_results
            (run_id, total_trades, winning_trades, win_rate, avg_return,
             total_return, max_drawdown, sharpe_ratio, calc_date)
        VALUES (:run_id, :total_trades, :winning_trades, :win_rate, :avg_return,
                :total_return, :max_drawdown, :sharpe_ratio, :calc_date)
        """,
        result,
    )
    conn.commit()
    logger.info(
        f"calc_metrics: run_id={run_id} trades={result['total_trades']} "
        f"win_rate={result['win_rate']:.1%} avg_return={result['avg_return']:.4%}"
    )
    return result


# ─────────────────────────────────────────────────────────────────────────────
# エントリポイント
# ─────────────────────────────────────────────────────────────────────────────

def run_backtest(
    db_path: str,
    name: str,
    from_date: str,
    to_date: str,
    holding_days: int = 5,
    signal_type: Optional[str] = None,
    direction_filter: Optional[str] = None,
    min_confidence: float = 0.0,
) -> dict:
    """
    バックテストを実行して結果を返す。

    Args:
        db_path:          SQLite ファイルパス
        name:             バックテスト名 (任意の識別名)
        from_date:        シグナル対象開始日 'YYYY-MM-DD'
        to_date:          シグナル対象終了日 'YYYY-MM-DD'
        holding_days:     保有営業日数 (デフォルト 5)
        signal_type:      フィルタするシグナルタイプ (None = 全種)
        direction_filter: 'bullish' / 'bearish' / None (= 両方)
        min_confidence:   最低 confidence 閾値 (0.0 〜 1.0)

    Returns:
        {"run_id": int, "metrics": dict}
    """
    conn = sqlite3.connect(db_path)
    try:
        # 実行設定を記録
        cur = conn.execute(
            """
            INSERT INTO backtest_runs
                (name, signal_type, from_date, to_date, holding_days,
                 direction_filter, min_confidence)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (name, signal_type, from_date, to_date, holding_days,
             direction_filter, min_confidence),
        )
        conn.commit()
        run_id = cur.lastrowid

        logger.info(
            f"=== バックテスト開始: run_id={run_id} name='{name}' "
            f"period={from_date}〜{to_date} holding={holding_days}d ==="
        )

        # シミュレーション
        simulate_trades(
            conn, run_id, signal_type, from_date, to_date,
            holding_days, direction_filter, min_confidence,
        )

        # 集計
        metrics = calc_metrics(conn, run_id)

    finally:
        conn.close()

    logger.info(f"=== バックテスト完了: run_id={run_id} ===")
    return {"run_id": run_id, "metrics": metrics}
