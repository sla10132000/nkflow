"""災害データ取得モジュールのテスト"""
import json
from unittest.mock import MagicMock, patch

import boto3
import pytest
from moto import mock_aws

from src.ingestion.disaster import (
    _parse_intensity,
    fetch_all_disaster_data,
    fetch_jma_earthquakes,
    fetch_jma_tsunami,
    fetch_jma_warnings,
    fetch_usgs_earthquakes,
)

S3_BUCKET = "test-nkflow-bucket"

FAKE_JMA_QUAKE_LIST = [
    {
        "ctt": "20260306113844",
        "eid": "20260306113352",
        "rdt": "2026-03-06T11:38:00+09:00",
        "ttl": "震源・震度情報",
        "ift": "発表",
        "ser": "1",
        "at": "2026-03-06T11:33:00+09:00",
        "anm": "北海道北西沖",
        "acd": "183",
        "cod": "+44.5+141.7-20000/",
        "mag": "5.2",
        "maxi": "4",
        "int": [{"code": "01", "maxi": "4", "city": []}],
        "json": "20260306113844_20260306113352_VXSE5k_1.json",
        "en_ttl": "Earthquake and Seismic Intensity Information",
        "en_anm": "Off the northwest Coast of Hokkaido",
    },
    {
        "ctt": "20260306090000",
        "eid": "20260306085500",
        "at": "2026-03-06T08:55:00+09:00",
        "anm": "茨城県沖",
        "mag": "2.1",
        "maxi": "1",
        "json": "20260306090000_20260306085500_VXSE5k_1.json",
    },
    {
        "ctt": "20260305200000",
        "eid": "20260305195500",
        "at": "2026-03-05T19:55:00+09:00",
        "anm": "福島県沖",
        "mag": "3.0",
        "maxi": "2",
        "json": "fake_detail.json",
    },
]

FAKE_JMA_QUAKE_DETAIL = {
    "Head": {"Title": "震源・震度に関する情報"},
    "Body": {"Earthquake": {"Hypocenter": {"Area": {"Name": "北海道北西沖"}}}},
}

FAKE_JMA_WARNING_MAP = [
    {
        "reportDatetime": "2026-03-06T10:12:00+09:00",
        "areaTypes": [
            {
                "areas": [
                    {
                        "code": "011000",
                        "warnings": [
                            {"code": "03", "status": "発表"},  # 大雨警報
                        ],
                    }
                ]
            },
            {
                "areas": [
                    {
                        "code": "0121400",
                        "warnings": [
                            {"code": "26", "status": "継続"},  # 着雪注意報
                        ],
                    }
                ]
            },
        ],
    },
    {
        "reportDatetime": "2026-03-06T10:12:00+09:00",
        "areaTypes": [
            {
                "areas": [
                    {
                        "code": "130000",
                        "warnings": [
                            {"code": "05", "status": "解除"},  # 暴風警報 (解除済み)
                        ],
                    }
                ]
            }
        ],
    },
]

FAKE_USGS_RESPONSE = {
    "type": "FeatureCollection",
    "metadata": {"count": 1},
    "features": [
        {
            "properties": {
                "mag": 4.7,
                "place": "123 km E of Miyako, Japan",
                "time": 1772585322061,
                "alert": "green",
                "tsunami": 0,
                "sig": 340,
                "type": "earthquake",
                "title": "M 4.7 - 123 km E of Miyako, Japan",
            },
            "geometry": {"type": "Point", "coordinates": [143.379, 39.73, 35]},
            "id": "us7000s1vd",
        }
    ],
}


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


def _mock_get(url, **kwargs):
    """requests.get のモック"""
    resp = MagicMock()
    resp.status_code = 200
    resp.raise_for_status = MagicMock()

    if "quake/data/list.json" in url:
        resp.json.return_value = FAKE_JMA_QUAKE_LIST
    elif "quake/data/" in url:
        resp.json.return_value = FAKE_JMA_QUAKE_DETAIL
    elif "warning/data/warning/map.json" in url:
        resp.json.return_value = FAKE_JMA_WARNING_MAP
    elif "tsunami/data/list.json" in url:
        resp.json.return_value = []
    elif "earthquake.usgs.gov" in url:
        resp.json.return_value = FAKE_USGS_RESPONSE
    else:
        resp.json.return_value = {}

    return resp


class TestFetchJmaEarthquakes:
    @patch("src.ingestion.disaster.requests.get", side_effect=_mock_get)
    def test_saves_earthquake_list_to_raw(self, mock_get, s3_bucket):
        count = fetch_jma_earthquakes("2026-03-06")

        assert count == 2  # 2 events on 2026-03-06 (3rd is 2026-03-05)
        stored = _get_raw(
            s3_bucket, "raw/disaster/natural/jma/earthquake_list/2026-03-06.json"
        )
        assert stored["category"] == "disaster"
        assert stored["subcategory"] == "natural"
        assert stored["source"] == "jma"
        assert len(stored["data"]) == 2

    @patch("src.ingestion.disaster.requests.get", side_effect=_mock_get)
    def test_filters_by_target_date(self, mock_get, s3_bucket):
        count = fetch_jma_earthquakes("2026-03-05")

        assert count == 1  # Only the 2026-03-05 event
        stored = _get_raw(
            s3_bucket, "raw/disaster/natural/jma/earthquake_list/2026-03-05.json"
        )
        assert stored["data"][0]["anm"] == "福島県沖"

    @patch("src.ingestion.disaster.requests.get", side_effect=_mock_get)
    def test_fetches_detail_for_intensity_4_plus(self, mock_get, s3_bucket):
        fetch_jma_earthquakes("2026-03-06")

        # Detail should be saved (maxi=4 event exists)
        stored = _get_raw(
            s3_bucket, "raw/disaster/natural/jma/earthquake_detail/2026-03-06.json"
        )
        assert len(stored["data"]) == 1
        assert stored["data"][0]["Head"]["Title"] == "震源・震度に関する情報"

    @patch("src.ingestion.disaster.requests.get", side_effect=_mock_get)
    def test_no_events_returns_zero(self, mock_get, s3_bucket):
        count = fetch_jma_earthquakes("2026-01-01")  # No events on this date
        assert count == 0

    @patch("src.ingestion.disaster.requests.get", side_effect=Exception("network error"))
    def test_handles_api_failure(self, mock_get, s3_bucket):
        with pytest.raises(Exception, match="network error"):
            fetch_jma_earthquakes("2026-03-06")


class TestFetchJmaWarnings:
    @patch("src.ingestion.disaster.requests.get", side_effect=_mock_get)
    def test_saves_active_warnings_only(self, mock_get, s3_bucket):
        count = fetch_jma_warnings("2026-03-06")

        assert count == 1  # Only 011000 has 大雨警報 (code 03, not 解除)
        stored = _get_raw(
            s3_bucket, "raw/disaster/natural/jma/warning_map/2026-03-06.json"
        )
        assert stored["data"][0]["code"] == "011000"
        assert stored["data"][0]["warnings"][0]["code"] == "03"

    @patch("src.ingestion.disaster.requests.get")
    def test_no_warnings_returns_zero(self, mock_get, s3_bucket):
        resp = MagicMock()
        resp.json.return_value = [
            {
                "reportDatetime": "2026-03-06T10:00:00+09:00",
                "areaTypes": [{"areas": [{"code": "130000", "warnings": []}]}],
            }
        ]
        resp.raise_for_status = MagicMock()
        mock_get.return_value = resp

        count = fetch_jma_warnings("2026-03-06")
        assert count == 0


class TestFetchJmaTsunami:
    @patch("src.ingestion.disaster.requests.get", side_effect=_mock_get)
    def test_empty_tsunami_returns_zero(self, mock_get, s3_bucket):
        count = fetch_jma_tsunami("2026-03-06")
        assert count == 0  # _mock_get returns [] for tsunami

    @patch("src.ingestion.disaster.requests.get")
    def test_saves_active_tsunami_warnings(self, mock_get, s3_bucket):
        resp = MagicMock()
        resp.json.return_value = [{"eid": "1234", "ttl": "大津波警報"}]
        resp.raise_for_status = MagicMock()
        mock_get.return_value = resp

        count = fetch_jma_tsunami("2026-03-06")
        assert count == 1
        stored = _get_raw(
            s3_bucket, "raw/disaster/natural/jma/tsunami/2026-03-06.json"
        )
        assert stored["data"][0]["ttl"] == "大津波警報"


class TestFetchUsgsEarthquakes:
    @patch("src.ingestion.disaster.requests.get", side_effect=_mock_get)
    def test_saves_geojson_to_raw(self, mock_get, s3_bucket):
        count = fetch_usgs_earthquakes("2026-03-05")

        assert count == 1
        stored = _get_raw(
            s3_bucket, "raw/disaster/natural/usgs/earthquake/2026-03-05.json"
        )
        assert stored["data"]["type"] == "FeatureCollection"
        assert len(stored["data"]["features"]) == 1

    @patch("src.ingestion.disaster.requests.get")
    def test_empty_features_returns_zero(self, mock_get, s3_bucket):
        resp = MagicMock()
        resp.json.return_value = {"type": "FeatureCollection", "features": []}
        resp.raise_for_status = MagicMock()
        mock_get.return_value = resp

        count = fetch_usgs_earthquakes("2026-03-05")
        assert count == 0


class TestFetchAllDisasterData:
    @patch("src.ingestion.disaster.requests.get", side_effect=_mock_get)
    def test_returns_combined_counts(self, mock_get, s3_bucket):
        result = fetch_all_disaster_data("2026-03-06")

        assert result["jma_earthquakes"] == 2
        assert result["jma_warnings"] == 1
        assert result["jma_tsunami"] == 0
        assert result["usgs_earthquakes"] == 1

    @patch("src.ingestion.disaster.requests.get")
    def test_individual_failure_does_not_block_others(self, mock_get, s3_bucket):
        call_count = {"n": 0}

        def selective_fail(url, **kwargs):
            call_count["n"] += 1
            if "quake/data/list.json" in url:
                raise Exception("JMA down")
            return _mock_get(url, **kwargs)

        mock_get.side_effect = selective_fail

        result = fetch_all_disaster_data("2026-03-06")
        assert result["jma_earthquakes"] == 0  # Failed
        assert result["jma_warnings"] == 1  # Succeeded
        assert result["usgs_earthquakes"] == 1  # Succeeded


class TestParseIntensity:
    @pytest.mark.parametrize(
        "input_val, expected",
        [
            ("1", 1),
            ("4", 4),
            ("5-", 5),
            ("5+", 5),
            ("6-", 6),
            ("6+", 6),
            ("7", 7),
            ("0", 0),
            ("", 0),
            (None, 0),
        ],
    )
    def test_parse_intensity(self, input_val, expected):
        assert _parse_intensity(input_val) == expected
