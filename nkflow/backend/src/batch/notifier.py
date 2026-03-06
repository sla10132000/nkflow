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

    Args:
        db_path:      SQLite ファイルパス
        target_date:  'YYYY-MM-DD'
        batch_result: handler から受け取る結果 dict
                      (stocks_updated, errors)
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
        batch_result: バッチ結果 dict (stocks_updated, errors)
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
