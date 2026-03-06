"""GET /api/report/{property_id} — ハザードレポート生成"""
import json
import logging
import sqlite3
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException

from src.api.storage import get_connection

logger = logging.getLogger(__name__)

router = APIRouter()

# リスクレベルの日本語表記
LEVEL_LABELS = {
    "low": "低",
    "medium": "中",
    "high": "高",
    "unknown": "要確認",
}

LEVEL_COLORS = {
    "low": "green",
    "medium": "yellow",
    "high": "orange",
    "unknown": "gray",
}

# 対策ヒント (リスクレベル別)
MITIGATION_HINTS = {
    "flood": {
        "low": "浸水想定区域外です。ただし局地的な大雨への備えとして排水環境の確認を推奨します。",
        "medium": "床上浸水の可能性があります。家財の高所保管、止水板の設置、ハザードマップの確認を検討してください。",
        "high": "深刻な浸水リスクがあります。避難経路の事前確認、建物の防水対策、保険の見直しを強く推奨します。",
        "unknown": "洪水データを取得できませんでした。市区町村のハザードマップを直接ご確認ください。",
    },
    "landslide": {
        "low": "土砂災害警戒区域外です。大雨の際も安全性は比較的高い立地です。",
        "medium": "土砂災害警戒区域（イエローゾーン）内です。大雨時の避難場所・経路を事前に確認してください。",
        "high": "土砂災害特別警戒区域（レッドゾーン）内です。建築制限がある場合があります。専門家への相談を推奨します。",
        "unknown": "土砂災害データを取得できませんでした。市区町村窓口での確認を推奨します。",
    },
    "tsunami": {
        "low": "津波浸水想定区域外です。ただし内陸部の大規模地震でも被害が及ぶ場合があります。",
        "medium": "津波浸水が想定されます。避難場所（高台・津波避難ビル）の確認を必ず行ってください。",
        "high": "深刻な津波浸水リスクがあります。避難計画の策定と、地域の防災訓練への参加を強く推奨します。",
        "unknown": "津波データを取得できませんでした。沿岸部の場合は特に市区町村の情報をご確認ください。",
    },
    "ground": {
        "low": "標高が高く、地盤リスクは相対的に低い傾向にあります。",
        "medium": "低地に位置しており、地盤調査報告書の内容確認を推奨します。液状化対策済みかも確認してください。",
        "high": "液状化・不同沈下のリスクが懸念されます。地盤改良の実績や建物基礎の仕様を確認してください。",
        "unknown": "地盤データを取得できませんでした。地盤調査会社への相談を推奨します。",
    },
}


@router.get("/report/{property_id}")
def get_report(
    property_id: str,
    conn: sqlite3.Connection = Depends(get_connection),
):
    """
    物件の防災レポートを生成して返す。

    hazard_reports テーブルの最新キャッシュを使用する。
    キャッシュがない場合は 404 を返す (先に /api/hazard/{id} を呼び出すこと)。
    """
    prop = conn.execute(
        """
        SELECT id, address, latitude, longitude, property_name, notes, created_at
        FROM properties WHERE id = ?
        """,
        (property_id,),
    ).fetchone()

    if not prop:
        raise HTTPException(status_code=404, detail=f"property not found: {property_id}")

    report_row = conn.execute(
        """
        SELECT flood_risk, landslide_risk, tsunami_risk, ground_risk, risk_summary,
               fetched_at, expires_at
        FROM hazard_reports
        WHERE property_id = ?
        ORDER BY fetched_at DESC
        LIMIT 1
        """,
        (property_id,),
    ).fetchone()

    if not report_row:
        raise HTTPException(
            status_code=404,
            detail="ハザードデータがまだ取得されていません。先に /api/hazard/{property_id} を呼び出してください。",
        )

    flood_risk = json.loads(report_row["flood_risk"] or "{}")
    landslide_risk = json.loads(report_row["landslide_risk"] or "{}")
    tsunami_risk = json.loads(report_row["tsunami_risk"] or "{}")
    ground_risk = json.loads(report_row["ground_risk"] or "{}")
    risk_summary = json.loads(report_row["risk_summary"] or "{}")

    # レポートカード生成
    cards = _build_risk_cards(flood_risk, landslide_risk, tsunami_risk, ground_risk)

    return {
        "property": dict(prop),
        "report": {
            "cards": cards,
            "risk_summary": risk_summary,
            "fetched_at": report_row["fetched_at"],
            "expires_at": report_row["expires_at"],
            "generated_at": datetime.utcnow().isoformat(),
        },
        "disclaimer": (
            "本レポートは公的機関が公表するデータを基に作成しています。"
            "ハザードマップは想定最大規模の災害を示すものであり、"
            "実際の被害程度は地形・建物構造・気象条件等により異なります。"
            "物件の安全性判断は、現地確認・専門家への相談と合わせてご活用ください。"
            "データ出典: 国土交通省ハザードマップポータルサイト"
        ),
    }


def _build_risk_cards(flood: dict, landslide: dict, tsunami: dict, ground: dict) -> list:
    """各リスクのカード情報を生成する。"""
    cards = []

    # 洪水リスクカード
    flood_level = flood.get("level", "unknown")
    cards.append({
        "risk_type": "flood",
        "title": "洪水リスク",
        "level": flood_level,
        "level_label": LEVEL_LABELS.get(flood_level, "要確認"),
        "level_color": LEVEL_COLORS.get(flood_level, "gray"),
        "available": flood.get("available", False),
        "details": {
            "depth_label": flood.get("depth_label", ""),
            "river_name": flood.get("river_name"),
            "source": flood.get("source", ""),
        },
        "description": _get_flood_description(flood),
        "mitigation": MITIGATION_HINTS["flood"].get(flood_level, ""),
    })

    # 土砂災害リスクカード
    landslide_level = landslide.get("level", "unknown")
    cards.append({
        "risk_type": "landslide",
        "title": "土砂災害リスク",
        "level": landslide_level,
        "level_label": LEVEL_LABELS.get(landslide_level, "要確認"),
        "level_color": LEVEL_COLORS.get(landslide_level, "gray"),
        "available": landslide.get("available", False),
        "details": {
            "zone_label": landslide.get("zone_label", ""),
            "disaster_type_label": landslide.get("disaster_type_label"),
            "source": landslide.get("source", ""),
        },
        "description": _get_landslide_description(landslide),
        "mitigation": MITIGATION_HINTS["landslide"].get(landslide_level, ""),
    })

    # 津波リスクカード
    tsunami_level = tsunami.get("level", "unknown")
    cards.append({
        "risk_type": "tsunami",
        "title": "津波リスク",
        "level": tsunami_level,
        "level_label": LEVEL_LABELS.get(tsunami_level, "要確認"),
        "level_color": LEVEL_COLORS.get(tsunami_level, "gray"),
        "available": tsunami.get("available", False),
        "details": {
            "depth_label": tsunami.get("depth_label", ""),
            "source": tsunami.get("source", ""),
        },
        "description": _get_tsunami_description(tsunami),
        "mitigation": MITIGATION_HINTS["tsunami"].get(tsunami_level, ""),
    })

    # 地盤リスクカード
    ground_level = ground.get("level", "unknown")
    cards.append({
        "risk_type": "ground",
        "title": "地盤リスク",
        "level": ground_level,
        "level_label": LEVEL_LABELS.get(ground_level, "要確認"),
        "level_color": LEVEL_COLORS.get(ground_level, "gray"),
        "available": ground.get("available", False),
        "details": {
            "elevation": ground.get("elevation"),
            "description": ground.get("description", ""),
            "source": ground.get("source", ""),
        },
        "description": ground.get("description", "地盤情報を取得できませんでした"),
        "mitigation": MITIGATION_HINTS["ground"].get(ground_level, ""),
    })

    return cards


def _get_flood_description(flood: dict) -> str:
    if not flood.get("available"):
        return "洪水リスクデータを取得できませんでした。"
    depth_label = flood.get("depth_label", "")
    river = flood.get("river_name")
    base = f"想定浸水深: {depth_label}"
    if river:
        base += f"（{river}）"
    return base


def _get_landslide_description(landslide: dict) -> str:
    if not landslide.get("available"):
        return "土砂災害リスクデータを取得できませんでした。"
    zone_label = landslide.get("zone_label", "")
    disaster_type = landslide.get("disaster_type_label")
    base = zone_label
    if disaster_type:
        base += f"（{disaster_type}）"
    return base


def _get_tsunami_description(tsunami: dict) -> str:
    if not tsunami.get("available"):
        return "津波リスクデータを取得できませんでした。"
    return f"想定浸水深: {tsunami.get('depth_label', '')}"
