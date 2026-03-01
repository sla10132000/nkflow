"""
Phase 11: シグナル的中率の自動追跡モジュール

バッチ実行時に評価期限が来たシグナルを判定し、
タイプ別の的中率を signal_accuracy テーブルに集計する。

評価ホライズン: 5日 / 10日 / 20日 (取引日ベース)
判定基準:
  bullish: 累積リターン >  0.1% → hit  /  < -0.1% → miss  / それ以外 → tie
  bearish: 累積リターン < -0.1% → hit  /  >  0.1% → miss  / それ以外 → tie

code が NULL のシグナル (セクターシグナル等) は評価対象外。
"""
import logging
import sqlite3
from datetime import date
from typing import Optional

logger = logging.getLogger(__name__)

EVAL_HORIZONS = [5, 10, 20]
HIT_THRESHOLD = 0.001  # 0.1% 以上の変動で勝敗を判定


# ─────────────────────────────────────────────────────────────────────────────
# 内部ユーティリティ
# ─────────────────────────────────────────────────────────────────────────────

def _nth_trading_date(conn: sqlite3.Connection, after_date: str, n: int) -> Optional[str]:
    """after_date の翌取引日から数えて n 番目の取引日を返す。データ不足なら None。"""
    row = conn.execute(
        """
        SELECT date FROM (
            SELECT DISTINCT date FROM daily_prices
            WHERE date > ?
            ORDER BY date ASC
            LIMIT ?
        ) ORDER BY date ASC LIMIT 1 OFFSET ?
        """,
        (after_date, n, n - 1),
    ).fetchone()
    return row[0] if row else None


def _cumulative_return(
    conn: sqlite3.Connection, code: str, after_date: str, n: int
) -> Optional[float]:
    """after_date 翌取引日から n 取引日分の cumulative return を返す。データ不足なら None。"""
    rows = conn.execute(
        """
        SELECT return_rate FROM daily_prices
        WHERE code = ? AND date > ? AND return_rate IS NOT NULL
        ORDER BY date ASC
        LIMIT ?
        """,
        (code, after_date, n),
    ).fetchall()
    if len(rows) < n:
        return None
    return sum(r[0] for r in rows)


def _judge(direction: str, cumret: float) -> str:
    if direction == "bullish":
        if cumret > HIT_THRESHOLD:
            return "hit"
        elif cumret < -HIT_THRESHOLD:
            return "miss"
        return "tie"
    else:  # bearish
        if cumret < -HIT_THRESHOLD:
            return "hit"
        elif cumret > HIT_THRESHOLD:
            return "miss"
        return "tie"


# ─────────────────────────────────────────────────────────────────────────────
# メイン関数
# ─────────────────────────────────────────────────────────────────────────────

def evaluate_pending_signals(db_path: str, eval_date: Optional[str] = None) -> int:
    """
    eval_date 時点で評価期限が来た未評価シグナルを判定し、
    signal_results テーブルに記録する。

    Args:
        db_path:   SQLite ファイルパス
        eval_date: 評価日 (YYYY-MM-DD)。省略時は今日。
    Returns:
        新たに記録した (signal_id, horizon) ペア数
    """
    if eval_date is None:
        eval_date = date.today().isoformat()

    conn = sqlite3.connect(db_path)
    total_recorded = 0

    try:
        for horizon in EVAL_HORIZONS:
            # eval_date から遡って horizon 取引日分のデータを取得
            # → horizon 日分揃っている場合のみ、最も古い日付をカットオフとして使用
            cutoff_rows = conn.execute(
                """
                SELECT DISTINCT date FROM daily_prices
                WHERE date <= ?
                ORDER BY date DESC
                LIMIT ?
                """,
                (eval_date, horizon),
            ).fetchall()

            if len(cutoff_rows) < horizon:
                continue  # 取引日データが horizon 日分に満たない
            signal_cutoff_date = cutoff_rows[-1][0]  # 最も古い日付

            # まだ signal_results に記録されていない、評価期限が来たシグナルを取得
            pending = conn.execute(
                """
                SELECT s.id, s.date, s.code, s.direction
                FROM signals s
                WHERE s.date <= ?
                  AND s.code IS NOT NULL
                  AND NOT EXISTS (
                      SELECT 1 FROM signal_results sr
                      WHERE sr.signal_id = s.id AND sr.horizon_days = ?
                  )
                ORDER BY s.date ASC
                """,
                (signal_cutoff_date, horizon),
            ).fetchall()

            if not pending:
                continue

            records = []
            for sig_id, sig_date, code, direction in pending:
                cumret = _cumulative_return(conn, code, sig_date, horizon)
                if cumret is None:
                    continue  # データ不足でスキップ

                actual_eval_date = _nth_trading_date(conn, sig_date, horizon) or eval_date
                result = _judge(direction, cumret)
                records.append((sig_id, horizon, actual_eval_date, cumret, result))

            if records:
                conn.executemany(
                    "INSERT OR IGNORE INTO signal_results "
                    "(signal_id, horizon_days, eval_date, actual_return, result) "
                    "VALUES (?, ?, ?, ?, ?)",
                    records,
                )
                conn.commit()
                total_recorded += len(records)
                logger.info(
                    f"signal_results 記録: horizon={horizon}日, {len(records)} 件"
                )

    finally:
        conn.close()

    logger.info(f"evaluate_pending_signals 完了: {total_recorded} 件")
    return total_recorded


def aggregate_accuracy(db_path: str, calc_date: Optional[str] = None) -> None:
    """
    signal_results から シグナルタイプ × ホライズン別の的中率を集計し、
    signal_accuracy テーブルを更新する。

    Args:
        db_path:   SQLite ファイルパス
        calc_date: 集計日 (YYYY-MM-DD)。省略時は今日。
    """
    if calc_date is None:
        calc_date = date.today().isoformat()

    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            """
            SELECT
                s.signal_type,
                sr.horizon_days,
                COUNT(*) AS total,
                SUM(CASE WHEN sr.result = 'hit' THEN 1 ELSE 0 END) AS hits,
                AVG(sr.actual_return) AS avg_return
            FROM signal_results sr
            JOIN signals s ON sr.signal_id = s.id
            GROUP BY s.signal_type, sr.horizon_days
            """
        ).fetchall()

        if not rows:
            logger.info("aggregate_accuracy: 集計対象なし")
            return

        records = []
        for signal_type, horizon_days, total, hits, avg_return in rows:
            hit_rate = round(hits / total, 4) if total > 0 else 0.0
            records.append(
                (signal_type, horizon_days, calc_date, total, hits, hit_rate, avg_return)
            )

        conn.executemany(
            """
            INSERT INTO signal_accuracy
                (signal_type, horizon_days, calc_date, total_signals, hits, hit_rate, avg_return)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(signal_type, horizon_days, calc_date) DO UPDATE SET
                total_signals = excluded.total_signals,
                hits          = excluded.hits,
                hit_rate      = excluded.hit_rate,
                avg_return    = excluded.avg_return
            """,
            records,
        )
        conn.commit()
        logger.info(f"signal_accuracy 更新: {len(records)} 行 (calc_date={calc_date})")

    finally:
        conn.close()


def run_all(db_path: str, eval_date: Optional[str] = None) -> int:
    """
    evaluate_pending_signals → aggregate_accuracy を順に実行する。
    バッチ handler から呼び出すエントリポイント。

    Returns:
        evaluate_pending_signals の記録件数
    """
    n = evaluate_pending_signals(db_path, eval_date)
    aggregate_accuracy(db_path, eval_date)
    return n
