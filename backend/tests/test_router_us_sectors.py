"""Phase 23b: /api/us-sectors/* エンドポイントテスト"""
import os
import sqlite3
import sys
from datetime import date, timedelta
from unittest.mock import patch

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scripts.init_sqlite import init_sqlite

BUCKET = "test-nkflow-bucket"

SECTOR_ETFS = [
    ("XLK", "Technology Select Sector SPDR"),
    ("XLF", "Financial Select Sector SPDR"),
    ("XLV", "Health Care Select Sector SPDR"),
    ("XLE", "Energy Select Sector SPDR"),
    ("XLI", "Industrial Select Sector SPDR"),
    ("XLY", "Consumer Discretionary Select Sector SPDR"),
    ("XLP", "Consumer Staples Select Sector SPDR"),
    ("XLU", "Utilities Select Sector SPDR"),
    ("XLB", "Materials Select Sector SPDR"),
    ("XLRE", "Real Estate Select Sector SPDR"),
    ("XLC", "Communication Services Select Sector SPDR"),
]


@pytest.fixture(autouse=True)
def aws_env(monkeypatch):
    monkeypatch.setenv("AWS_DEFAULT_REGION", "ap-northeast-1")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test")
    monkeypatch.setenv("S3_BUCKET", BUCKET)


@pytest.fixture
def db_with_sector_data(tmp_path):
    """セクター ETF データ入り SQLite を S3 にアップロードし、パスを返す。"""
    db_path = str(tmp_path / "stocks.db")
    init_sqlite(db_path)

    conn = sqlite3.connect(db_path)
    today = date.today().isoformat()
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    last_week = (date.today() - timedelta(days=7)).isoformat()

    rows = []
    for i, (ticker, name) in enumerate(SECTOR_ETFS):
        base = 100.0 + i * 10
        # 先週
        rows.append((last_week, ticker, name, base, base + 2, base - 1, base + 1.0, 5000000))
        # 昨日
        rows.append((yesterday, ticker, name, base + 1, base + 3, base, base + 2.0, 6000000))
        # 今日 (変動: XLK +1.85%, XLF -0.5% など)
        change = 1.85 if ticker == "XLK" else (-0.5 if ticker == "XLF" else 0.5)
        close_today = round((base + 2.0) * (1 + change / 100), 2)
        rows.append((today, ticker, name, base + 2, base + 5, base + 1, close_today, 8000000))

    conn.executemany(
        "INSERT OR REPLACE INTO us_indices (date, ticker, name, open, high, low, close, volume) "
        "VALUES (?,?,?,?,?,?,?,?)",
        rows,
    )
    conn.commit()
    conn.close()
    return db_path


@pytest.fixture
def client(db_with_sector_data, monkeypatch):
    """FastAPI TestClient (S3 モック + SQLite ファイル直接利用)。"""
    monkeypatch.setenv("SQLITE_PATH", db_with_sector_data)

    with mock_aws():
        s3 = boto3.client("s3", region_name="ap-northeast-1")
        s3.create_bucket(
            Bucket=BUCKET,
            CreateBucketConfiguration={"LocationConstraint": "ap-northeast-1"},
        )
        s3.upload_file(db_with_sector_data, BUCKET, "data/stocks.db")

        from src.api.main import app
        yield TestClient(app)


class TestUsSectorsPerformance:
    def test_performance_returns_all_sectors(self, client):
        """パフォーマンス API が全 11 セクターを返すこと"""
        resp = client.get("/api/us-sectors/performance")
        assert resp.status_code == 200
        data = resp.json()
        assert "sectors" in data
        assert len(data["sectors"]) == 11

    def test_performance_has_required_fields(self, client):
        """各セクターに必須フィールドが含まれること"""
        resp = client.get("/api/us-sectors/performance")
        assert resp.status_code == 200
        sectors = resp.json()["sectors"]
        for s in sectors:
            assert "ticker" in s
            assert "name" in s
            assert "sector" in s
            assert "close" in s
            assert "change_pct" in s
            assert "volume" in s

    def test_performance_sorts_by_change_pct(self, client):
        """騰落率降順でソートされること"""
        resp = client.get("/api/us-sectors/performance")
        assert resp.status_code == 200
        sectors = resp.json()["sectors"]
        change_pcts = [s["change_pct"] for s in sectors if s["change_pct"] is not None]
        assert change_pcts == sorted(change_pcts, reverse=True)

    def test_performance_period_parameter(self, client):
        """period パラメータで期間切替できること"""
        for period in ["1d", "1w", "1m", "3m"]:
            resp = client.get(f"/api/us-sectors/performance?period={period}")
            assert resp.status_code == 200
            assert resp.json()["period"] == period

    def test_performance_invalid_period(self, client):
        """不正な period パラメータで 422 エラーになること"""
        resp = client.get("/api/us-sectors/performance?period=invalid")
        assert resp.status_code == 422

    def test_performance_xlk_has_sector_name(self, client):
        """XLK の sector フィールドが日本語名であること"""
        resp = client.get("/api/us-sectors/performance")
        assert resp.status_code == 200
        sectors = resp.json()["sectors"]
        xlk = next((s for s in sectors if s["ticker"] == "XLK"), None)
        assert xlk is not None
        assert xlk["sector"] == "テクノロジー"

    def test_performance_empty_data(self, tmp_path, monkeypatch):
        """データがない場合に空リストを返すこと"""
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
            resp = c.get("/api/us-sectors/performance")

        assert resp.status_code == 200
        assert resp.json()["sectors"] == []


class TestUsSectorsHeatmap:
    def test_heatmap_returns_weekly_data(self, client):
        """週次ヒートマップが正しい形式で返ること"""
        resp = client.get("/api/us-sectors/heatmap?period_type=weekly&periods=4")
        assert resp.status_code == 200
        data = resp.json()
        assert "periods" in data
        assert "sectors" in data
        assert isinstance(data["periods"], list)
        assert isinstance(data["sectors"], list)

    def test_heatmap_sectors_have_values(self, client):
        """各セクターに values 配列があること"""
        resp = client.get("/api/us-sectors/heatmap")
        assert resp.status_code == 200
        sectors = resp.json()["sectors"]
        for s in sectors:
            assert "ticker" in s
            assert "sector" in s
            assert "values" in s
            assert isinstance(s["values"], list)

    def test_heatmap_period_type_monthly(self, client):
        """月次ヒートマップが返ること"""
        resp = client.get("/api/us-sectors/heatmap?period_type=monthly")
        assert resp.status_code == 200
        data = resp.json()
        assert "periods" in data

    def test_heatmap_invalid_period_type(self, client):
        """不正な period_type で 422 エラーになること"""
        resp = client.get("/api/us-sectors/heatmap?period_type=daily")
        assert resp.status_code == 422
