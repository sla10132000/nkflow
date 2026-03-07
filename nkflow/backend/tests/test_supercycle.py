"""Phase 27: スーパーサイクル分析 API テスト

テスト対象:
  - src.api.routers.supercycle (全3エンドポイント)
  - src.api.supercycle_config (フェーズ定義・シナリオ)
"""
import os
import sqlite3
import sys
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


BUCKET = "test-nkflow-bucket"
TODAY = date.today().isoformat()


# ─────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────


@pytest.fixture(autouse=True)
def env(monkeypatch, tmp_path):
    """テスト用環境変数を設定する。"""
    monkeypatch.setenv("S3_BUCKET", BUCKET)
    monkeypatch.setenv("AWS_DEFAULT_REGION", "ap-northeast-1")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "stocks.db"))
    monkeypatch.setenv("PORTFOLIO_DB_PATH", str(tmp_path / "portfolio.db"))
    yield


@pytest.fixture()
def db_with_commodity_data(tmp_path, monkeypatch) -> str:
    """us_indices テーブルにスーパーサイクル用テストデータを INSERT する。"""
    db_path = str(tmp_path / "stocks.db")
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS us_indices (
            date TEXT NOT NULL,
            ticker TEXT NOT NULL,
            name TEXT,
            open REAL,
            high REAL,
            low REAL,
            close REAL,
            volume INTEGER,
            PRIMARY KEY (date, ticker)
        )
        """
    )

    # スーパーサイクル対象ティッカーのテストデータ (5日分)
    sc_tickers = [
        ("GC=F", "Gold Futures", 2000.0),
        ("CL=F", "WTI Crude Oil", 80.0),
        ("SI=F", "Silver Futures", 25.0),
        ("HG=F", "Copper Futures", 4.0),
        ("NG=F", "Natural Gas", 3.5),
        ("ZW=F", "Wheat Futures", 600.0),
        ("ZC=F", "Corn Futures", 450.0),
        ("URA", "Global X Uranium ETF", 50.0),
        ("ALI=F", "Aluminum Futures", 3200.0),
        ("LIT", "Global X Lithium & Battery Tech ETF", 70.0),
    ]

    rows = []
    for i in range(5):
        day = (date.today() - timedelta(days=5 - i)).isoformat()
        for ticker, name, base_close in sc_tickers:
            close = base_close * (1 + i * 0.01)  # 1% 日次上昇
            rows.append((day, ticker, name, close * 0.99, close * 1.01, close * 0.98, close, 100000))

    conn.executemany(
        "INSERT OR REPLACE INTO us_indices (date, ticker, name, open, high, low, close, volume) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()
    conn.close()
    monkeypatch.setenv("SQLITE_PATH", db_path)
    return db_path


@pytest.fixture()
def client(db_with_commodity_data, monkeypatch):
    """TestClient を返す (DB 準備済み)。"""
    import importlib

    import src.api.storage as storage_mod

    importlib.reload(storage_mod)

    # ensure_db が S3 アクセスしないよう、ローカル DB パスを返すよう差し替える
    monkeypatch.setattr(storage_mod, "ensure_db", lambda: db_with_commodity_data)

    from src.api.main import app

    return TestClient(app)


# ─────────────────────────────────────────────
# /api/supercycle/overview
# ─────────────────────────────────────────────


class TestSupercycleOverview:
    def test_returns_200(self, client):
        resp = client.get("/api/supercycle/overview")
        assert resp.status_code == 200

    def test_response_structure(self, client):
        data = client.get("/api/supercycle/overview").json()
        assert "phases" in data
        assert "sectors" in data
        assert "scenarios" in data
        assert "correlations" in data
        assert "updated" in data

    def test_phases_has_4_entries(self, client):
        data = client.get("/api/supercycle/overview").json()
        assert len(data["phases"]) == 4
        for phase_id in ["1", "2", "3", "4"]:
            assert phase_id in data["phases"]
            phase = data["phases"][phase_id]
            assert "name" in phase
            assert "color" in phase

    def test_sectors_has_5_entries(self, client):
        data = client.get("/api/supercycle/overview").json()
        sector_ids = [s["id"] for s in data["sectors"]]
        assert "energy" in sector_ids
        assert "base_metals" in sector_ids
        assert "precious_metals" in sector_ids
        assert "battery_metals" in sector_ids
        assert "agriculture" in sector_ids

    def test_commodity_has_price_data(self, client):
        data = client.get("/api/supercycle/overview").json()
        # エネルギーセクターの CL=F に price が入っていること
        energy = next(s for s in data["sectors"] if s["id"] == "energy")
        cl = next(c for c in energy["commodities"] if c["ticker"] == "CL=F")
        assert cl["close"] is not None
        assert cl["close"] > 0

    def test_commodity_has_phase_position(self, client):
        data = client.get("/api/supercycle/overview").json()
        for sector in data["sectors"]:
            assert "phase" in sector
            assert "position" in sector
            assert 1 <= sector["phase"] <= 4
            for commodity in sector["commodities"]:
                assert "phase" in commodity
                assert "position" in commodity

    def test_scenarios_count(self, client):
        data = client.get("/api/supercycle/overview").json()
        assert len(data["scenarios"]) == 3
        probs = [s["probability"] for s in data["scenarios"]]
        assert sum(probs) == 100

    def test_etf_flag(self, client):
        data = client.get("/api/supercycle/overview").json()
        energy = next(s for s in data["sectors"] if s["id"] == "energy")
        ura = next(c for c in energy["commodities"] if c["ticker"] == "URA")
        cl = next(c for c in energy["commodities"] if c["ticker"] == "CL=F")
        assert ura["is_etf"] is True
        assert cl["is_etf"] is False


# ─────────────────────────────────────────────
# /api/supercycle/sector-returns
# ─────────────────────────────────────────────


class TestSupercycleSectorReturns:
    def test_returns_200_energy(self, client):
        resp = client.get("/api/supercycle/sector-returns?sector=energy")
        assert resp.status_code == 200

    def test_invalid_sector_returns_400(self, client):
        resp = client.get("/api/supercycle/sector-returns?sector=invalid_sector")
        assert resp.status_code == 400

    def test_response_structure(self, client):
        data = client.get("/api/supercycle/sector-returns?sector=energy").json()
        assert data["sector"] == "energy"
        assert "label" in data
        assert "series" in data

    def test_series_has_energy_tickers(self, client):
        data = client.get("/api/supercycle/sector-returns?sector=energy").json()
        tickers = [s["ticker"] for s in data["series"]]
        assert "CL=F" in tickers
        assert "NG=F" in tickers
        assert "URA" in tickers

    def test_normalized_to_base_100(self, client):
        data = client.get("/api/supercycle/sector-returns?sector=energy&days=30").json()
        for series in data["series"]:
            if series["data"]:
                # 最初のデータポイントが 100.0 であること
                assert series["data"][0]["value"] == 100.0

    def test_all_sectors_valid(self, client):
        sectors = ["energy", "base_metals", "precious_metals", "battery_metals", "agriculture"]
        for sector in sectors:
            resp = client.get(f"/api/supercycle/sector-returns?sector={sector}")
            assert resp.status_code == 200, f"Failed for sector: {sector}"


# ─────────────────────────────────────────────
# /api/supercycle/performance
# ─────────────────────────────────────────────


class TestSupercyclePerformance:
    def test_returns_200(self, client):
        resp = client.get("/api/supercycle/performance")
        assert resp.status_code == 200

    def test_returns_list(self, client):
        data = client.get("/api/supercycle/performance").json()
        assert isinstance(data, list)
        assert len(data) > 0

    def test_item_structure(self, client):
        data = client.get("/api/supercycle/performance").json()
        item = data[0]
        assert "ticker" in item
        assert "label" in item
        assert "sector_id" in item
        assert "returns" in item
        returns = item["returns"]
        for horizon in ["1m", "3m", "6m", "1y", "3y", "5y"]:
            assert horizon in returns

    def test_all_sc_tickers_present(self, client):
        data = client.get("/api/supercycle/performance").json()
        tickers = {item["ticker"] for item in data}
        expected = {"GC=F", "CL=F", "SI=F", "HG=F", "NG=F", "ZW=F", "ZC=F", "URA", "ALI=F", "LIT"}
        assert expected.issubset(tickers)

    def test_short_horizon_returns_value(self, client):
        """5日分のデータがあれば 1M リターンは null だが、データ範囲内は計算される。"""
        data = client.get("/api/supercycle/performance").json()
        # 5日分しかないので 1m (21日) 以上は null
        for item in data:
            assert item["returns"]["1m"] is None or isinstance(item["returns"]["1m"], float)

    def test_sector_id_mapping(self, client):
        data = client.get("/api/supercycle/performance").json()
        gold = next(item for item in data if item["ticker"] == "GC=F")
        assert gold["sector_id"] == "precious_metals"
        crude = next(item for item in data if item["ticker"] == "CL=F")
        assert crude["sector_id"] == "energy"
