"""raw_store モジュールのテスト"""
import json

import boto3
import pandas as pd
import pytest
from moto import mock_aws

from src.pipeline.raw_store import save_raw

S3_BUCKET = "test-nkflow-bucket"


@pytest.fixture
def s3_bucket():
    with mock_aws():
        s3 = boto3.client("s3", region_name="ap-northeast-1")
        s3.create_bucket(
            Bucket=S3_BUCKET,
            CreateBucketConfiguration={"LocationConstraint": "ap-northeast-1"},
        )
        yield s3


def _get_raw(s3, key: str) -> dict:
    obj = s3.get_object(Bucket=S3_BUCKET, Key=key)
    return json.loads(obj["Body"].read())


class TestSaveRaw:
    def test_creates_json_in_s3(self, s3_bucket):
        data = [{"code": "7203", "close": 2500}]
        key = save_raw("jquants", "daily_prices", "2026-03-06", data)

        assert key == "raw/jquants/daily_prices/2026-03-06.json"
        stored = _get_raw(s3_bucket, key)
        assert stored["source"] == "jquants"
        assert stored["data_type"] == "daily_prices"
        assert stored["date"] == "2026-03-06"
        assert stored["data"] == data
        assert "saved_at" in stored

    def test_skips_existing_file(self, s3_bucket):
        data1 = [{"v": 1}]
        data2 = [{"v": 2}]
        save_raw("src", "type", "2026-01-01", data1)
        save_raw("src", "type", "2026-01-01", data2)

        stored = _get_raw(s3_bucket, "raw/src/type/2026-01-01.json")
        assert stored["data"] == data1  # 上書きされていない

    def test_overwrite_flag(self, s3_bucket):
        save_raw("src", "type", "2026-01-01", [{"v": 1}])
        save_raw("src", "type", "2026-01-01", [{"v": 2}], overwrite=True)

        stored = _get_raw(s3_bucket, "raw/src/type/2026-01-01.json")
        assert stored["data"] == [{"v": 2}]

    def test_handles_dataframe(self, s3_bucket):
        df = pd.DataFrame({"code": ["7203", "6758"], "close": [2500, 1800]})
        key = save_raw("jquants", "stock_master", "2026-03-06", df)

        stored = _get_raw(s3_bucket, key)
        assert len(stored["data"]) == 2
        assert stored["data"][0]["code"] == "7203"

    def test_handles_non_serializable_types(self, s3_bucket):
        from datetime import date

        data = {"date": date(2026, 3, 6), "value": 100}
        key = save_raw("test", "misc", "2026-03-06", data)

        stored = _get_raw(s3_bucket, key)
        assert stored["data"]["date"] == "2026-03-06"

    def test_failure_returns_none(self, monkeypatch):
        monkeypatch.setattr(
            "src.pipeline.raw_store.S3_BUCKET", "nonexistent-bucket"
        )
        result = save_raw("src", "type", "2026-01-01", {"x": 1})
        assert result is None
