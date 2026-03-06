"""国土地理院 標高API で地盤リスクを取得"""
import logging

import httpx

logger = logging.getLogger(__name__)

GSI_ELEVATION_URL = "https://cyberjapandata2.gsi.go.jp/general/dem/scripts/getelevation.php"

# 標高と地盤リスクの目安
# 海抜が低いほど液状化・洪水リスクが高い傾向にある
ELEVATION_RISK_THRESHOLDS = [
    (0, "low", "標高が高く、地盤リスクは相対的に低い傾向"),
    (5, "low", "標高はやや高め。地盤状況は現地確認を推奨"),
    (10, "medium", "標高が低め。液状化リスクに注意が必要な可能性"),
    (float("inf"), "high", "海抜が低い。液状化・洪水リスクの現地確認を推奨"),
]


async def get_ground_risk(lat: float, lon: float) -> dict:
    """
    国土地理院 標高API から地盤リスク情報を取得する。

    Returns:
        {
            "level": str,
            "elevation": float | None,
            "description": str,
            "liquefaction_note": str,
            "source": str,
            "available": bool,
        }
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                GSI_ELEVATION_URL,
                params={
                    "lon": lon,
                    "lat": lat,
                    "outtype": "JSON",
                },
            )
            resp.raise_for_status()
            data = resp.json()

        elevation = data.get("elevation")
        if elevation is None or elevation == "-----":
            return {
                "level": "unknown",
                "elevation": None,
                "description": "標高データを取得できませんでした（海上または離島の可能性）",
                "liquefaction_note": "液状化リスクの評価には現地調査が必要です",
                "source": "国土地理院 標高API",
                "available": False,
                "unavailable_reason": "標高データなし",
            }

        elevation_val = float(elevation)
        level, description = _elevation_to_risk(elevation_val)

        # 海抜5m以下は液状化リスクの注記を付加
        liquefaction_note = (
            "標高が低い地域では液状化リスクが高まる場合があります。地盤調査報告書の確認を推奨します。"
            if elevation_val < 5
            else "標高から判断する限り液状化リスクは標準的です。詳細は地盤調査をご確認ください。"
        )

        return {
            "level": level,
            "elevation": elevation_val,
            "description": description,
            "liquefaction_note": liquefaction_note,
            "source": "国土地理院 標高API",
            "available": True,
        }

    except httpx.HTTPError as e:
        logger.error(f"標高API HTTP エラー: {e}")
        return _unavailable_response(str(e))
    except Exception as e:
        logger.error(f"地盤リスク取得失敗: {e}")
        return _unavailable_response(str(e))


def _elevation_to_risk(elevation: float) -> tuple[str, str]:
    """標高からリスクレベルと説明を返す。"""
    if elevation >= 10:
        return "low", "標高が高く、地盤リスクは相対的に低い傾向です"
    elif elevation >= 5:
        return "low", "標高はやや高め。地盤状況は現地確認を推奨します"
    elif elevation >= 0:
        return "medium", "標高が低め。液状化・浸水リスクに注意が必要な可能性があります"
    else:
        return "high", "海抜がマイナスのエリア。液状化・浸水リスクの現地確認を強く推奨します"


def _unavailable_response(reason: str) -> dict:
    return {
        "level": "unknown",
        "elevation": None,
        "description": "地盤情報を取得できませんでした",
        "liquefaction_note": "液状化リスクの評価には現地調査が必要です",
        "source": "国土地理院 標高API",
        "available": False,
        "unavailable_reason": reason,
    }
