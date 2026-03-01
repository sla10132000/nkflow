"""
Phase 12: SNS に日次レポートを Publish する通知モジュール

バッチ処理完了後に呼び出し、当日のサマリーを SNS トピックに送信する。
SNS → Notification Lambda → LINE Notify / Slack Webhook の流れで通知が届く。

環境変数:
  SNS_TOPIC_ARN - SNS トピック ARN (未設定時は通知をスキップ)
"""
import json
import logging
import sqlite3
from typing import Any, Optional

import boto3

from src.config import SNS_TOPIC_ARN

logger = logging.getLogger(__name__)


def build_report(
    db_path: str,
    target_date: str,
    batch_result: dict[str, Any],
) -> str:
    """
    日次レポート文字列を組み立てる。

    内容:
      - 日経225状況 (regime / nikkei_return / nikkei_close)
      - 生成シグナル数
      - 信頼度上位シグナル (最大5件)
      - シグナル的中率サマリー (5日ホライズン、直近集計日)

    Args:
        db_path:      SQLite ファイルパス
        target_date:  'YYYY-MM-DD'
        batch_result: handler から受け取る結果 dict
                      (stocks_updated, signals_generated, errors)
    Returns:
        通知用テキスト
    """
    conn = sqlite3.connect(db_path)
    lines: list[str] = []

    try:
        # ─── ヘッダー ───────────────────────────────────────────
        lines.append(f"【nkflow 日次レポート】{target_date}")
        lines.append("")

        # ─── 日経225状況 ─────────────────────────────────────────
        summary_row = conn.execute(
            "SELECT nikkei_close, nikkei_return, regime FROM daily_summary WHERE date = ?",
            (target_date,),
        ).fetchone()

        if summary_row:
            nk_close, nk_return, regime = summary_row
            regime_label = {"risk_on": "リスクオン", "risk_off": "リスクオフ"}.get(
                regime or "", regime or "不明"
            )
            close_str = f"{nk_close:,.0f}" if nk_close else "---"
            ret_str = (
                f"{nk_return:+.2%}" if nk_return is not None else "---"
            )
            lines.append(f"📊 日経225")
            lines.append(f"  終値: {close_str}  ({ret_str})")
            lines.append(f"  レジーム: {regime_label}")
        else:
            lines.append("📊 日経225: データなし")

        lines.append("")

        # ─── シグナルサマリー ─────────────────────────────────────
        signals_generated = batch_result.get("signals_generated", 0)
        lines.append(f"📣 本日のシグナル: {signals_generated} 件")

        if signals_generated > 0:
            top_signals = conn.execute(
                """
                SELECT sg.code, st.name, sg.signal_type, sg.direction, sg.confidence
                FROM signals sg
                LEFT JOIN stocks st ON sg.code = st.code
                WHERE sg.date = ? AND sg.code IS NOT NULL
                ORDER BY sg.confidence DESC
                LIMIT 5
                """,
                (target_date,),
            ).fetchall()

            for code, name, sig_type, direction, confidence in top_signals:
                icon = "▲" if direction == "bullish" else "▼"
                name_str = name or code
                lines.append(
                    f"  {icon} {code} {name_str} [{sig_type}/{direction}]"
                    f" 信頼度:{confidence:.2f}"
                )

        lines.append("")

        # ─── 的中率サマリー ───────────────────────────────────────
        accuracy_rows = conn.execute(
            """
            SELECT sa.signal_type, sa.hit_rate, sa.total_signals
            FROM signal_accuracy sa
            WHERE sa.horizon_days = 5
              AND sa.calc_date = (
                SELECT MAX(calc_date) FROM signal_accuracy WHERE horizon_days = 5
              )
            ORDER BY sa.hit_rate DESC
            """,
        ).fetchall()

        if accuracy_rows:
            lines.append("🎯 直近シグナル的中率 (5日ホライズン)")
            for sig_type, hit_rate, total in accuracy_rows:
                lines.append(
                    f"  {sig_type}: {hit_rate:.1%} ({total} 件)"
                )
        else:
            lines.append("🎯 的中率データなし")

        lines.append("")

        # ─── エラー情報 ───────────────────────────────────────────
        errors = batch_result.get("errors", [])
        if errors:
            lines.append(f"⚠️  エラー ({len(errors)} 件)")
            for err in errors[:3]:  # 最大3件
                lines.append(f"  - {err}")

    finally:
        conn.close()

    return "\n".join(lines)


def publish(
    db_path: str,
    target_date: str,
    batch_result: dict[str, Any],
    topic_arn: Optional[str] = None,
) -> bool:
    """
    SNS トピックに日次レポートを publish する。

    SNS_TOPIC_ARN (または topic_arn 引数) が未設定の場合は通知をスキップ。

    Args:
        db_path:      SQLite ファイルパス
        target_date:  'YYYY-MM-DD'
        batch_result: バッチ結果 dict (stocks_updated, signals_generated, errors)
        topic_arn:    SNS トピック ARN (省略時は config.SNS_TOPIC_ARN を使用)
    Returns:
        成功または スキップ: True / 失敗: False
    """
    arn = topic_arn or SNS_TOPIC_ARN
    if not arn:
        logger.info("SNS_TOPIC_ARN 未設定 — 通知をスキップ")
        return True

    try:
        message = build_report(db_path, target_date, batch_result)
        subject = f"nkflow 日次レポート {target_date}"

        sns = boto3.client("sns")
        resp = sns.publish(
            TopicArn=arn,
            Subject=subject,
            Message=message,
        )
        logger.info(f"SNS publish 完了: MessageId={resp['MessageId']}")
        return True

    except Exception as e:
        logger.error(f"SNS publish 失敗: {e}")
        return False
