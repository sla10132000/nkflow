"""国交省 不動産情報ライブラリ API で洪水リスクを取得"""
import logging
import os
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

REINFOLIB_BASE_URL = "https://www.reinfolib.mlit.go.jp/ex-api/external"

# 洪水浸水深レベルの説明
FLOOD_DEPTH_LABELS = {
    "0": "浸水なし（想定区域外）",
    "1": "0〜0.5m未満（床下浸水）",
    "2": "0.5〜1.0m未満（床上浸水）",
    "3": "1.0〜2.0m未満（1階浸水）",
    "4": "2.0〜3.0m未満（1〜2階浸水）",
    "5": "3.0〜5.0m未満（2階浸水）",
    "6": "5.0〜10.0m未満（2階以上浸水）",
    "7": "10.0〜20.0m未満（大規模浸水）",
    "8": "20.0m以上（壊滅的浸水）",
}


async def get_flood_risk(lat: float, lon: float, zoom: int = 15) -> dict:
    """
    国交省 不動産情報ライブラリ API から洪水浸水想定区域データを取得する。

    Args:
        lat: 緯度
        lon: 経度
        zoom: タイルズームレベル (デフォルト: 15)

    Returns:
        {
            "level": str,          # リスクレベル (low/medium/high/unknown)
            "depth": str | None,   # 浸水深カテゴリ
            "depth_label": str,    # 浸水深の説明
            "river_name": str | None,
            "source": str,
            "available": bool,
        }
    """
    api_key = os.environ.get("REINFOLIB_API_KEY", "")
    if not api_key:
        logger.warning("REINFOLIB_API_KEY 未設定 — 洪水リスクはダミーデータを返します")
        return _unavailable_response("REINFOLIB_API_KEY が設定されていません")

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"{REINFOLIB_BASE_URL}/XIT001",
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
                "depth_label": FLOOD_DEPTH_LABELS["0"],
                "river_name": None,
                "source": "国土交通省 不動産情報ライブラリ",
                "available": True,
            }

        # 最も深い浸水深を採用
        max_depth = 0
        river_name = None
        for feature in features:
            props = feature.get("properties", {})
            depth_str = str(props.get("depth", "0"))
            try:
                depth_val = int(depth_str)
                if depth_val > max_depth:
                    max_depth = depth_val
                    river_name = props.get("A31b_201", None) or props.get("river_name", None)
            except (ValueError, TypeError):
                pass

        depth_key = str(max_depth)
        level = _depth_to_level(max_depth)

        return {
            "level": level,
            "depth": depth_key,
            "depth_label": FLOOD_DEPTH_LABELS.get(depth_key, "不明"),
            "river_name": river_name,
            "source": "国土交通省 不動産情報ライブラリ",
            "available": True,
        }

    except httpx.HTTPStatusError as e:
        if e.response.status_code == 401:
            logger.error("REINFOLIB_API_KEY が無効です")
            return _unavailable_response("APIキーが無効です")
        logger.error(f"洪水リスク取得 HTTP エラー: {e.response.status_code}")
        return _unavailable_response(f"API エラー: {e.response.status_code}")
    except Exception as e:
        logger.error(f"洪水リスク取得失敗: {e}")
        return _unavailable_response(str(e))


def _depth_to_level(depth: int) -> str:
    """浸水深カテゴリからリスクレベルを返す。"""
    if depth == 0:
        return "low"
    elif depth <= 2:
        return "medium"
    elif depth <= 5:
        return "high"
    else:
        return "high"


def _unavailable_response(reason: str) -> dict:
    """データ取得不可時のフォールバックレスポンス。"""
    return {
        "level": "unknown",
        "depth": None,
        "depth_label": "データ取得不可",
        "river_name": None,
        "source": "国土交通省 不動産情報ライブラリ",
        "available": False,
        "unavailable_reason": reason,
    }
