"""物件 CRUD エンドポイントのテスト"""
import os
import sqlite3
import sys
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture(autouse=True)
def setup_env(monkeypatch, tmp_path):
    """テスト用環境変数とDB設定。"""
    db_path = str(tmp_path / "hazardbrief.db")
    from scripts.init_sqlite import init_sqlite
    init_sqlite(db_path)
    monkeypatch.setenv("SQLITE_PATH", db_path)
    monkeypatch.setenv("S3_BUCKET", "")  # ローカルモード


@pytest.fixture
def client():
    """FastAPI テストクライアント。"""
    from src.api.main import app
    return TestClient(app)


@pytest.fixture
def client_with_data(tmp_path, monkeypatch):
    """テストデータ入りのクライアント。"""
    db_path = str(tmp_path / "hazardbrief.db")
    from scripts.init_sqlite import init_sqlite
    init_sqlite(db_path)
    monkeypatch.setenv("SQLITE_PATH", db_path)
    monkeypatch.setenv("S3_BUCKET", "")

    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO companies (id, name, plan) VALUES ('c1', 'テスト不動産', 'free')"
    )
    conn.execute(
        """
        INSERT INTO properties
            (id, address, latitude, longitude, property_name, company_id)
        VALUES
            ('p1', '東京都千代田区丸の内1-1-1', 35.6812, 139.7671, 'テスト物件', 'c1')
        """
    )
    conn.commit()
    conn.close()

    from src.api.main import app
    return TestClient(app)


class TestListProperties:
    def test_returns_empty_list_when_no_properties(self, client):
        resp = client.get("/api/properties")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_returns_properties(self, client_with_data):
        resp = client_with_data.get("/api/properties")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["id"] == "p1"
        assert data[0]["address"] == "東京都千代田区丸の内1-1-1"

    def test_filter_by_company_id(self, client_with_data):
        resp = client_with_data.get("/api/properties", params={"company_id": "c1"})
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    def test_filter_by_nonexistent_company_returns_empty(self, client_with_data):
        resp = client_with_data.get("/api/properties", params={"company_id": "nonexistent"})
        assert resp.status_code == 200
        assert resp.json() == []


class TestGetProperty:
    def test_returns_property(self, client_with_data):
        resp = client_with_data.get("/api/properties/p1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == "p1"
        assert data["latitude"] == pytest.approx(35.6812)
        assert data["longitude"] == pytest.approx(139.7671)

    def test_returns_404_for_nonexistent(self, client):
        resp = client.get("/api/properties/nonexistent")
        assert resp.status_code == 404


class TestCreateProperty:
    def test_create_property_with_geocoding(self, client):
        """ジオコーディングが成功する場合。"""
        mock_geo = {
            "latitude": 35.6812,
            "longitude": 139.7671,
            "display_name": "東京都千代田区丸の内",
        }
        with patch(
            "src.api.routers.properties.geocode_address",
            new_callable=AsyncMock,
            return_value=mock_geo,
        ):
            resp = client.post(
                "/api/properties",
                json={"address": "東京都千代田区丸の内1-1-1"},
            )

        assert resp.status_code == 201
        data = resp.json()
        assert data["latitude"] == pytest.approx(35.6812)
        assert data["longitude"] == pytest.approx(139.7671)
        assert "id" in data

    def test_create_property_without_geocoding_failure(self, client):
        """ジオコーディングが失敗しても登録できる（lat/lon=NULL）。"""
        with patch(
            "src.api.routers.properties.geocode_address",
            new_callable=AsyncMock,
            return_value=None,
        ):
            resp = client.post(
                "/api/properties",
                json={"address": "不明な住所99999"},
            )

        assert resp.status_code == 201
        data = resp.json()
        assert data["latitude"] is None
        assert data["longitude"] is None

    def test_create_property_with_manual_coordinates(self, client):
        """緯度経度を手動で指定する場合はジオコーディングをスキップ。"""
        resp = client.post(
            "/api/properties",
            json={
                "address": "東京都千代田区丸の内1-1-1",
                "latitude": 35.6812,
                "longitude": 139.7671,
                "property_name": "丸の内ビル",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["property_name"] == "丸の内ビル"


class TestDeleteProperty:
    def test_delete_existing_property(self, client_with_data):
        resp = client_with_data.delete("/api/properties/p1")
        assert resp.status_code == 200
        assert resp.json()["status"] == "deleted"

        # 削除確認
        resp2 = client_with_data.get("/api/properties/p1")
        assert resp2.status_code == 404

    def test_delete_nonexistent_returns_404(self, client):
        resp = client.delete("/api/properties/nonexistent")
        assert resp.status_code == 404
