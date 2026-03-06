"""災害データ取得モジュール (raw layer only)

データソース:
  - JMA (気象庁): 地震情報、気象警報、津波情報
  - USGS: 日本周辺の地震情報 (GeoJSON)
"""
import logging
from datetime import date, timedelta
from typing import Optional

import requests

logger = logging.getLogger(__name__)

_JMA_QUAKE_LIST_URL = "https://www.jma.go.jp/bosai/quake/data/list.json"
_JMA_QUAKE_DETAIL_URL = "https://www.jma.go.jp/bosai/quake/data/{filename}"
_JMA_WARNING_MAP_URL = "https://www.jma.go.jp/bosai/warning/data/warning/map.json"
_JMA_TSUNAMI_URL = "https://www.jma.go.jp/bosai/tsunami/data/list.json"
_USGS_QUERY_URL = "https://earthquake.usgs.gov/fdsnws/event/1/query"

_TIMEOUT = 15

# JMA 警報コード (注意報を除く: 警報・特別警報のみ)
# https://www.jma.go.jp/jma/kishou/know/bosai/warning_code.html
_WARNING_CODES = {
    "02", "03", "04", "05", "06", "07", "08",  # 警報
    "10", "11", "12", "13", "14", "15", "16", "17", "18", "19",  # 特別警報
    "32", "33",  # 暴風雪/暴風 警報 (海上)
}


def fetch_jma_earthquakes(target_date: str) -> int:
    """JMA 地震情報を取得し raw layer に保存する。

    list.json から target_date の地震をフィルタし保存。
    震度4以上のイベントは詳細 JSON も取得して保存する。

    Returns:
        保存した地震イベント数
    """
    from src.pipeline.raw_store import save_raw

    resp = requests.get(_JMA_QUAKE_LIST_URL, timeout=_TIMEOUT)
    resp.raise_for_status()
    all_quakes = resp.json()

    # at フィールドの日付部分で target_date をフィルタ
    filtered = [q for q in all_quakes if q.get("at", "").startswith(target_date)]

    if not filtered:
        logger.info(f"JMA 地震: {target_date} のイベントなし")
        return 0

    save_raw("disaster", "natural", "jma", "earthquake_list", target_date, filtered)

    # 震度4以上の詳細を取得
    significant = [q for q in filtered if _parse_intensity(q.get("maxi", "0")) >= 4]
    if significant:
        details = []
        for quake in significant:
            filename = quake.get("json")
            if not filename:
                continue
            try:
                detail_resp = requests.get(
                    _JMA_QUAKE_DETAIL_URL.format(filename=filename),
                    timeout=_TIMEOUT,
                )
                detail_resp.raise_for_status()
                details.append(detail_resp.json())
            except Exception as e:
                logger.warning(f"JMA 地震詳細取得失敗 ({filename}): {e}")

        if details:
            save_raw(
                "disaster", "natural", "jma", "earthquake_detail",
                target_date, details,
            )

    logger.info(f"JMA 地震: {len(filtered)} 件 (震度4+: {len(significant)} 件)")
    return len(filtered)


def fetch_jma_warnings(target_date: str) -> int:
    """JMA 気象警報を取得し raw layer に保存する。

    map.json から警報以上が発表中のエリアのみ抽出して保存。
    注意報のみの日は保存しない。

    Returns:
        アクティブな警報エリア数
    """
    from src.pipeline.raw_store import save_raw

    resp = requests.get(_JMA_WARNING_MAP_URL, timeout=_TIMEOUT)
    resp.raise_for_status()
    all_data = resp.json()

    # 警報以上が発表中のエリアを抽出
    warning_areas = []
    for prefecture in all_data:
        for area_type in prefecture.get("areaTypes", []):
            for area in area_type.get("areas", []):
                active_warnings = [
                    w for w in area.get("warnings", [])
                    if w.get("code") in _WARNING_CODES
                    and w.get("status") != "解除"
                ]
                if active_warnings:
                    warning_areas.append({
                        "code": area.get("code"),
                        "warnings": active_warnings,
                        "reportDatetime": prefecture.get("reportDatetime"),
                    })

    if not warning_areas:
        logger.info(f"JMA 警報: {target_date} アクティブな警報なし")
        return 0

    save_raw("disaster", "natural", "jma", "warning_map", target_date, warning_areas)
    logger.info(f"JMA 警報: {len(warning_areas)} エリアで警報発表中")
    return len(warning_areas)


def fetch_jma_tsunami(target_date: str) -> int:
    """JMA 津波情報を取得し raw layer に保存する。

    空配列 (警報なし) の場合は保存しない。

    Returns:
        アクティブな津波警報数
    """
    from src.pipeline.raw_store import save_raw

    resp = requests.get(_JMA_TSUNAMI_URL, timeout=_TIMEOUT)
    resp.raise_for_status()
    data = resp.json()

    if not data:
        logger.info(f"JMA 津波: {target_date} アクティブな津波警報なし")
        return 0

    save_raw("disaster", "natural", "jma", "tsunami", target_date, data)
    logger.info(f"JMA 津波: {len(data)} 件の津波警報")
    return len(data)


def fetch_usgs_earthquakes(target_date: str) -> int:
    """USGS 地震情報 (日本周辺 M3.0+) を取得し raw layer に保存する。

    Returns:
        保存した地震イベント数
    """
    from src.pipeline.raw_store import save_raw

    end_date = (date.fromisoformat(target_date) + timedelta(days=1)).isoformat()
    params = {
        "format": "geojson",
        "starttime": target_date,
        "endtime": end_date,
        "minlatitude": 30,
        "maxlatitude": 46,
        "minlongitude": 128,
        "maxlongitude": 146,
        "minmagnitude": 3.0,
        "orderby": "time",
    }

    resp = requests.get(_USGS_QUERY_URL, params=params, timeout=_TIMEOUT)
    resp.raise_for_status()
    data = resp.json()

    features = data.get("features", [])
    if not features:
        logger.info(f"USGS 地震: {target_date} 日本周辺 M3.0+ なし")
        return 0

    save_raw("disaster", "natural", "usgs", "earthquake", target_date, data)
    logger.info(f"USGS 地震: {len(features)} 件 (日本周辺 M3.0+)")
    return len(features)


def fetch_all_disaster_data(target_date: Optional[str] = None) -> dict:
    """全災害データソースを取得する。各ソースは独立してエラーハンドリング。

    Returns:
        {"jma_earthquakes": N, "jma_warnings": N, "jma_tsunami": N, "usgs_earthquakes": N}
    """
    if target_date is None:
        target_date = date.today().isoformat()

    result = {
        "jma_earthquakes": 0,
        "jma_warnings": 0,
        "jma_tsunami": 0,
        "usgs_earthquakes": 0,
    }

    for key, func in [
        ("jma_earthquakes", fetch_jma_earthquakes),
        ("jma_warnings", fetch_jma_warnings),
        ("jma_tsunami", fetch_jma_tsunami),
        ("usgs_earthquakes", fetch_usgs_earthquakes),
    ]:
        try:
            result[key] = func(target_date)
        except Exception as e:
            logger.error(f"{key} 取得失敗 (処理は継続): {e}")

    return result


def _parse_intensity(maxi: str) -> int:
    """JMA 震度文字列を数値に変換する。

    "5-" → 5, "5+" → 5, "6-" → 6, "6+" → 6, "1" → 1, etc.
    """
    if not maxi:
        return 0
    cleaned = maxi.replace("-", "").replace("+", "")
    try:
        return int(cleaned)
    except ValueError:
        return 0
