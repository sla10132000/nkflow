"""
Phase 12: 通知 Lambda ハンドラ

SNS トピックからのメッセージを受け取り、
LINE Notify / Slack Incoming Webhook に転送する。

SNS → この Lambda の流れで呼ばれる。
通知先は SSM Parameter Store から動的に取得する (未設定の場合はスキップ)。

SSM パラメータ (SecureString):
  /nkflow/slack-webhook-url   - Slack Incoming Webhook URL (オプション)
  /nkflow/line-notify-token   - LINE Notify アクセストークン (オプション)
"""
import json
import logging
import sys
import urllib.parse
import urllib.request
from typing import Any

import boto3
from botocore.exceptions import ClientError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

# ウォームスタート間でSSM値をキャッシュ
_ssm_cache: dict[str, str | None] = {}


def _get_ssm(name: str) -> str | None:
    """SSM Parameter Store から SecureString を取得する。キャッシュ付き。"""
    if name in _ssm_cache:
        return _ssm_cache[name]

    try:
        ssm = boto3.client("ssm")
        value = ssm.get_parameter(Name=name, WithDecryption=True)["Parameter"]["Value"]
        _ssm_cache[name] = value
        logger.info(f"SSM から取得: {name}")
        return value
    except ClientError as e:
        if e.response["Error"]["Code"] == "ParameterNotFound":
            logger.info(f"SSM パラメータ未設定: {name}")
            _ssm_cache[name] = None
            return None
        logger.error(f"SSM 取得エラー ({name}): {e}")
        raise


def _send_slack(webhook_url: str, message: str) -> None:
    """Slack Incoming Webhook にメッセージを送信する。"""
    payload = json.dumps({"text": message}).encode("utf-8")
    req = urllib.request.Request(
        webhook_url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        body = resp.read().decode()
        logger.info(f"Slack 送信完了: status={resp.status} body={body}")


def _send_line(token: str, message: str) -> None:
    """LINE Notify API にメッセージを送信する。"""
    data = urllib.parse.urlencode({"message": f"\n{message}"}).encode("utf-8")
    req = urllib.request.Request(
        "https://notify-api.line.me/api/notify",
        data=data,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Authorization": f"Bearer {token}",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        body = resp.read().decode()
        logger.info(f"LINE Notify 送信完了: status={resp.status} body={body}")


def handler(event: dict, context: Any) -> dict:
    """
    Lambda ハンドラ。SNS Records を順に処理して通知を送信する。

    event 例:
      {
        "Records": [
          {
            "Sns": {
              "Subject": "nkflow 日次レポート 2025-01-15",
              "Message": "【nkflow 日次レポート】..."
            }
          }
        ]
      }
    """
    records = event.get("Records", [])
    if not records:
        logger.warning("SNS Records が空です")
        return {"statusCode": 200, "body": "no records"}

    slack_url = _get_ssm("/nkflow/slack-webhook-url")
    line_token = _get_ssm("/nkflow/line-notify-token")

    if not slack_url and not line_token:
        logger.warning(
            "通知先が設定されていません。"
            "SSM に /nkflow/slack-webhook-url または /nkflow/line-notify-token を設定してください。"
        )
        return {"statusCode": 200, "body": "no destination configured"}

    sent = 0
    errors: list[str] = []

    for record in records:
        sns_payload = record.get("Sns", {})
        message = sns_payload.get("Message", "")

        if not message:
            logger.warning("SNS Message が空です")
            continue

        if slack_url:
            try:
                _send_slack(slack_url, message)
                sent += 1
            except Exception as e:
                logger.error(f"Slack 送信失敗: {e}")
                errors.append(f"slack: {e}")

        if line_token:
            try:
                _send_line(line_token, message)
                sent += 1
            except Exception as e:
                logger.error(f"LINE Notify 送信失敗: {e}")
                errors.append(f"line: {e}")

    status = 200 if not errors else 207
    return {"statusCode": status, "body": {"sent": sent, "errors": errors}}
