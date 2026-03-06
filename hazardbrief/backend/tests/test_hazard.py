"""ハザードデータ取得テスト (外部APIはモック)"""
import json
import os
import sqlite3
import sys
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

MOCK_FLOOD = {
    "level": "medium",
    "depth": "2",
    "depth_label": "0.5〜1.0m未満（床上浸水）",
    "river_name": "テスト川",
    "source": "国土交通省 不動産情報ライブラリ",
    "available": True,
}

MOCK_LANDSLIDE = {
    "level": "low",
    "zone_type": "none",
    "zone_label": "警戒区域外",
    "disaster_type": None,
    "disaster_type_label": None,
    "source": "国土交通省 不動産情報ライブラリ",
    "available": True,
}

MOCK_TSUNAMI = {
    "level": "low",
    "depth": "0",
    "depth_label": "浸水なし（想定区域外）",
    "source": "国土交通省 不動産情報ライブラリ",
    "available": True,
}

MOCK_GROUND = {
    "level": "low",
    "elevation": 15.5,
    "description": "標高が高く、地盤リスクは相対的に低い傾向です",
    "liquefaction_note": "標高から判断する限り液状化リスクは標準的です。",
    "source": "国土地理院 標高API",
    "available": True,
}


@pytest.fixture(autouse=True)
def setup_env(monkeypatch, tmp_path):
    """テスト用環境変数とDB設定。"""
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
    # 緯度経度なし物件
    conn.execute(
        """
        INSERT INTO properties
            (id, address, property_name, company_id)
        VALUES
            ('p2', '住所不明', '緯度経度なし物件', 'c1')
        """
    )
    conn.commit()
    conn.close()


@pytest.fixture
def client():
    from src.api.main import app
    return TestClient(app)


class TestGetHazard:
    def test_returns_404_for_nonexistent_property(self, client):
        resp = client.get("/api/hazard/nonexistent")
        assert resp.status_code == 404

    def test_returns_422_when_no_coordinates(self, client):
        resp = client.get("/api/hazard/p2")
        assert resp.status_code == 422

    def test_fetches_hazard_data_from_external_api(self, client):
        """外部APIをモックしてハザードデータを取得するテスト。"""
        mock_result = {
            "flood_risk": MOCK_FLOOD,
            "landslide_risk": MOCK_LANDSLIDE,
            "tsunami_risk": MOCK_TSUNAMI,
            "ground_risk": MOCK_GROUND,
            "risk_summary": {
                "overall_level": "medium",
                "levels": {
                    "flood": "medium",
                    "landslide": "low",
                    "tsunami": "low",
                    "ground": "low",
                },
                "unavailable_count": 0,
                "has_partial_data": False,
                "disclaimer": "テスト用免責事項",
            },
        }

        with patch(
            "src.api.routers.hazard.fetch_all_hazards",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            resp = client.get("/api/hazard/p1")

        assert resp.status_code == 200
        data = resp.json()
        assert data["property_id"] == "p1"
        assert data["flood_risk"]["level"] == "medium"
        assert data["landslide_risk"]["level"] == "low"
        assert data["tsunami_risk"]["level"] == "low"
        assert data["ground_risk"]["level"] == "low"
        assert data["risk_summary"]["overall_level"] == "medium"
        assert data["from_cache"] is False

    def test_returns_cached_data_on_second_request(self, client):
        """2回目のリクエストはキャッシュから返す。"""
        mock_result = {
            "flood_risk": MOCK_FLOOD,
            "landslide_risk": MOCK_LANDSLIDE,
            "tsunami_risk": MOCK_TSUNAMI,
            "ground_risk": MOCK_GROUND,
            "risk_summary": {
                "overall_level": "medium",
                "levels": {"flood": "medium", "landslide": "low", "tsunami": "low", "ground": "low"},
                "unavailable_count": 0,
                "has_partial_data": False,
                "disclaimer": "テスト",
            },
        }

        with patch(
            "src.api.routers.hazard.fetch_all_hazards",
            new_callable=AsyncMock,
            return_value=mock_result,
        ) as mock_fetch:
            # 1回目 (API呼び出し)
            resp1 = client.get("/api/hazard/p1")
            assert resp1.status_code == 200
            assert resp1.json()["from_cache"] is False

            # 2回目 (キャッシュ)
            resp2 = client.get("/api/hazard/p1")
            assert resp2.status_code == 200
            assert resp2.json()["from_cache"] is True

            # 外部API呼び出しは1回のみ
            assert mock_fetch.call_count == 1

    def test_force_refresh_bypasses_cache(self, client):
        """force_refresh=true でキャッシュをバイパスする。"""
        mock_result = {
            "flood_risk": MOCK_FLOOD,
            "landslide_risk": MOCK_LANDSLIDE,
            "tsunami_risk": MOCK_TSUNAMI,
            "ground_risk": MOCK_GROUND,
            "risk_summary": {
                "overall_level": "medium",
                "levels": {"flood": "medium", "landslide": "low", "tsunami": "low", "ground": "low"},
                "unavailable_count": 0,
                "has_partial_data": False,
                "disclaimer": "テスト",
            },
        }

        with patch(
            "src.api.routers.hazard.fetch_all_hazards",
            new_callable=AsyncMock,
            return_value=mock_result,
        ) as mock_fetch:
            client.get("/api/hazard/p1")
            client.get("/api/hazard/p1", params={"force_refresh": "true"})

            # 2回呼び出されることを確認
            assert mock_fetch.call_count == 2


class TestGetReport:
    def test_returns_404_when_no_hazard_report(self, client):
        """ハザードレポートなしの場合は 404。"""
        resp = client.get("/api/report/p1")
        assert resp.status_code == 404

    def test_returns_report_when_hazard_data_exists(self, client, tmp_path, monkeypatch):
        """ハザードレポートが存在する場合はレポートを返す。"""
        import os
        db_path = str(tmp_path / "hazardbrief.db")
        monkeypatch.setenv("SQLITE_PATH", db_path)

        # DB再作成 (autouse fixture が先に作ってるのでパスが違う場合は注意)
        # ここでは setup_env の db を使う
        db_path = os.environ["SQLITE_PATH"]
        conn = sqlite3.connect(db_path)
        conn.execute(
            """
            INSERT INTO hazard_reports
                (property_id, flood_risk, landslide_risk, tsunami_risk, ground_risk,
                 risk_summary, fetched_at, expires_at)
            VALUES
                (?, ?, ?, ?, ?, ?, datetime('now'), datetime('now', '+90 days'))
            """,
            (
                "p1",
                json.dumps(MOCK_FLOOD),
                json.dumps(MOCK_LANDSLIDE),
                json.dumps(MOCK_TSUNAMI),
                json.dumps(MOCK_GROUND),
                json.dumps({
                    "overall_level": "medium",
                    "levels": {"flood": "medium", "landslide": "low", "tsunami": "low", "ground": "low"},
                    "unavailable_count": 0,
                    "has_partial_data": False,
                    "disclaimer": "テスト用免責事項",
                }),
            ),
        )
        conn.commit()
        conn.close()

        resp = client.get("/api/report/p1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["property"]["id"] == "p1"
        assert len(data["report"]["cards"]) == 4
        assert "disclaimer" in data

        # カードの内容確認
        flood_card = next(c for c in data["report"]["cards"] if c["risk_type"] == "flood")
        assert flood_card["level"] == "medium"
        assert flood_card["level_label"] == "中"
        assert "mitigation" in flood_card
