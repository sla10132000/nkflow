"""storage.py のテスト (moto で S3/SSM をモック)"""
import os
import sqlite3
import sys
import tarfile
from unittest.mock import patch

import boto3
import pytest
from moto import mock_aws

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scripts.init_sqlite import init_sqlite

BUCKET = "test-nkflow-bucket"
TARGET_DATE = "2025-01-06"


@pytest.fixture(autouse=True)
def aws_env(monkeypatch):
    """テスト用 AWS 環境変数を設定する。"""
    monkeypatch.setenv("S3_BUCKET", BUCKET)
    monkeypatch.setenv("AWS_DEFAULT_REGION", "ap-northeast-1")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_SECURITY_TOKEN", "testing")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "testing")


# ─────────────────────────────────────────────────────────────────────────────
# get_api_key
# ─────────────────────────────────────────────────────────────────────────────

class TestGetApiKey:
    def test_returns_env_var_if_set(self, monkeypatch):
        """環境変数が設定済みなら SSM をスキップして返す。"""
        monkeypatch.setenv("JQUANTS_API_KEY", "env-api-key")

        import importlib
        import src.config as cfg
        importlib.reload(cfg)
        from src.pipeline import storage
        importlib.reload(storage)

        api_key = storage.get_api_key()
        assert api_key == "env-api-key"

    @mock_aws
    def test_fetches_from_ssm_when_env_empty(self, monkeypatch):
        """環境変数が空なら SSM から取得する。"""
        monkeypatch.setenv("JQUANTS_API_KEY", "")

        ssm = boto3.client("ssm", region_name="ap-northeast-1")
        ssm.put_parameter(Name="/nkflow/jquants-api-key", Value="ssm-api-key", Type="SecureString")

        import importlib
        import src.config as cfg
        importlib.reload(cfg)
        from src.pipeline import storage
        importlib.reload(storage)

        api_key = storage.get_api_key()
        assert api_key == "ssm-api-key"


# ─────────────────────────────────────────────────────────────────────────────
# download (_download_sqlite)
# ─────────────────────────────────────────────────────────────────────────────

class TestDownloadSQLite:
    @mock_aws
    def test_downloads_existing_sqlite_from_s3(self, tmp_path, monkeypatch):
        """S3 に SQLite が存在する場合はダウンロードし、スキーマを適用する (冪等)。"""
        # S3 にダミー SQLite を配置
        s3 = boto3.client("s3", region_name="ap-northeast-1")
        s3.create_bucket(
            Bucket=BUCKET,
            CreateBucketConfiguration={"LocationConstraint": "ap-northeast-1"},
        )
        dummy_db = tmp_path / "source.db"
        init_sqlite(str(dummy_db))
        s3.upload_file(str(dummy_db), BUCKET, "data/stocks.db")

        dest_path = str(tmp_path / "stocks.db")

        with patch("src.pipeline.storage._init_sqlite_schema") as mock_init:
            from src.pipeline import storage
            storage._download_sqlite(dest_path)

        assert os.path.exists(dest_path)
        # 既存 DB でも _init_sqlite_schema を呼び出してマイグレーションを適用する
        mock_init.assert_called_once_with(dest_path)

    @mock_aws
    def test_initializes_schema_when_not_in_s3(self, tmp_path):
        """S3 に SQLite がない場合はスキーマを初期化する。"""
        s3 = boto3.client("s3", region_name="ap-northeast-1")
        s3.create_bucket(
            Bucket=BUCKET,
            CreateBucketConfiguration={"LocationConstraint": "ap-northeast-1"},
        )

        dest_path = str(tmp_path / "stocks.db")

        with patch("src.pipeline.storage._init_sqlite_schema") as mock_init:
            from src.pipeline import storage
            storage._download_sqlite(dest_path)

        mock_init.assert_called_once_with(dest_path)


# ─────────────────────────────────────────────────────────────────────────────
# download (_download_kuzu)
# ─────────────────────────────────────────────────────────────────────────────

class TestDownloadKuzu:
    @mock_aws
    def test_downloads_and_extracts_tarball(self, tmp_path):
        """S3 に KùzuDB tar.gz が存在する場合はダウンロードして展開する。"""
        s3 = boto3.client("s3", region_name="ap-northeast-1")
        s3.create_bucket(
            Bucket=BUCKET,
            CreateBucketConfiguration={"LocationConstraint": "ap-northeast-1"},
        )

        # ダミー kuzu_db ディレクトリを tar.gz にして S3 に配置
        kuzu_src = tmp_path / "kuzu_db_source"
        kuzu_src.mkdir()
        (kuzu_src / "data.bin").write_bytes(b"\x00" * 16)

        tar_src = tmp_path / "kuzu_db_source.tar.gz"
        with tarfile.open(str(tar_src), "w:gz") as tar:
            tar.add(str(kuzu_src), arcname="kuzu_db")
        s3.upload_file(str(tar_src), BUCKET, "data/kuzu_db.tar.gz")

        kuzu_dest = str(tmp_path / "kuzu_db")
        from src.pipeline import storage
        storage._download_kuzu(kuzu_dest)

        assert os.path.exists(kuzu_dest)

    @mock_aws
    def test_cleans_up_on_not_found(self, tmp_path):
        """S3 に KùzuDB がない場合は既存ディレクトリを削除する (初回実行対応)。"""
        s3 = boto3.client("s3", region_name="ap-northeast-1")
        s3.create_bucket(
            Bucket=BUCKET,
            CreateBucketConfiguration={"LocationConstraint": "ap-northeast-1"},
        )

        kuzu_path = str(tmp_path / "kuzu_db")
        os.makedirs(kuzu_path)  # 事前に存在させる

        from src.pipeline import storage
        storage._download_kuzu(kuzu_path)

        # 既存ディレクトリが削除されている (KùzuDB が新規作成できる状態)
        assert not os.path.exists(kuzu_path)


# ─────────────────────────────────────────────────────────────────────────────
# upload (_upload_sqlite / _upload_kuzu)
# ─────────────────────────────────────────────────────────────────────────────

class TestUploadSQLite:
    @mock_aws
    def test_uploads_sqlite_to_s3(self, tmp_path):
        """SQLite ファイルを S3 にアップロードする。"""
        s3 = boto3.client("s3", region_name="ap-northeast-1")
        s3.create_bucket(
            Bucket=BUCKET,
            CreateBucketConfiguration={"LocationConstraint": "ap-northeast-1"},
        )

        sqlite_path = str(tmp_path / "stocks.db")
        init_sqlite(sqlite_path)

        from src.pipeline import storage
        storage._upload_sqlite(sqlite_path)

        response = s3.head_object(Bucket=BUCKET, Key="data/stocks.db")
        assert response["ResponseMetadata"]["HTTPStatusCode"] == 200

    def test_skips_upload_if_file_missing(self, tmp_path):
        """SQLite が存在しない場合はスキップする (例外を送出しない)。"""
        from src.pipeline import storage
        storage._upload_sqlite(str(tmp_path / "nonexistent.db"))


class TestUploadKuzu:
    @mock_aws
    def test_creates_tarball_and_uploads(self, tmp_path):
        """kuzu_path を tar.gz に圧縮して S3 にアップロードする。"""
        s3 = boto3.client("s3", region_name="ap-northeast-1")
        s3.create_bucket(
            Bucket=BUCKET,
            CreateBucketConfiguration={"LocationConstraint": "ap-northeast-1"},
        )

        kuzu_path = tmp_path / "kuzu_db"
        kuzu_path.mkdir()
        (kuzu_path / "data.bin").write_bytes(b"\xde\xad\xbe\xef")

        from src.pipeline import storage
        storage._upload_kuzu(str(kuzu_path))

        # tar.gz がローカルに作成されている
        assert os.path.exists(str(kuzu_path) + ".tar.gz")

        # S3 にアップロードされている
        response = s3.head_object(Bucket=BUCKET, Key="data/kuzu_db.tar.gz")
        assert response["ResponseMetadata"]["HTTPStatusCode"] == 200

    def test_skips_upload_if_path_missing(self, tmp_path):
        """kuzu_path が存在しない場合はスキップする (例外を送出しない)。"""
        from src.pipeline import storage
        storage._upload_kuzu(str(tmp_path / "nonexistent"))


# ─────────────────────────────────────────────────────────────────────────────
# handler.handler
# ─────────────────────────────────────────────────────────────────────────────

class TestBatchHandler:
    def _patch_all(self, n_fetched: int = 5):
        return [
            patch("src.pipeline.storage.get_api_key", return_value="test-api-key"),
            patch("src.pipeline.storage.download"),
            patch("src.pipeline.storage.upload"),
            patch("src.ingestion.jquants.fetch_daily", return_value=n_fetched),
            patch("src.transform.compute.compute_all"),
            patch("src.transform.statistics.run_all"),
            patch("src.graph.kuzu.update_and_query", return_value={
                "chains": [], "fund_flow_paths": [], "regime_perf": {}
            }),
            patch("src.ingestion.yahoo_finance.fetch_exchange_rates", return_value=0),
            patch("src.ingestion.yahoo_finance.fetch_margin_balance", return_value=0),
            patch("src.transform.sector_rotation.run_all"),
            patch("src.notification.notifier.publish", return_value=True),
            patch("src.ingestion.yahoo_finance.fetch_crypto_fear_greed", return_value=0),  # Phase 21
            patch("src.transform.td_sequential.compute_td_sequential", return_value=0),      # Phase 22
            patch("src.ingestion.news.normalize_news", return_value=0),
            patch("src.transform.news_enrichment.enrich_articles", return_value={}),
            patch("src.ingestion.yahoo_finance.fetch_nikkei_close"),
            patch("src.ingestion.yahoo_finance.fetch_us_indices", return_value={}),
            patch("src.signals.generator.generate", return_value=0),
            patch("src.ingestion.jquants.fetch_investor_flows", return_value=0),          # Phase 23
            patch("src.transform.statistics.compute_investor_flow_indicators", return_value=0),  # Phase 23
            patch("src.signals.generator.generate_investor_flow_signals", return_value=0),      # Phase 23
        ]

    def test_returns_200_on_trading_day(self, tmp_path, monkeypatch):
        """取引日は statusCode=200 で全ステップが実行される。"""
        monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "stocks.db"))
        monkeypatch.setenv("KUZU_PATH", str(tmp_path / "kuzu_db"))
        init_sqlite(str(tmp_path / "stocks.db"))

        from contextlib import ExitStack
        patches = self._patch_all(n_fetched=5)
        with ExitStack() as stack:
            mocks = [stack.enter_context(p) for p in patches]
            mock_fetch = mocks[3]
            mock_compute = mocks[4]
            mock_stats = mocks[5]
            mock_graph = mocks[6]

            import importlib
            import src.pipeline.handler as handler_mod
            importlib.reload(handler_mod)

            resp = handler_mod.handler({"target_date": TARGET_DATE}, None)

        assert resp["statusCode"] == 200
        assert resp["body"]["stocks_updated"] == 5
        mock_fetch.assert_called_once()
        mock_compute.assert_called_once()
        mock_stats.assert_called_once()
        mock_graph.assert_called_once()

    def test_returns_200_on_non_trading_day(self, tmp_path, monkeypatch):
        """非取引日は stocks_updated=0 で後続処理をスキップ。"""
        monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "stocks.db"))
        monkeypatch.setenv("KUZU_PATH", str(tmp_path / "kuzu_db"))
        init_sqlite(str(tmp_path / "stocks.db"))

        from contextlib import ExitStack
        patches = self._patch_all(n_fetched=0)
        with ExitStack() as stack:
            mocks = [stack.enter_context(p) for p in patches]
            mock_compute = mocks[4]
            mock_stats = mocks[5]
            mock_graph = mocks[6]

            import importlib
            import src.pipeline.handler as handler_mod
            importlib.reload(handler_mod)

            resp = handler_mod.handler({"target_date": TARGET_DATE}, None)

        assert resp["statusCode"] == 200
        assert resp["body"]["stocks_updated"] == 0
        mock_compute.assert_not_called()
        mock_stats.assert_not_called()
        mock_graph.assert_not_called()

    def test_upload_always_runs_even_on_error(self, tmp_path, monkeypatch):
        """途中ステップが例外を送出しても upload は必ず実行される。"""
        monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "stocks.db"))
        monkeypatch.setenv("KUZU_PATH", str(tmp_path / "kuzu_db"))
        init_sqlite(str(tmp_path / "stocks.db"))

        with patch("src.pipeline.storage.get_api_key", return_value="test-api-key"), \
             patch("src.pipeline.storage.download"), \
             patch("src.pipeline.storage.upload") as mock_upload, \
             patch("src.ingestion.jquants.fetch_daily", return_value=3), \
             patch("src.transform.compute.compute_all", side_effect=RuntimeError("DuckDB crash")), \
             patch("src.transform.statistics.run_all"), \
             patch("src.graph.kuzu.update_and_query", return_value={}), \
             patch("src.ingestion.yahoo_finance.fetch_exchange_rates", return_value=0), \
             patch("src.ingestion.yahoo_finance.fetch_margin_balance", return_value=0), \
             patch("src.transform.sector_rotation.run_all"), \
             patch("src.notification.notifier.publish", return_value=True), \
             patch("src.ingestion.yahoo_finance.fetch_crypto_fear_greed", return_value=0):  # Phase 21

            import importlib
            import src.pipeline.handler as handler_mod
            importlib.reload(handler_mod)

            resp = handler_mod.handler({"target_date": TARGET_DATE}, None)

        mock_upload.assert_called_once()
        assert resp["statusCode"] == 207  # partial success
        assert any("compute" in e for e in resp["body"]["errors"])

    def test_returns_500_on_download_failure(self, tmp_path, monkeypatch):
        """download が失敗した場合は statusCode=500 を返す。"""
        monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "stocks.db"))
        monkeypatch.setenv("KUZU_PATH", str(tmp_path / "kuzu_db"))

        with patch("src.pipeline.storage.get_api_key", return_value="test-api-key"), \
             patch("src.pipeline.storage.download", side_effect=RuntimeError("S3 error")), \
             patch("src.pipeline.storage.upload") as mock_upload:

            import importlib
            import src.pipeline.handler as handler_mod
            importlib.reload(handler_mod)

            resp = handler_mod.handler({"target_date": TARGET_DATE}, None)

        assert resp["statusCode"] == 500
        mock_upload.assert_not_called()
