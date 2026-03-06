"""Phase 23: /api/investor-flows/* エンドポイントテスト"""
import json
import os
import sqlite3
import sys

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scripts.init_sqlite import init_sqlite

BUCKET = "test-nkflow-bucket"


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def aws_env(monkeypatch):
    monkeypatch.setenv("AWS_DEFAULT_REGION", "ap-northeast-1")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test")
    monkeypatch.setenv("S3_BUCKET", BUCKET)


def _build_test_db(tmp_path) -> str:
    """テストデータ入りの stocks.db を作成して S3 にアップロードする。"""
    db_path = str(tmp_path / "stocks.db")
    init_sqlite(db_path)

    conn = sqlite3.connect(db_path)

    # investor_flow_weekly データ
    flow_weeks = [
        ("2026-01-01", "2026-01-07", "TSEPrime", "foreigners",
         5_000_000.0, 8_000_000.0, 3_000_000.0, "2026-01-14"),
        ("2026-01-01", "2026-01-07", "TSEPrime", "individuals",
         8_000_000.0, 5_000_000.0, -3_000_000.0, "2026-01-14"),
        ("2026-01-01", "2026-01-07", "TSEPrime", "investment_trusts",
         1_000_000.0, 1_200_000.0, 200_000.0, "2026-01-14"),
        ("2026-01-08", "2026-01-14", "TSEPrime", "foreigners",
         6_000_000.0, 9_000_000.0, 3_000_000.0, "2026-01-21"),
        ("2026-01-08", "2026-01-14", "TSEPrime", "individuals",
         9_000_000.0, 6_000_000.0, -3_000_000.0, "2026-01-21"),
    ]
    conn.executemany(
        """
        INSERT OR REPLACE INTO investor_flow_weekly
            (week_start, week_end, section, investor_type, sales, purchases, balance, published_date)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        flow_weeks,
    )

    # investor_flow_indicators データ
    indicators = [
        ("2026-01-07", 3_000_000.0, -3_000_000.0,
         2_500_000.0, -2_500_000.0,
         100_000.0, -100_000.0,
         0.35, 0.02, "bull"),
        ("2026-01-14", 3_000_000.0, -3_000_000.0,
         2_800_000.0, -2_800_000.0,
         200_000.0, -200_000.0,
         0.40, 0.03, "bull"),
    ]
    conn.executemany(
        """
        INSERT OR REPLACE INTO investor_flow_indicators
            (week_end, foreigners_net, individuals_net,
             foreigners_4w_ma, individuals_4w_ma,
             foreigners_momentum, individuals_momentum,
             divergence_score, nikkei_return_4w, flow_regime)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        indicators,
    )

    # シグナルデータ
    reasoning = json.dumps({
        "foreigners_net": 3_000_000.0,
        "individuals_net": -3_000_000.0,
        "divergence_score": 0.40,
        "nikkei_return_4w": 0.03,
        "flow_regime": "bull",
    })
    conn.execute(
        """
        INSERT INTO signals
            (date, signal_type, code, sector, direction, confidence, reasoning)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        ("2026-01-14", "investor_flow_divergence", None, None, "bearish", 0.40, reasoning),
    )

    conn.commit()
    conn.close()
    return db_path


@pytest.fixture
def client(tmp_path, monkeypatch):
    """テストデータ入り DB を S3 にアップロードし、FastAPI TestClient を返す。"""
    db_path = _build_test_db(tmp_path)
    monkeypatch.setenv("SQLITE_PATH", db_path)

    with mock_aws():
        s3 = boto3.client("s3", region_name="ap-northeast-1")
        s3.create_bucket(
            Bucket=BUCKET,
            CreateBucketConfiguration={"LocationConstraint": "ap-northeast-1"},
        )
        s3.upload_file(db_path, BUCKET, "data/stocks.db")

        from src.api.main import app
        yield TestClient(app)


# ── GET /api/investor-flows/timeseries ───────────────────────────────────────

class TestInvestorFlowTimeseries:
    def test_returns_list(self, client):
        """正常レスポンスはリスト形式であること"""
        resp = client.get("/api/investor-flows/timeseries?investor_type=foreigners&weeks=10")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    def test_returns_correct_investor_type(self, client):
        """指定した investor_type のデータのみ返すこと"""
        resp = client.get("/api/investor-flows/timeseries?investor_type=foreigners&weeks=52")
        assert resp.status_code == 200
        data = resp.json()
        for row in data:
            assert row["investor_type"] == "foreigners"

    def test_ordered_ascending_by_week_end(self, client):
        """結果が week_end 昇順であること (チャート表示用)"""
        resp = client.get("/api/investor-flows/timeseries?investor_type=foreigners&weeks=52")
        assert resp.status_code == 200
        data = resp.json()
        if len(data) >= 2:
            dates = [r["week_end"] for r in data]
            assert dates == sorted(dates)

    def test_response_contains_required_fields(self, client):
        """レスポンスに必須フィールドが含まれること"""
        resp = client.get("/api/investor-flows/timeseries?investor_type=foreigners")
        assert resp.status_code == 200
        data = resp.json()
        if data:
            row = data[0]
            assert "week_start" in row
            assert "week_end" in row
            assert "balance" in row
            assert "sales" in row
            assert "purchases" in row

    def test_invalid_investor_type_returns_400(self, client):
        """不明な investor_type は 400 エラーになること"""
        resp = client.get("/api/investor-flows/timeseries?investor_type=unknown_type")
        assert resp.status_code == 400

    def test_weeks_out_of_range_returns_400(self, client):
        """weeks が範囲外 (0) は 400 エラーになること"""
        resp = client.get("/api/investor-flows/timeseries?weeks=0&investor_type=foreigners")
        assert resp.status_code == 400

    def test_empty_db_returns_empty_list(self, tmp_path, monkeypatch):
        """データがない場合は空リストを返すこと"""
        db_path = str(tmp_path / "empty.db")
        init_sqlite(db_path)
        monkeypatch.setenv("SQLITE_PATH", db_path)

        with mock_aws():
            s3 = boto3.client("s3", region_name="ap-northeast-1")
            s3.create_bucket(
                Bucket=BUCKET,
                CreateBucketConfiguration={"LocationConstraint": "ap-northeast-1"},
            )
            s3.upload_file(db_path, BUCKET, "data/stocks.db")

            from src.api.main import app
            c = TestClient(app)
            resp = c.get("/api/investor-flows/timeseries?investor_type=foreigners")
            assert resp.status_code == 200
            assert resp.json() == []


# ── GET /api/investor-flows/indicators ───────────────────────────────────────

class TestInvestorFlowIndicators:
    def test_returns_list(self, client):
        """正常レスポンスはリスト形式であること"""
        resp = client.get("/api/investor-flows/indicators?weeks=26")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_ordered_ascending(self, client):
        """week_end 昇順で返すこと"""
        resp = client.get("/api/investor-flows/indicators?weeks=52")
        assert resp.status_code == 200
        data = resp.json()
        if len(data) >= 2:
            dates = [r["week_end"] for r in data]
            assert dates == sorted(dates)

    def test_response_contains_indicator_fields(self, client):
        """レスポンスに指標フィールドが含まれること"""
        resp = client.get("/api/investor-flows/indicators")
        assert resp.status_code == 200
        data = resp.json()
        if data:
            row = data[0]
            assert "week_end" in row
            assert "foreigners_net" in row
            assert "individuals_net" in row
            assert "foreigners_4w_ma" in row
            assert "divergence_score" in row
            assert "flow_regime" in row

    def test_weeks_out_of_range_returns_400(self, client):
        """weeks が範囲外 (0) は 400 エラーになること"""
        resp = client.get("/api/investor-flows/indicators?weeks=0")
        assert resp.status_code == 400

    def test_indicator_values_correct(self, client):
        """指標値が DB の値と一致すること"""
        resp = client.get("/api/investor-flows/indicators?weeks=10")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1
        latest = data[-1]
        assert latest["week_end"] == "2026-01-14"
        assert latest["foreigners_net"] == pytest.approx(3_000_000.0)
        assert latest["flow_regime"] == "bull"


# ── GET /api/investor-flows/latest ───────────────────────────────────────────

class TestInvestorFlowLatest:
    def test_returns_dict_with_required_keys(self, client):
        """レスポンスが必須フィールドを持つ dict であること"""
        resp = client.get("/api/investor-flows/latest")
        assert resp.status_code == 200
        data = resp.json()
        assert "week_end" in data
        assert "indicators" in data
        assert "flows" in data
        assert "signals" in data

    def test_week_end_is_latest(self, client):
        """week_end が最新の週であること"""
        resp = client.get("/api/investor-flows/latest")
        assert resp.status_code == 200
        data = resp.json()
        assert data["week_end"] == "2026-01-14"

    def test_flows_contains_investor_types(self, client):
        """flows に該当週の投資主体データが含まれること"""
        resp = client.get("/api/investor-flows/latest")
        assert resp.status_code == 200
        data = resp.json()
        assert "foreigners" in data["flows"]
        assert "individuals" in data["flows"]

    def test_signals_list_returned(self, client):
        """signals はリスト形式であること"""
        resp = client.get("/api/investor-flows/latest")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data["signals"], list)

    def test_signals_contain_required_fields(self, client):
        """signals の各要素に必須フィールドが含まれること"""
        resp = client.get("/api/investor-flows/latest")
        assert resp.status_code == 200
        data = resp.json()
        if data["signals"]:
            sig = data["signals"][0]
            assert "signal_type" in sig
            assert "direction" in sig
            assert "confidence" in sig
            assert "reasoning" in sig

    def test_signals_reasoning_is_dict(self, client):
        """signals の reasoning は dict (JSON デコード済み) であること"""
        resp = client.get("/api/investor-flows/latest")
        assert resp.status_code == 200
        data = resp.json()
        for sig in data["signals"]:
            assert isinstance(sig["reasoning"], dict)

    def test_404_when_no_indicator_data(self, tmp_path, monkeypatch):
        """指標データがない場合は 404 を返すこと"""
        db_path = str(tmp_path / "empty.db")
        init_sqlite(db_path)
        monkeypatch.setenv("SQLITE_PATH", db_path)

        with mock_aws():
            s3 = boto3.client("s3", region_name="ap-northeast-1")
            s3.create_bucket(
                Bucket=BUCKET,
                CreateBucketConfiguration={"LocationConstraint": "ap-northeast-1"},
            )
            s3.upload_file(db_path, BUCKET, "data/stocks.db")

            from src.api.main import app
            c = TestClient(app)
            resp = c.get("/api/investor-flows/latest")
            assert resp.status_code == 404
