"""
Phase 12: notifier.py / notification/handler.py のテスト

- build_report: SQLite から日次レポートを組み立てる
- publish: SNS トピックにメッセージを publish する
- notification/handler: SNS イベントを受け取り LINE/Slack に転送する
"""
import json
import os
import sqlite3
import tempfile
from unittest.mock import MagicMock, patch

import boto3
import pytest
from moto import mock_aws

from scripts.init_sqlite import init_sqlite


# ─────────────────────────────────────────────────────────────────────────────
# フィクスチャ
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def aws_credentials(monkeypatch):
    """moto 用のダミー AWS 認証情報を設定する。"""
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_SECURITY_TOKEN", "testing")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "ap-northeast-1")


@pytest.fixture
def db_path(tmp_path):
    """初期化済み SQLite のパスを返す。"""
    path = str(tmp_path / "test.db")
    init_sqlite(path)

    conn = sqlite3.connect(path)
    conn.execute("INSERT INTO stocks (code, name, sector) VALUES ('7203', 'トヨタ自動車', '輸送用機器')")
    conn.execute("INSERT INTO stocks (code, name, sector) VALUES ('6758', 'ソニーグループ', '電気機器')")

    conn.execute(
        """
        INSERT INTO daily_prices (code, date, open, high, low, close, volume, return_rate)
        VALUES ('7203', '2025-01-15', 2800, 2900, 2750, 2880, 5000000, 0.028)
        """
    )
    conn.execute(
        """
        INSERT INTO daily_prices (code, date, open, high, low, close, volume, return_rate)
        VALUES ('6758', '2025-01-15', 1500, 1560, 1480, 1540, 3000000, 0.027)
        """
    )

    conn.execute(
        """
        INSERT INTO daily_summary (date, nikkei_close, nikkei_return, regime, active_signals)
        VALUES ('2025-01-15', 38500.0, 0.012, 'risk_on', 3)
        """
    )

    conn.execute(
        """
        INSERT INTO signals (date, signal_type, code, direction, confidence, reasoning)
        VALUES ('2025-01-15', 'causality_chain', '7203', 'bullish', 0.92, '{}')
        """
    )
    conn.execute(
        """
        INSERT INTO signals (date, signal_type, code, direction, confidence, reasoning)
        VALUES ('2025-01-15', 'fund_flow', '6758', 'bullish', 0.80, '{}')
        """
    )

    conn.commit()
    conn.close()
    return path


# ─────────────────────────────────────────────────────────────────────────────
# build_report テスト
# ─────────────────────────────────────────────────────────────────────────────

class TestBuildReport:
    def test_contains_date(self, db_path):
        from src.batch.notifier import build_report
        report = build_report(db_path, "2025-01-15", {"stocks_updated": 225, "errors": []})
        assert "2025-01-15" in report

    def test_contains_nikkei_info(self, db_path):
        from src.batch.notifier import build_report
        report = build_report(db_path, "2025-01-15", {"stocks_updated": 225, "errors": []})
        assert "38,500" in report
        assert "リスクオン" in report

    def test_contains_errors_when_present(self, db_path):
        from src.batch.notifier import build_report
        report = build_report(
            db_path, "2025-01-15",
            {"stocks_updated": 225, "errors": ["compute: some error"]}
        )
        assert "エラー" in report
        assert "compute: some error" in report

    def test_no_summary_row(self, db_path):
        """daily_summary がない日でもクラッシュしない。"""
        from src.batch.notifier import build_report
        report = build_report(db_path, "2000-01-01", {"stocks_updated": 0, "errors": []})
        assert "2000-01-01" in report


# ─────────────────────────────────────────────────────────────────────────────
# publish テスト
# ─────────────────────────────────────────────────────────────────────────────

class TestPublish:
    @mock_aws
    def test_publish_sends_to_sns(self, db_path):
        """SNS_TOPIC_ARN が設定されていれば SNS に publish される。"""
        sns_client = boto3.client("sns", region_name="ap-northeast-1")
        topic = sns_client.create_topic(Name="nkflow-notifications")
        topic_arn = topic["TopicArn"]

        from src.batch import notifier
        result = notifier.publish(
            db_path, "2025-01-15",
            {"stocks_updated": 225, "errors": []},
            topic_arn=topic_arn,
        )
        assert result is True

    def test_publish_skips_when_no_arn(self, db_path, monkeypatch):
        """SNS_TOPIC_ARN が未設定の場合はスキップして True を返す。"""
        monkeypatch.setenv("SNS_TOPIC_ARN", "")
        import src.config as cfg
        cfg.SNS_TOPIC_ARN = ""

        from src.batch import notifier
        result = notifier.publish(
            db_path, "2025-01-15",
            {"stocks_updated": 225, "errors": []},
            topic_arn="",
        )
        assert result is True

    @mock_aws
    def test_publish_returns_false_on_error(self, db_path):
        """存在しない ARN への publish は False を返す (例外を raise しない)。"""
        from src.batch import notifier
        result = notifier.publish(
            db_path, "2025-01-15",
            {"stocks_updated": 225, "errors": []},
            topic_arn="arn:aws:sns:ap-northeast-1:123456789012:nonexistent",
        )
        assert result is False


# ─────────────────────────────────────────────────────────────────────────────
# notification/handler テスト
# ─────────────────────────────────────────────────────────────────────────────

def _make_sns_event(message: str, subject: str = "nkflow test") -> dict:
    return {
        "Records": [
            {
                "Sns": {
                    "Subject": subject,
                    "Message": message,
                }
            }
        ]
    }


class TestNotificationHandler:
    def test_no_slack_no_line_skips(self, monkeypatch):
        """SSMに通知先が未設定の場合はスキップして 200 を返す。"""
        import src.notification.handler as nh
        nh._ssm_cache.clear()

        with mock_aws():
            boto3.client("ssm", region_name="ap-northeast-1").put_parameter(
                Name="/nkflow/slack-webhook-url",
                Value="PLACEHOLDER_SET_MANUALLY",
                Type="String",
            )
            boto3.client("ssm", region_name="ap-northeast-1").put_parameter(
                Name="/nkflow/line-notify-token",
                Value="PLACEHOLDER_SET_MANUALLY",
                Type="String",
            )
            # PLACEHOLDER は URL として無効なので通知先なしと同じ扱いになる
            # 実装上はSSM値があれば送信を試みるため、ここではモックをパッチする
            with patch.object(nh, "_get_ssm", return_value=None):
                resp = nh.handler(_make_sns_event("test message"), None)
        assert resp["statusCode"] == 200

    def test_empty_records_returns_200(self):
        """Records が空の場合も 200 を返す。"""
        import src.notification.handler as nh
        resp = nh.handler({"Records": []}, None)
        assert resp["statusCode"] == 200

    def test_slack_send_called(self):
        """SSMから Slack URL が取得できる場合、_send_slack が呼ばれる。"""
        import src.notification.handler as nh
        nh._ssm_cache.clear()

        with patch.object(nh, "_get_ssm", side_effect=lambda name: (
            "https://hooks.slack.com/test" if "slack" in name else None
        )):
            with patch.object(nh, "_send_slack") as mock_slack:
                resp = nh.handler(_make_sns_event("hello slack"), None)

        mock_slack.assert_called_once_with("https://hooks.slack.com/test", "hello slack")
        assert resp["statusCode"] == 200

    def test_line_send_called(self):
        """SSMから LINE トークンが取得できる場合、_send_line が呼ばれる。"""
        import src.notification.handler as nh
        nh._ssm_cache.clear()

        with patch.object(nh, "_get_ssm", side_effect=lambda name: (
            None if "slack" in name else "dummy-line-token"
        )):
            with patch.object(nh, "_send_line") as mock_line:
                resp = nh.handler(_make_sns_event("hello line"), None)

        mock_line.assert_called_once_with("dummy-line-token", "hello line")
        assert resp["statusCode"] == 200

    def test_slack_error_returns_207(self):
        """Slack 送信でエラーが発生した場合は 207 を返す。"""
        import src.notification.handler as nh
        nh._ssm_cache.clear()

        with patch.object(nh, "_get_ssm", side_effect=lambda name: (
            "https://hooks.slack.com/test" if "slack" in name else None
        )):
            with patch.object(nh, "_send_slack", side_effect=Exception("timeout")):
                resp = nh.handler(_make_sns_event("error test"), None)

        assert resp["statusCode"] == 207
        assert len(resp["body"]["errors"]) > 0

    def test_both_slack_and_line_called(self):
        """Slack と LINE 両方が設定されている場合、両方に送信する。"""
        import src.notification.handler as nh
        nh._ssm_cache.clear()

        with patch.object(nh, "_get_ssm", side_effect=lambda name: (
            "https://hooks.slack.com/test" if "slack" in name else "dummy-line-token"
        )):
            with patch.object(nh, "_send_slack") as mock_slack:
                with patch.object(nh, "_send_line") as mock_line:
                    resp = nh.handler(_make_sns_event("both message"), None)

        mock_slack.assert_called_once()
        mock_line.assert_called_once()
        assert resp["statusCode"] == 200
        assert resp["body"]["sent"] == 2

    def test_ssm_cache_reused(self):
        """SSM 呼び出しはキャッシュされ、複数レコードでも1回しか呼ばれない。"""
        import src.notification.handler as nh
        nh._ssm_cache.clear()

        call_count = 0

        def fake_get_ssm(name):
            nonlocal call_count
            call_count += 1
            return None

        with patch.object(nh, "_get_ssm", side_effect=fake_get_ssm):
            nh.handler({"Records": [
                {"Sns": {"Subject": "s", "Message": "m1"}},
                {"Sns": {"Subject": "s", "Message": "m2"}},
            ]}, None)

        # Records が2件でも _get_ssm は2パラメータ分しか呼ばれない (Recordsループ外で取得)
        assert call_count == 2
