"""Phase 15: ポートフォリオ連携 テスト

テスト対象:
  - migrate_phase15.init_portfolio_db
  - src.api.portfolio_storage (ensure_portfolio_db, writable_portfolio_connection)
  - src.api.routers.portfolio (全エンドポイント)
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
from scripts.migrate_phase15 import init_portfolio_db

BUCKET = "test-nkflow-bucket"
TODAY = date.today().isoformat()
RECENT = (date.today() - timedelta(days=3)).isoformat()


def _upload_portfolio_db(db_path: str) -> None:
    """テスト用: ローカルの portfolio.db を moto S3 にアップロードする。"""
    s3 = boto3.client("s3", region_name="ap-northeast-1")
    s3.upload_file(db_path, BUCKET, "data/portfolio.db")


# ─────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────

@pytest.fixture(autouse=True)
def aws_env(monkeypatch, tmp_path):
    """テスト用 AWS / SQLite 環境変数を設定する。"""
    monkeypatch.setenv("S3_BUCKET", BUCKET)
    monkeypatch.setenv("AWS_DEFAULT_REGION", "ap-northeast-1")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_SECURITY_TOKEN", "testing")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "testing")
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "stocks.db"))
    monkeypatch.setenv("PORTFOLIO_DB_PATH", str(tmp_path / "portfolio.db"))


@pytest.fixture
def stocks_db(tmp_path):
    """stocks.db (テスト用データ付き)"""
    db_path = str(tmp_path / "stocks.db")
    init_sqlite(db_path)
    conn = sqlite3.connect(db_path)
    conn.execute("INSERT INTO stocks VALUES ('72030', 'トヨタ自動車', '輸送用機器')")
    conn.execute("INSERT INTO stocks VALUES ('67580', 'ソニーグループ', '電気機器')")
    conn.execute(
        "INSERT INTO daily_prices (code, date, open, high, low, close, volume) VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("72030", RECENT, 3000, 3050, 2980, 3020, 5000000),
    )
    conn.execute(
        "INSERT INTO daily_prices (code, date, open, high, low, close, volume) VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("67580", RECENT, 2500, 2540, 2480, 2510, 3000000),
    )
    conn.execute(
        "INSERT INTO signals (date, signal_type, code, direction, confidence, reasoning) VALUES (?, ?, ?, ?, ?, ?)",
        (RECENT, 'causality_chain', '72030', 'bullish', 0.8, '{"msg":"test"}'),
    )
    conn.commit()
    conn.close()
    return db_path


@pytest.fixture
def portfolio_db(tmp_path):
    """portfolio.db (空スキーマ)"""
    db_path = str(tmp_path / "portfolio.db")
    init_portfolio_db(db_path)
    return db_path


@pytest.fixture
def s3_with_dbs(tmp_path, stocks_db, portfolio_db):
    """S3 に stocks.db / portfolio.db をアップロードした状態を作る (moto)。"""
    with mock_aws():
        s3 = boto3.client("s3", region_name="ap-northeast-1")
        s3.create_bucket(
            Bucket=BUCKET,
            CreateBucketConfiguration={"LocationConstraint": "ap-northeast-1"},
        )
        s3.upload_file(stocks_db, BUCKET, "data/stocks.db")
        s3.upload_file(portfolio_db, BUCKET, "data/portfolio.db")
        yield s3


@pytest.fixture
def client(s3_with_dbs, monkeypatch, tmp_path):
    """FastAPI テストクライアント (モック S3 + portfolio 接続を /tmp の実ファイルに向ける)。"""
    # portfolio_storage モジュールのキャッシュをリセット
    import importlib
    import src.api.portfolio_storage as ps
    importlib.reload(ps)

    from src.api.main import app
    yield TestClient(app, raise_server_exceptions=True)


# ─────────────────────────────────────────────
# migrate_phase15.init_portfolio_db
# ─────────────────────────────────────────────

class TestInitPortfolioDb:
    def test_creates_tables(self, tmp_path):
        """portfolio.db に 3 テーブルが作成される。"""
        db_path = str(tmp_path / "portfolio.db")
        init_portfolio_db(db_path)

        conn = sqlite3.connect(db_path)
        tables = {row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        conn.close()

        assert "portfolio_holdings" in tables
        assert "portfolio_transactions" in tables
        assert "portfolio_snapshots" in tables

    def test_idempotent(self, tmp_path):
        """2 回実行しても例外が出ない (IF NOT EXISTS)。"""
        db_path = str(tmp_path / "portfolio.db")
        init_portfolio_db(db_path)
        init_portfolio_db(db_path)  # 2 回目も OK


# ─────────────────────────────────────────────
# portfolio_storage
# ─────────────────────────────────────────────

class TestPortfolioStorage:
    @mock_aws
    def test_download_creates_schema_when_not_in_s3(self, tmp_path, monkeypatch):
        """S3 に portfolio.db がない場合は空スキーマを作成する。"""
        s3 = boto3.client("s3", region_name="ap-northeast-1")
        s3.create_bucket(
            Bucket=BUCKET,
            CreateBucketConfiguration={"LocationConstraint": "ap-northeast-1"},
        )

        db_path = str(tmp_path / "portfolio.db")
        monkeypatch.setenv("PORTFOLIO_DB_PATH", db_path)

        import importlib
        import src.api.portfolio_storage as ps
        importlib.reload(ps)
        ps._download_portfolio(db_path)

        assert os.path.exists(db_path)
        conn = sqlite3.connect(db_path)
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        conn.close()
        assert "portfolio_holdings" in tables

    @mock_aws
    def test_upload_portfolio(self, tmp_path):
        """portfolio.db を S3 にアップロードする。"""
        s3 = boto3.client("s3", region_name="ap-northeast-1")
        s3.create_bucket(
            Bucket=BUCKET,
            CreateBucketConfiguration={"LocationConstraint": "ap-northeast-1"},
        )

        db_path = str(tmp_path / "portfolio.db")
        init_portfolio_db(db_path)

        import importlib
        import src.api.portfolio_storage as ps
        importlib.reload(ps)
        ps._upload_portfolio(db_path)

        head = s3.head_object(Bucket=BUCKET, Key="data/portfolio.db")
        assert head["ResponseMetadata"]["HTTPStatusCode"] == 200


# ─────────────────────────────────────────────
# GET /api/portfolio/holdings
# ─────────────────────────────────────────────

class TestListHoldings:
    def test_empty_holdings(self, client):
        """保有銘柄がない場合は空リストを返す。"""
        resp = client.get("/api/portfolio/holdings")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_holdings_with_price(self, client, tmp_path):
        """保有銘柄がある場合は含み損益付きで返す。"""
        db_path = str(tmp_path / "portfolio.db")
        conn = sqlite3.connect(db_path)
        conn.execute(
            "INSERT INTO portfolio_holdings (code, quantity, avg_cost, entry_date) VALUES ('72030', 100, 2800, '2025-01-01')"
        )
        conn.commit()
        conn.close()
        _upload_portfolio_db(db_path)

        resp = client.get("/api/portfolio/holdings")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["code"] == "72030"
        assert data[0]["quantity"] == 100
        assert data[0]["avg_cost"] == 2800
        # current_price = 3020 (stocks.db の終値)
        assert data[0]["current_price"] == 3020
        assert data[0]["valuation"] == 302000.0
        assert data[0]["unrealized_pnl"] == pytest.approx((3020 - 2800) * 100)


# ─────────────────────────────────────────────
# POST /api/portfolio/holdings
# ─────────────────────────────────────────────

class TestUpsertHolding:
    def test_add_new_holding(self, client, tmp_path):
        """新規保有銘柄を追加できる。"""
        resp = client.post("/api/portfolio/holdings", json={
            "code": "72030",
            "quantity": 100,
            "avg_cost": 2900,
            "entry_date": "2025-01-15",
        })
        assert resp.status_code == 201
        assert resp.json()["status"] == "upserted"

        db_path = str(tmp_path / "portfolio.db")
        conn = sqlite3.connect(db_path)
        row = conn.execute(
            "SELECT quantity, avg_cost FROM portfolio_holdings WHERE code='72030'"
        ).fetchone()
        conn.close()
        assert row[0] == 100
        assert row[1] == 2900

    def test_update_existing_holding(self, client, tmp_path):
        """既存の保有銘柄を上書き更新できる。"""
        client.post("/api/portfolio/holdings", json={
            "code": "72030", "quantity": 100, "avg_cost": 2900, "entry_date": "2025-01-15",
        })
        resp = client.post("/api/portfolio/holdings", json={
            "code": "72030", "quantity": 200, "avg_cost": 3000, "entry_date": "2025-01-15",
        })
        assert resp.status_code == 201

        db_path = str(tmp_path / "portfolio.db")
        conn = sqlite3.connect(db_path)
        row = conn.execute(
            "SELECT quantity, avg_cost FROM portfolio_holdings WHERE code='72030'"
        ).fetchone()
        conn.close()
        assert row[0] == 200
        assert row[1] == 3000


# ─────────────────────────────────────────────
# DELETE /api/portfolio/holdings/{code}
# ─────────────────────────────────────────────

class TestDeleteHolding:
    def test_delete_existing(self, client, tmp_path):
        """保有銘柄を削除できる。"""
        client.post("/api/portfolio/holdings", json={
            "code": "72030", "quantity": 100, "avg_cost": 2900, "entry_date": "2025-01-01",
        })
        resp = client.delete("/api/portfolio/holdings/72030")
        assert resp.status_code == 200
        assert resp.json()["status"] == "deleted"

    def test_delete_not_found(self, client):
        """存在しない銘柄の削除は 404。"""
        resp = client.delete("/api/portfolio/holdings/99999")
        assert resp.status_code == 404


# ─────────────────────────────────────────────
# GET /api/portfolio/transactions
# ─────────────────────────────────────────────

class TestListTransactions:
    def test_empty(self, client):
        """取引なしは空リスト。"""
        resp = client.get("/api/portfolio/transactions")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_filter_by_code(self, client, tmp_path):
        """code フィルタが動作する。"""
        db_path = str(tmp_path / "portfolio.db")
        conn = sqlite3.connect(db_path)
        conn.execute(
            "INSERT INTO portfolio_transactions (code, date, action, quantity, price, fee) VALUES ('72030','2025-01-01','buy',100,2900,100)"
        )
        conn.execute(
            "INSERT INTO portfolio_transactions (code, date, action, quantity, price, fee) VALUES ('67580','2025-01-02','buy',50,2500,100)"
        )
        conn.commit()
        conn.close()
        _upload_portfolio_db(db_path)

        resp = client.get("/api/portfolio/transactions?code=72030")
        assert resp.status_code == 200
        data = resp.json()
        assert all(r["code"] == "72030" for r in data)
        assert len(data) == 1


# ─────────────────────────────────────────────
# POST /api/portfolio/transactions
# ─────────────────────────────────────────────

class TestAddTransaction:
    def test_buy_creates_holding(self, client, tmp_path):
        """buy 取引で holdings が自動作成される。"""
        resp = client.post("/api/portfolio/transactions", json={
            "code": "72030", "date": "2025-01-15", "action": "buy",
            "quantity": 100, "price": 3000, "fee": 100,
        })
        assert resp.status_code == 201

        db_path = str(tmp_path / "portfolio.db")
        conn = sqlite3.connect(db_path)
        row = conn.execute(
            "SELECT quantity, avg_cost FROM portfolio_holdings WHERE code='72030'"
        ).fetchone()
        conn.close()
        assert row[0] == 100
        assert row[1] == 3000

    def test_buy_updates_avg_cost(self, client, tmp_path):
        """2 回 buy すると加重平均で avg_cost が更新される。"""
        client.post("/api/portfolio/transactions", json={
            "code": "72030", "date": "2025-01-10", "action": "buy",
            "quantity": 100, "price": 3000, "fee": 0,
        })
        client.post("/api/portfolio/transactions", json={
            "code": "72030", "date": "2025-01-20", "action": "buy",
            "quantity": 100, "price": 3200, "fee": 0,
        })

        db_path = str(tmp_path / "portfolio.db")
        conn = sqlite3.connect(db_path)
        row = conn.execute(
            "SELECT quantity, avg_cost FROM portfolio_holdings WHERE code='72030'"
        ).fetchone()
        conn.close()
        assert row[0] == 200
        assert row[1] == pytest.approx(3100.0)

    def test_sell_reduces_quantity(self, client, tmp_path):
        """sell 取引で holdings の quantity が減る。"""
        client.post("/api/portfolio/transactions", json={
            "code": "72030", "date": "2025-01-10", "action": "buy",
            "quantity": 100, "price": 3000, "fee": 0,
        })
        resp = client.post("/api/portfolio/transactions", json={
            "code": "72030", "date": "2025-01-20", "action": "sell",
            "quantity": 40, "price": 3200, "fee": 0,
        })
        assert resp.status_code == 201

        db_path = str(tmp_path / "portfolio.db")
        conn = sqlite3.connect(db_path)
        row = conn.execute(
            "SELECT quantity FROM portfolio_holdings WHERE code='72030'"
        ).fetchone()
        conn.close()
        assert row[0] == 60

    def test_sell_removes_holding_when_zero(self, client, tmp_path):
        """全株売却で holdings が削除される。"""
        client.post("/api/portfolio/transactions", json={
            "code": "72030", "date": "2025-01-10", "action": "buy",
            "quantity": 100, "price": 3000, "fee": 0,
        })
        client.post("/api/portfolio/transactions", json={
            "code": "72030", "date": "2025-01-20", "action": "sell",
            "quantity": 100, "price": 3200, "fee": 0,
        })

        db_path = str(tmp_path / "portfolio.db")
        conn = sqlite3.connect(db_path)
        row = conn.execute(
            "SELECT quantity FROM portfolio_holdings WHERE code='72030'"
        ).fetchone()
        conn.close()
        assert row is None

    def test_sell_over_quantity_returns_400(self, client):
        """保有量を超える sell は 400。"""
        client.post("/api/portfolio/transactions", json={
            "code": "72030", "date": "2025-01-10", "action": "buy",
            "quantity": 50, "price": 3000, "fee": 0,
        })
        resp = client.post("/api/portfolio/transactions", json={
            "code": "72030", "date": "2025-01-20", "action": "sell",
            "quantity": 100, "price": 3200, "fee": 0,
        })
        assert resp.status_code == 400

    def test_sell_without_holding_returns_400(self, client):
        """保有していない銘柄の sell は 400。"""
        resp = client.post("/api/portfolio/transactions", json={
            "code": "99999", "date": "2025-01-20", "action": "sell",
            "quantity": 10, "price": 1000, "fee": 0,
        })
        assert resp.status_code == 400


# ─────────────────────────────────────────────
# GET /api/portfolio/performance
# ─────────────────────────────────────────────

class TestGetPerformance:
    def test_empty_snapshots(self, client):
        """スナップショットなしは空リスト。"""
        resp = client.get("/api/portfolio/performance")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_returns_aggregated_by_date(self, client, tmp_path):
        """複数銘柄のスナップショットが日付でまとめられる。"""
        db_path = str(tmp_path / "portfolio.db")
        conn = sqlite3.connect(db_path)
        conn.execute(
            "INSERT INTO portfolio_holdings (code, quantity, avg_cost, entry_date) VALUES ('72030', 100, 2800, '2025-01-01')"
        )
        conn.execute(
            "INSERT INTO portfolio_snapshots (date, code, close_price, quantity, valuation, unrealized_pnl) VALUES (?, '72030', 3020, 100, 302000, 22000)",
            (RECENT,),
        )
        conn.commit()
        conn.close()
        _upload_portfolio_db(db_path)

        resp = client.get("/api/portfolio/performance?days=30")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1
        assert data[0]["total_valuation"] == pytest.approx(302000.0)


# ─────────────────────────────────────────────
# GET /api/portfolio/signals
# ─────────────────────────────────────────────

class TestPortfolioSignals:
    def test_no_holdings_returns_empty(self, client):
        """保有なしは空リスト。"""
        resp = client.get("/api/portfolio/signals")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_returns_signals_for_holdings(self, client, tmp_path):
        """保有銘柄に関連するシグナルを返す。"""
        db_path = str(tmp_path / "portfolio.db")
        conn = sqlite3.connect(db_path)
        conn.execute(
            "INSERT INTO portfolio_holdings (code, quantity, avg_cost, entry_date) VALUES ('72030', 100, 2800, '2025-01-01')"
        )
        conn.commit()
        conn.close()
        _upload_portfolio_db(db_path)

        resp = client.get("/api/portfolio/signals?days=30")
        assert resp.status_code == 200
        data = resp.json()
        # signals テーブルには 72030 のシグナルが 1 件ある (stocks_db fixture)
        codes = [s["code"] for s in data]
        assert "72030" in codes
