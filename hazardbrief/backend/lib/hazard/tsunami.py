"""国交省 不動産情報ライブラリ API で津波リスクを取得"""
import logging
import os

import httpx

logger = logging.getLogger(__name__)

REINFOLIB_BASE_URL = "https://www.reinfolib.mlit.go.jp/ex-api/external"

TSUNAMI_DEPTH_LABELS = {
    "0": "浸水なし（想定区域外）",
    "1": "0〜1.0m未満",
    "2": "1.0〜2.0m未満",
    "3": "2.0〜5.0m未満",
    "4": "5.0〜10.0m未満",
    "5": "10.0〜20.0m未満",
    "6": "20.0m以上",
}


async def get_tsunami_risk(lat: float, lon: float, zoom: int = 15) -> dict:
    """
    国交省 不動産情報ライブラリ API から津波浸水想定データを取得する。

    Returns:
        {
            "level": str,
            "depth": str | None,
            "depth_label": str,
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
                f"{REINFOLIB_BASE_URL}/XIT003",
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
                "depth": "0",
                "depth_label": TSUNAMI_DEPTH_LABELS["0"],
                "source": "国土交通省 不動産情報ライブラリ",
                "available": True,
            }

        max_depth = 0
        for feature in features:
            props = feature.get("properties", {})
            try:
                depth_val = int(str(props.get("depth", "0")))
                if depth_val > max_depth:
                    max_depth = depth_val
            except (ValueError, TypeError):
                pass

        depth_key = str(max_depth)
        level = _depth_to_level(max_depth)

        return {
            "level": level,
            "depth": depth_key,
            "depth_label": TSUNAMI_DEPTH_LABELS.get(depth_key, "不明"),
            "source": "国土交通省 不動産情報ライブラリ",
            "available": True,
        }

    except httpx.HTTPStatusError as e:
        logger.error(f"津波リスク取得 HTTP エラー: {e.response.status_code}")
        return _unavailable_response(f"API エラー: {e.response.status_code}")
    except Exception as e:
        logger.error(f"津波リスク取得失敗: {e}")
        return _unavailable_response(str(e))


def _depth_to_level(depth: int) -> str:
    if depth == 0:
        return "low"
    elif depth <= 2:
        return "medium"
    else:
        return "high"


def _unavailable_response(reason: str) -> dict:
    return {
        "level": "unknown",
        "depth": None,
        "depth_label": "データ取得不可",
        "source": "国土交通省 不動産情報ライブラリ",
        "available": False,
        "unavailable_reason": reason,
    }
