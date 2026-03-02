"""Phase 16: 市場圧力 (Market Pressure) テスト

テスト内容:
  1. _calc_pl_zone: 各閾値の境界値テスト
  2. run_market_pressure: SQLite in-memory DB で指標計算
  3. generate_credit_overheating_signal: 2条件を満たすデータで発動確認
  4. GET /api/market-pressure/timeseries: TestClient でエンドポイント確認
"""
import json
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
from scripts.migrate_phase16 import migrate
from src.batch.statistics import _calc_pl_zone, run_market_pressure
from src.batch.signals import generate_credit_overheating_signal

BUCKET = "test-nkflow-bucket"
TARGET_DATE = "2025-03-01"

STOCKS = [
    ("7203", "トヨタ自動車", "輸送用機器"),
    ("6758", "ソニーグループ", "電気機器"),
    ("6902", "デンソー",      "輸送用機器"),
]


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def aws_env(monkeypatch, tmp_path):
    monkeypatch.setenv("S3_BUCKET", BUCKET)
    monkeypatch.setenv("AWS_DEFAULT_REGION", "ap-northeast-1")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "stocks.db"))


def _make_db(tmp_path) -> str:
    """Phase 16 マイグレーション済みの stocks.db を作成する。"""
    db_path = str(tmp_path / "stocks.db")
    init_sqlite(db_path)
    migrate(db_path)

    conn = sqlite3.connect(db_path)
    conn.executemany("INSERT INTO stocks (code, name, sector) VALUES (?, ?, ?)", STOCKS)

    # daily_prices: TARGET_DATE の直近 25 営業日分
    for i in range(25):
        d = (date.fromisoformat(TARGET_DATE) - timedelta(days=i + 1)).isoformat()
        for code in [s[0] for s in STOCKS]:
            conn.execute(
                "INSERT OR REPLACE INTO daily_prices "
                "(code, date, open, high, low, close, volume, return_rate, price_range, range_pct) "
                "VALUES (?, ?, 1000, 1010, 990, 1000, 1000000, ?, 20, 0.02)",
                (code, d, 0.005),
            )

    # margin_balances: TARGET_DATE 直前の週次データ
    week = "2025-02-28"
    for code, _, _ in STOCKS:
        conn.execute(
            "INSERT OR REPLACE INTO margin_balances "
            "(code, week_date, margin_buy, margin_sell, margin_ratio) "
            "VALUES (?, ?, ?, ?, ?)",
            (code, week, 1_000_000.0, 200_000.0, 5.0),
        )

    conn.commit()
    conn.close()
    return db_path


# ─────────────────────────────────────────────────────────────────────────────
# 1. _calc_pl_zone 境界値テスト
# ─────────────────────────────────────────────────────────────────────────────

class TestCalcPlZone:
    def test_ceiling_at_015(self):
        assert _calc_pl_zone(0.15) == "ceiling"

    def test_ceiling_above_015(self):
        assert _calc_pl_zone(0.20) == "ceiling"

    def test_overheat_at_005(self):
        assert _calc_pl_zone(0.05) == "overheat"

    def test_overheat_just_below_015(self):
        assert _calc_pl_zone(0.149) == "overheat"

    def test_neutral_at_zero(self):
        assert _calc_pl_zone(0.0) == "neutral"

    def test_neutral_just_below_005(self):
        assert _calc_pl_zone(0.049) == "neutral"

    def test_weak_at_minus_010(self):
        assert _calc_pl_zone(-0.10) == "weak"

    def test_weak_just_below_zero(self):
        assert _calc_pl_zone(-0.001) == "weak"

    def test_sellin_at_minus_015(self):
        assert _calc_pl_zone(-0.15) == "sellin"

    def test_sellin_just_below_minus_010(self):
        assert _calc_pl_zone(-0.101) == "sellin"

    def test_bottom_below_minus_015(self):
        assert _calc_pl_zone(-0.16) == "bottom"

    def test_bottom_very_low(self):
        assert _calc_pl_zone(-0.30) == "bottom"


# ─────────────────────────────────────────────────────────────────────────────
# 2. run_market_pressure
# ─────────────────────────────────────────────────────────────────────────────

class TestRunMarketPressure:
    def test_returns_1_when_data_exists(self, tmp_path):
        db_path = _make_db(tmp_path)
        result = run_market_pressure(db_path, TARGET_DATE)
        assert result == 1

    def test_writes_market_pressure_daily(self, tmp_path):
        db_path = _make_db(tmp_path)
        run_market_pressure(db_path, TARGET_DATE)

        conn = sqlite3.connect(db_path)
        row = conn.execute(
            "SELECT date, pl_zone, margin_ratio FROM market_pressure_daily WHERE date = ?",
            (TARGET_DATE,),
        ).fetchone()
        conn.close()

        assert row is not None
        assert row[0] == TARGET_DATE
        assert row[1] in ("ceiling", "overheat", "neutral", "weak", "sellin", "bottom")

    def test_writes_margin_trading_weekly(self, tmp_path):
        db_path = _make_db(tmp_path)
        run_market_pressure(db_path, TARGET_DATE)

        conn = sqlite3.connect(db_path)
        row = conn.execute(
            "SELECT market_code, margin_buy_balance FROM margin_trading_weekly"
        ).fetchone()
        conn.close()

        assert row is not None
        assert row[0] == "ALL"
        # 3銘柄 × 1,000,000
        assert row[1] == pytest.approx(3_000_000.0)

    def test_returns_0_without_margin_data(self, tmp_path):
        db_path = str(tmp_path / "empty.db")
        init_sqlite(db_path)
        migrate(db_path)
        result = run_market_pressure(db_path, TARGET_DATE)
        assert result == 0

    def test_idempotent(self, tmp_path):
        db_path = _make_db(tmp_path)
        run_market_pressure(db_path, TARGET_DATE)
        run_market_pressure(db_path, TARGET_DATE)

        conn = sqlite3.connect(db_path)
        cnt = conn.execute(
            "SELECT COUNT(*) FROM market_pressure_daily WHERE date = ?", (TARGET_DATE,)
        ).fetchone()[0]
        conn.close()
        assert cnt == 1


# ─────────────────────────────────────────────────────────────────────────────
# 3. generate_credit_overheating_signal
# ─────────────────────────────────────────────────────────────────────────────

def _make_conn_with_pressure(db_path: str, pl_ratio: float, buy_growth_4w: float) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        INSERT OR REPLACE INTO market_pressure_daily
            (date, pl_ratio, pl_zone, buy_growth_4w, margin_ratio, margin_ratio_trend, signal_flags)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (TARGET_DATE, pl_ratio, _calc_pl_zone(pl_ratio), buy_growth_4w, 5.0, 0.1,
         json.dumps({"credit_overheating": False})),
    )
    conn.commit()
    return conn


class TestGenerateCreditOverheatingSignal:
    def test_fires_when_conditions_met(self, tmp_path):
        db_path = _make_db(tmp_path)
        conn = _make_conn_with_pressure(db_path, pl_ratio=0.15, buy_growth_4w=0.10)
        n = generate_credit_overheating_signal(conn, TARGET_DATE)
        conn.close()
        assert n == 1

    def test_does_not_fire_when_pl_ratio_low(self, tmp_path):
        db_path = _make_db(tmp_path)
        conn = _make_conn_with_pressure(db_path, pl_ratio=0.08, buy_growth_4w=0.10)
        n = generate_credit_overheating_signal(conn, TARGET_DATE)
        conn.close()
        assert n == 0

    def test_does_not_fire_when_buy_growth_low(self, tmp_path):
        db_path = _make_db(tmp_path)
        conn = _make_conn_with_pressure(db_path, pl_ratio=0.15, buy_growth_4w=0.03)
        n = generate_credit_overheating_signal(conn, TARGET_DATE)
        conn.close()
        assert n == 0

    def test_signal_is_bearish(self, tmp_path):
        db_path = _make_db(tmp_path)
        conn = _make_conn_with_pressure(db_path, pl_ratio=0.15, buy_growth_4w=0.10)
        generate_credit_overheating_signal(conn, TARGET_DATE)

        row = conn.execute(
            "SELECT direction, signal_type FROM signals WHERE date = ?", (TARGET_DATE,)
        ).fetchone()
        conn.close()

        assert row is not None
        assert row[0] == "bearish"
        assert row[1] == "credit_overheating"

    def test_updates_signal_flags(self, tmp_path):
        db_path = _make_db(tmp_path)
        conn = _make_conn_with_pressure(db_path, pl_ratio=0.15, buy_growth_4w=0.10)
        generate_credit_overheating_signal(conn, TARGET_DATE)

        row = conn.execute(
            "SELECT signal_flags FROM market_pressure_daily WHERE date = ?", (TARGET_DATE,)
        ).fetchone()
        conn.close()

        flags = json.loads(row[0])
        assert flags["credit_overheating"] is True

    def test_confidence_formula(self, tmp_path):
        pl = 0.15   # 0.15 - 0.12 = 0.03
        bg = 0.10   # 0.10 - 0.08 = 0.02
        expected = min(1.0, 0.5 + min(0.4, 0.03 * 4 + 0.02 * 2))

        db_path = _make_db(tmp_path)
        conn = _make_conn_with_pressure(db_path, pl_ratio=pl, buy_growth_4w=bg)
        generate_credit_overheating_signal(conn, TARGET_DATE)

        row = conn.execute(
            "SELECT confidence FROM signals WHERE date = ?", (TARGET_DATE,)
        ).fetchone()
        conn.close()
        assert row[0] == pytest.approx(expected, abs=1e-4)

    def test_no_data_returns_0(self, tmp_path):
        db_path = _make_db(tmp_path)
        conn = sqlite3.connect(db_path)
        n = generate_credit_overheating_signal(conn, TARGET_DATE)
        conn.close()
        assert n == 0


# ─────────────────────────────────────────────────────────────────────────────
# 4. GET /api/market-pressure/timeseries
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def api_client(tmp_path, monkeypatch):
    """FastAPI テストクライアント (moto S3 + stocks.db をローカルに向ける)。"""
    db_path = _make_db(tmp_path)
    run_market_pressure(db_path, TARGET_DATE)

    with mock_aws():
        s3 = boto3.client("s3", region_name="ap-northeast-1")
        s3.create_bucket(
            Bucket=BUCKET,
            CreateBucketConfiguration={"LocationConstraint": "ap-northeast-1"},
        )
        s3.upload_file(db_path, BUCKET, "data/stocks.db")

        monkeypatch.setenv("SQLITE_PATH", db_path)

        import importlib
        import src.api.storage as st
        importlib.reload(st)

        from src.api.main import app
        client = TestClient(app, raise_server_exceptions=True)

        yield client


class TestMarketPressureTimeseriesEndpoint:
    def test_returns_200(self, api_client):
        resp = api_client.get("/api/market-pressure/timeseries")
        assert resp.status_code == 200

    def test_returns_expected_keys(self, api_client):
        resp = api_client.get("/api/market-pressure/timeseries")
        data = resp.json()
        for key in ("dates", "pl_ratio", "pl_zone", "buy_growth_4w",
                    "margin_ratio", "margin_ratio_trend", "signal_flags"):
            assert key in data, f"Missing key: {key}"

    def test_dates_ascending(self, api_client):
        resp = api_client.get("/api/market-pressure/timeseries")
        data = resp.json()
        dates = data["dates"]
        if len(dates) > 1:
            assert dates == sorted(dates)

    def test_days_param_limits_result(self, api_client):
        resp = api_client.get("/api/market-pressure/timeseries?days=1")
        data = resp.json()
        assert len(data["dates"]) <= 1

    def test_empty_db_returns_empty(self, tmp_path, monkeypatch):
        """データなしの場合は空配列を返す。"""
        db_path = str(tmp_path / "empty.db")
        init_sqlite(db_path)
        migrate(db_path)

        with mock_aws():
            s3 = boto3.client("s3", region_name="ap-northeast-1")
            s3.create_bucket(
                Bucket=BUCKET,
                CreateBucketConfiguration={"LocationConstraint": "ap-northeast-1"},
            )
            s3.upload_file(db_path, BUCKET, "data/stocks.db")

            monkeypatch.setenv("SQLITE_PATH", db_path)

            import importlib
            import src.api.storage as st
            importlib.reload(st)

            from src.api.main import app
            client = TestClient(app)
            resp = client.get("/api/market-pressure/timeseries")

        assert resp.status_code == 200
        data = resp.json()
        assert data["dates"] == []
