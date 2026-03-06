"""国土地理院ジオコーダー API で住所→緯度経度を取得"""
import logging
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

GSI_GEOCODER_URL = "https://msearch.gsi.go.jp/address-search/AddressSearch"


async def geocode_address(address: str) -> Optional[dict]:
    """
    国土地理院ジオコーダー API で住所を緯度経度に変換する。

    Args:
        address: 住所文字列 (例: "東京都千代田区丸の内1-1-1")

    Returns:
        {"latitude": float, "longitude": float, "display_name": str} or None (失敗時)
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                GSI_GEOCODER_URL,
                params={"q": address},
            )
            resp.raise_for_status()
            data = resp.json()

        if not data or not isinstance(data, list):
            logger.warning(f"ジオコーディング結果なし: {address}")
            return None

        # 最初の結果を使用
        first = data[0]
        geometry = first.get("geometry", {})
        coordinates = geometry.get("coordinates", [])
        if len(coordinates) < 2:
            return None

        longitude, latitude = coordinates[0], coordinates[1]
        display_name = first.get("properties", {}).get("title", address)

        return {
            "latitude": float(latitude),
            "longitude": float(longitude),
            "display_name": display_name,
        }

    except httpx.HTTPError as e:
        logger.error(f"ジオコーディング HTTP エラー: {e}")
        return None
    except Exception as e:
        logger.error(f"ジオコーディング失敗: {e}")
        return None
