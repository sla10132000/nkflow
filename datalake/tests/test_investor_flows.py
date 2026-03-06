"""fetch_investor_flows のユニットテスト (J-Quants API を unittest.mock でモック)"""
import sqlite3
import sys
import os
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scripts.init_sqlite import init_sqlite
from src.ingestion.jquants import fetch_investor_flows, _normalize_date


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def db_conn(tmp_path):
    """テスト用 SQLite (スキーマ初期化済み)"""
    db_path = str(tmp_path / "test.db")
    init_sqlite(db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    yield conn
    conn.close()


@pytest.fixture
def mock_client():
    """J-Quants APIクライアントのモック (ClientV2 互換)"""
    client = MagicMock()
    client._api_key = "test-api-key-12345"
    return client


def _make_api_response(start="20260101", end="20260107"):
    """trades_spec API の典型的なレスポンスを生成する。"""
    return {
        "trades_spec": [
            {
                "PublishedDate": "20260114",
                "StartDate": start,
                "EndDate": end,
                "Section": "TSEPrime",
                "ForeignersSales": 5_000_000.0,
                "ForeignersPurchases": 8_000_000.0,
                "ForeignersBalance": 3_000_000.0,
                "IndividualsSales": 6_000_000.0,
                "IndividualsPurchases": 4_000_000.0,
                "IndividualsBalance": -2_000_000.0,
                "InvestmentTrustsSales": 1_000_000.0,
                "InvestmentTrustsPurchases": 1_200_000.0,
                "InvestmentTrustsBalance": 200_000.0,
                "TrustBanksSales": 800_000.0,
                "TrustBanksPurchases": 900_000.0,
                "TrustBanksBalance": 100_000.0,
                "BusinessCompaniesSales": 500_000.0,
                "BusinessCompaniesPurchases": 600_000.0,
                "BusinessCompaniesBalance": 100_000.0,
            }
        ]
    }


# ── _normalize_date テスト ─────────────────────────────────────────────────

class TestNormalizeDate:
    def test_yyyymmdd_to_iso(self):
        assert _normalize_date("20260101") == "2026-01-01"

    def test_iso_passthrough(self):
        assert _normalize_date("2026-01-01") == "2026-01-01"

    def test_empty_string(self):
        assert _normalize_date("") == ""

    def test_none_like_empty(self):
        assert _normalize_date(None) == ""

    def test_invalid_format(self):
        assert _normalize_date("invalid") == ""


# ── fetch_investor_flows テスト ───────────────────────────────────────────

class TestFetchInvestorFlows:
    def test_normal_response_saves_all_investor_types(self, db_conn, mock_client):
        """正常レスポンス: 5種類の投資主体が保存されること"""
        mock_resp = MagicMock()
        mock_resp.json.return_value = _make_api_response()
        mock_resp.raise_for_status.return_value = None

        with patch("src.ingestion.jquants.requests.get", return_value=mock_resp) as mock_get:
            count = fetch_investor_flows(db_conn, "2026-01-01", "2026-01-07", client=mock_client)

        assert count == 5  # 5 investor_types

        # 各投資主体が正しく保存されているか
        rows = db_conn.execute(
            "SELECT * FROM investor_flow_weekly ORDER BY investor_type"
        ).fetchall()
        investor_types = {r["investor_type"] for r in rows}
        assert investor_types == {
            "foreigners", "individuals", "investment_trusts",
            "trust_banks", "business_cos"
        }

    def test_foreigners_balance_stored_correctly(self, db_conn, mock_client):
        """海外の差引値が正しく保存されること (手計算で検証)"""
        mock_resp = MagicMock()
        mock_resp.json.return_value = _make_api_response()
        mock_resp.raise_for_status.return_value = None

        with patch("src.ingestion.jquants.requests.get", return_value=mock_resp):
            fetch_investor_flows(db_conn, "2026-01-01", "2026-01-07", client=mock_client)

        row = db_conn.execute(
            "SELECT * FROM investor_flow_weekly WHERE investor_type = 'foreigners'"
        ).fetchone()
        assert row is not None
        assert row["week_start"] == "2026-01-01"
        assert row["week_end"] == "2026-01-07"
        assert row["sales"] == pytest.approx(5_000_000.0)
        assert row["purchases"] == pytest.approx(8_000_000.0)
        assert row["balance"] == pytest.approx(3_000_000.0)
        assert row["published_date"] == "2026-01-14"
        assert row["section"] == "TSEPrime"

    def test_individuals_negative_balance(self, db_conn, mock_client):
        """個人の差引がマイナス値 (-2,000,000) で保存されること"""
        mock_resp = MagicMock()
        mock_resp.json.return_value = _make_api_response()
        mock_resp.raise_for_status.return_value = None

        with patch("src.ingestion.jquants.requests.get", return_value=mock_resp):
            fetch_investor_flows(db_conn, "2026-01-01", "2026-01-07", client=mock_client)

        row = db_conn.execute(
            "SELECT balance FROM investor_flow_weekly WHERE investor_type = 'individuals'"
        ).fetchone()
        assert row["balance"] == pytest.approx(-2_000_000.0)

    def test_empty_response_returns_zero(self, db_conn, mock_client):
        """レスポンスが空の場合は 0 を返すこと"""
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"trades_spec": []}
        mock_resp.raise_for_status.return_value = None

        with patch("src.ingestion.jquants.requests.get", return_value=mock_resp):
            count = fetch_investor_flows(db_conn, "2026-01-01", "2026-01-07", client=mock_client)

        assert count == 0

    def test_http_400_returns_zero(self, db_conn, mock_client):
        """HTTP 400 エラーはデータなしとして 0 を返すこと"""
        import requests as _requests
        mock_resp = MagicMock()
        http_err = _requests.exceptions.HTTPError(response=MagicMock(status_code=400))
        mock_resp.raise_for_status.side_effect = http_err

        with patch("src.ingestion.jquants.requests.get", return_value=mock_resp):
            count = fetch_investor_flows(db_conn, "2026-01-01", "2026-01-07", client=mock_client)

        assert count == 0

    def test_api_called_with_correct_params(self, db_conn, mock_client):
        """API が正しいパラメータで呼び出されること"""
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"trades_spec": []}
        mock_resp.raise_for_status.return_value = None

        with patch("src.ingestion.jquants.requests.get", return_value=mock_resp) as mock_get:
            fetch_investor_flows(
                db_conn, "2026-01-01", "2026-01-31",
                section="TSEPrime", client=mock_client
            )

        call_kwargs = mock_get.call_args
        params = call_kwargs.kwargs.get("params") or call_kwargs[1].get("params") or call_kwargs[0][1]
        # params は dict 形式
        assert params.get("section") == "TSEPrime"
        assert "20260101" in params.get("from", "") or params.get("from") == "20260101"

    def test_api_key_used_in_header(self, db_conn, mock_client):
        """x-api-key ヘッダーで認証が行われること"""
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"trades_spec": []}
        mock_resp.raise_for_status.return_value = None

        with patch("src.ingestion.jquants.requests.get", return_value=mock_resp) as mock_get:
            fetch_investor_flows(db_conn, "2026-01-01", "2026-01-07", client=mock_client)

        call_kwargs = mock_get.call_args
        headers = call_kwargs.kwargs.get("headers") or call_kwargs[1].get("headers")
        assert headers is not None
        assert headers.get("x-api-key") == "test-api-key-12345"

    def test_insert_or_replace_idempotent(self, db_conn, mock_client):
        """同じデータを2回投入しても重複しないこと (INSERT OR REPLACE)"""
        mock_resp = MagicMock()
        mock_resp.json.return_value = _make_api_response()
        mock_resp.raise_for_status.return_value = None

        with patch("src.ingestion.jquants.requests.get", return_value=mock_resp):
            fetch_investor_flows(db_conn, "2026-01-01", "2026-01-07", client=mock_client)
            fetch_investor_flows(db_conn, "2026-01-01", "2026-01-07", client=mock_client)

        count = db_conn.execute(
            "SELECT COUNT(*) FROM investor_flow_weekly"
        ).fetchone()[0]
        assert count == 5  # 5種類のみ (重複なし)

    def test_multiple_weeks_saved(self, db_conn, mock_client):
        """複数週のデータが全て保存されること"""
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "trades_spec": [
                {
                    "PublishedDate": "20260114",
                    "StartDate": "20260101", "EndDate": "20260107",
                    "Section": "TSEPrime",
                    "ForeignersSales": 1.0, "ForeignersPurchases": 2.0, "ForeignersBalance": 1.0,
                    "IndividualsSales": 2.0, "IndividualsPurchases": 1.0, "IndividualsBalance": -1.0,
                    "InvestmentTrustsSales": None, "InvestmentTrustsPurchases": None, "InvestmentTrustsBalance": None,
                    "TrustBanksSales": None, "TrustBanksPurchases": None, "TrustBanksBalance": None,
                    "BusinessCompaniesSales": None, "BusinessCompaniesPurchases": None, "BusinessCompaniesBalance": None,
                },
                {
                    "PublishedDate": "20260121",
                    "StartDate": "20260108", "EndDate": "20260114",
                    "Section": "TSEPrime",
                    "ForeignersSales": 3.0, "ForeignersPurchases": 4.0, "ForeignersBalance": 1.0,
                    "IndividualsSales": 4.0, "IndividualsPurchases": 3.0, "IndividualsBalance": -1.0,
                    "InvestmentTrustsSales": None, "InvestmentTrustsPurchases": None, "InvestmentTrustsBalance": None,
                    "TrustBanksSales": None, "TrustBanksPurchases": None, "TrustBanksBalance": None,
                    "BusinessCompaniesSales": None, "BusinessCompaniesPurchases": None, "BusinessCompaniesBalance": None,
                },
            ]
        }
        mock_resp.raise_for_status.return_value = None

        with patch("src.ingestion.jquants.requests.get", return_value=mock_resp):
            count = fetch_investor_flows(db_conn, "2026-01-01", "2026-01-14", client=mock_client)

        # 2週 × 2種類 (None のみの投資主体は保存しない)
        assert count == 4

        weeks = db_conn.execute(
            "SELECT DISTINCT week_end FROM investor_flow_weekly ORDER BY week_end"
        ).fetchall()
        assert len(weeks) == 2
