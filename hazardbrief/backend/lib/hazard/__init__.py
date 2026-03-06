"""HazardBrief ハザードデータ取得 — 統合インターフェース

asyncio.gather(return_exceptions=True) で全リスクを並列取得し、
個別の失敗は graceful degradation (フォールバック表示) で対応する。
"""
import asyncio
import logging

from lib.hazard.flood import get_flood_risk
from lib.hazard.ground import get_ground_risk
from lib.hazard.landslide import get_landslide_risk
from lib.hazard.tsunami import get_tsunami_risk

logger = logging.getLogger(__name__)

# リスクレベルの優先順位 (高い方を採用)
_LEVEL_PRIORITY = {"high": 3, "medium": 2, "low": 1, "unknown": 0}


async def fetch_all_hazards(lat: float, lon: float) -> dict:
    """
    全ハザードリスクを並列取得する。

    個別の失敗は exception オブジェクトとして返り、フォールバック表示に切り替える。
    Promise.allSettled 相当の動作。

    Returns:
        {
            "flood_risk": dict,
            "landslide_risk": dict,
            "tsunami_risk": dict,
            "ground_risk": dict,
            "risk_summary": dict,
        }
    """
    results = await asyncio.gather(
        get_flood_risk(lat, lon),
        get_landslide_risk(lat, lon),
        get_tsunami_risk(lat, lon),
        get_ground_risk(lat, lon),
        return_exceptions=True,
    )

    flood_result, landslide_result, tsunami_result, ground_result = results

    # Exception の場合はフォールバックに変換
    flood_risk = _handle_exception(flood_result, "flood")
    landslide_risk = _handle_exception(landslide_result, "landslide")
    tsunami_risk = _handle_exception(tsunami_result, "tsunami")
    ground_risk = _handle_exception(ground_result, "ground")

    risk_summary = _compute_summary(flood_risk, landslide_risk, tsunami_risk, ground_risk)

    return {
        "flood_risk": flood_risk,
        "landslide_risk": landslide_risk,
        "tsunami_risk": tsunami_risk,
        "ground_risk": ground_risk,
        "risk_summary": risk_summary,
    }


def _handle_exception(result, risk_type: str) -> dict:
    """例外が発生した場合はフォールバックレスポンスを返す。"""
    if isinstance(result, Exception):
        logger.error(f"{risk_type} リスク取得で例外発生: {result}")
        return {
            "level": "unknown",
            "available": False,
            "unavailable_reason": f"予期しないエラー: {type(result).__name__}",
        }
    return result


def _compute_summary(flood: dict, landslide: dict, tsunami: dict, ground: dict) -> dict:
    """
    各リスクから統合サマリーを計算する。

    全リスクの中で最も高いレベルを overall_level として返す。
    """
    risks = {
        "flood": flood,
        "landslide": landslide,
        "tsunami": tsunami,
        "ground": ground,
    }

    levels = {
        name: data.get("level", "unknown")
        for name, data in risks.items()
    }

    # 最大リスクレベルを計算 (unknown は除く)
    known_levels = [lv for lv in levels.values() if lv != "unknown"]
    if not known_levels:
        overall_level = "unknown"
    else:
        overall_level = max(known_levels, key=lambda lv: _LEVEL_PRIORITY.get(lv, 0))

    # 取得できなかった項目数
    unavailable_count = sum(1 for d in risks.values() if not d.get("available", True))

    return {
        "overall_level": overall_level,
        "levels": levels,
        "unavailable_count": unavailable_count,
        "has_partial_data": unavailable_count > 0,
        "disclaimer": (
            "本レポートは公的機関が公表するデータを基に作成しています。"
            "ハザードマップは想定最大規模の災害を示すものであり、"
            "実際の被害程度は地形・建物構造・気象条件等により異なります。"
            "物件の安全性判断は、現地確認・専門家への相談と合わせてご活用ください。"
            "データ出典: 国土交通省ハザードマップポータルサイト"
        ),
    }
