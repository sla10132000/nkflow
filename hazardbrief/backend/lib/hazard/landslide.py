"""国交省 不動産情報ライブラリ API で土砂災害リスクを取得"""
import logging
import os
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

REINFOLIB_BASE_URL = "https://www.reinfolib.mlit.go.jp/ex-api/external"

# 土砂災害リスク区分
LANDSLIDE_ZONE_LABELS = {
    "special": "土砂災害特別警戒区域（レッドゾーン）",
    "warning": "土砂災害警戒区域（イエローゾーン）",
    "none": "警戒区域外",
}

LANDSLIDE_TYPE_LABELS = {
    "1": "急傾斜地の崩壊",
    "2": "土石流",
    "3": "地すべり",
}


async def get_landslide_risk(lat: float, lon: float, zoom: int = 15) -> dict:
    """
    国交省 不動産情報ライブラリ API から土砂災害警戒区域データを取得する。

    Returns:
        {
            "level": str,
            "zone_type": str | None,
            "zone_label": str,
            "disaster_type": str | None,
            "disaster_type_label": str | None,
            "source": str,
            "available": bool,
        }
    """
    api_key = os.environ.get("REINFOLIB_API_KEY", "")
    if not api_key:
        return _unavailable_response("REINFOLIB_API_KEY が設定されていません")

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"{REINFOLIB_BASE_URL}/XIT002",
                params={
                    "response_format": "geojson",
                    "datum": "wgs84",
                    "lat": lat,
                    "lon": lon,
                    "zoom": zoom,
                },
                headers={"Ocp-Apim-Subscription-Key": api_key},
            )
            resp.raise_for_status()
            data = resp.json()

        features = data.get("features", [])
        if not features:
            return {
                "level": "low",
                "zone_type": "none",
                "zone_label": LANDSLIDE_ZONE_LABELS["none"],
                "disaster_type": None,
                "disaster_type_label": None,
                "source": "国土交通省 不動産情報ライブラリ",
                "available": True,
            }

        # 特別警戒区域（レッドゾーン）を優先
        zone_type = "warning"
        disaster_type = None

        for feature in features:
            props = feature.get("properties", {})
            # A33a_001: 区域区分 (1=特別警戒, 2=警戒)
            zone_code = str(props.get("A33a_001", "2"))
            if zone_code == "1":
                zone_type = "special"
            disaster_type = str(props.get("A33a_002", "1"))

        level = "high" if zone_type == "special" else "medium"

        return {
            "level": level,
            "zone_type": zone_type,
            "zone_label": LANDSLIDE_ZONE_LABELS.get(zone_type, "不明"),
            "disaster_type": disaster_type,
            "disaster_type_label": LANDSLIDE_TYPE_LABELS.get(disaster_type),
            "source": "国土交通省 不動産情報ライブラリ",
            "available": True,
        }

    except httpx.HTTPStatusError as e:
        logger.error(f"土砂リスク取得 HTTP エラー: {e.response.status_code}")
        return _unavailable_response(f"API エラー: {e.response.status_code}")
    except Exception as e:
        logger.error(f"土砂リスク取得失敗: {e}")
        return _unavailable_response(str(e))


def _unavailable_response(reason: str) -> dict:
    return {
        "level": "unknown",
        "zone_type": None,
        "zone_label": "データ取得不可",
        "disaster_type": None,
        "disaster_type_label": None,
        "source": "国土交通省 不動産情報ライブラリ",
        "available": False,
        "unavailable_reason": reason,
    }
