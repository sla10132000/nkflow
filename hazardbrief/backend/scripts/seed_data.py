"""HazardBrief シードデータ投入スクリプト

テスト・開発用のサンプルデータを投入する。
事前に init_sqlite.py でスキーマを作成しておくこと。

実行例:
    python scripts/seed_data.py /tmp/hazardbrief.db
"""
import json
import sqlite3
import sys
from datetime import datetime, timedelta


COMPANIES = [
    {
        "id": "company-001",
        "name": "サンプル不動産株式会社",
        "plan": "standard",
    },
    {
        "id": "company-002",
        "name": "テスト住宅販売",
        "plan": "free",
    },
]

PROFILES = [
    {
        "id": "profile-001",
        "company_id": "company-001",
        "full_name": "山田 太郎",
        "email": "yamada@sample-fudosan.co.jp",
        "role": "admin",
    },
    {
        "id": "profile-002",
        "company_id": "company-001",
        "full_name": "鈴木 花子",
        "email": "suzuki@sample-fudosan.co.jp",
        "role": "agent",
    },
    {
        "id": "profile-003",
        "company_id": "company-002",
        "full_name": "佐藤 次郎",
        "email": "sato@test-jutaku.co.jp",
        "role": "admin",
    },
]

# 実際の住所と緯度経度（都内・神奈川エリアのサンプル）
PROPERTIES = [
    {
        "id": "prop-001",
        "company_id": "company-001",
        "created_by": "profile-001",
        "address": "東京都江東区豊洲3丁目1番",
        "latitude": 35.6558,
        "longitude": 139.7956,
        "property_name": "豊洲ベイサイドマンション",
        "notes": "臨海部・埋立地。液状化リスクと洪水リスク要確認。",
    },
    {
        "id": "prop-002",
        "company_id": "company-001",
        "created_by": "profile-002",
        "address": "東京都世田谷区成城4丁目1番",
        "latitude": 35.6337,
        "longitude": 139.5897,
        "property_name": "成城高台邸宅",
        "notes": "台地上・高標高。洪水リスク低、土砂リスク要確認。",
    },
    {
        "id": "prop-003",
        "company_id": "company-001",
        "created_by": "profile-001",
        "address": "神奈川県鎌倉市由比ガ浜2丁目1番",
        "latitude": 35.3136,
        "longitude": 139.5452,
        "property_name": "由比ガ浜海岸物件",
        "notes": "海岸沿い。津波・高潮リスクが高い地域。",
    },
    {
        "id": "prop-004",
        "company_id": "company-002",
        "created_by": "profile-003",
        "address": "東京都新宿区西新宿2丁目8番",
        "latitude": 35.6896,
        "longitude": 139.6917,
        "property_name": "西新宿オフィスビル",
        "notes": "都市部・商業地域。",
    },
    {
        "id": "prop-005",
        "company_id": "company-002",
        "created_by": "profile-003",
        "address": "神奈川県横浜市中区山下町1番",
        "latitude": 35.4436,
        "longitude": 139.6480,
        "property_name": "山下公園前マンション",
        "notes": "みなとみらい近接。海岸低地、津波リスク要確認。",
    },
]

# サンプルハザードレポート（豊洲・由比ガ浜のみ生成済みとする）
def make_hazard_reports() -> list[dict]:
    expires_at = (datetime.now() + timedelta(days=90)).strftime("%Y-%m-%dT%H:%M:%S")

    # 豊洲（埋立地・液状化リスク高）
    toyosu_flood = {
        "level": "high",
        "depth_m": 2.0,
        "description": "想定最大規模の洪水で2m以上の浸水が想定されます。",
        "source": "国土交通省 不動産情報ライブラリ",
    }
    toyosu_ground = {
        "level": "high",
        "elevation_m": 1.2,
        "land_type": "埋立地",
        "liquefaction_risk": "高",
        "description": "埋立地のため液状化リスクが高く、地盤改良の確認が必要です。",
        "source": "国土地理院 標高API",
    }
    toyosu_summary = {
        "overall_level": "high",
        "flood": "high",
        "landslide": "low",
        "tsunami": "medium",
        "ground": "high",
        "key_risks": ["洪水浸水（2m以上）", "液状化リスク（埋立地）", "津波浸水"],
        "recommendations": ["耐震・免震構造の確認", "地盤改良工事履歴の確認", "ハザードマップを顧客に提示"],
    }

    # 由比ガ浜（海岸・津波リスク高）
    yuigahama_tsunami = {
        "level": "high",
        "depth_m": 5.0,
        "description": "想定最大規模の津波で5m以上の浸水が想定されます。避難経路の確認が重要です。",
        "source": "国土交通省 不動産情報ライブラリ",
    }
    yuigahama_ground = {
        "level": "medium",
        "elevation_m": 3.5,
        "land_type": "海岸低地",
        "liquefaction_risk": "中",
        "description": "海岸低地で標高が低く、高潮・津波時の浸水リスクがあります。",
        "source": "国土地理院 標高API",
    }
    yuigahama_summary = {
        "overall_level": "high",
        "flood": "medium",
        "landslide": "low",
        "tsunami": "high",
        "ground": "medium",
        "key_risks": ["津波浸水（5m以上）", "高潮リスク", "海岸低地"],
        "recommendations": ["津波避難ビル・避難経路の確認", "防潮扉・止水板の設置可否確認", "顧客への丁寧な説明と書面交付"],
    }

    return [
        {
            "id": "report-001",
            "property_id": "prop-001",
            "flood_risk": json.dumps(toyosu_flood, ensure_ascii=False),
            "landslide_risk": json.dumps({"level": "low", "description": "土砂災害警戒区域外です。", "source": "国土交通省"}, ensure_ascii=False),
            "tsunami_risk": json.dumps({"level": "medium", "depth_m": 1.0, "description": "津波浸水想定区域（1m未満）です。", "source": "国土交通省"}, ensure_ascii=False),
            "ground_risk": json.dumps(toyosu_ground, ensure_ascii=False),
            "risk_summary": json.dumps(toyosu_summary, ensure_ascii=False),
            "expires_at": expires_at,
        },
        {
            "id": "report-002",
            "property_id": "prop-003",
            "flood_risk": json.dumps({"level": "medium", "depth_m": 0.5, "description": "洪水浸水想定区域（0.5m未満）です。", "source": "国土交通省"}, ensure_ascii=False),
            "landslide_risk": json.dumps({"level": "low", "description": "土砂災害警戒区域外です。", "source": "国土交通省"}, ensure_ascii=False),
            "tsunami_risk": json.dumps(yuigahama_tsunami, ensure_ascii=False),
            "ground_risk": json.dumps(yuigahama_ground, ensure_ascii=False),
            "risk_summary": json.dumps(yuigahama_summary, ensure_ascii=False),
            "expires_at": expires_at,
        },
    ]


def seed(db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

    # companies
    for c in COMPANIES:
        conn.execute(
            "INSERT OR IGNORE INTO companies (id, name, plan, created_at) VALUES (?, ?, ?, ?)",
            (c["id"], c["name"], c["plan"], now),
        )
    print(f"  companies: {len(COMPANIES)} 件")

    # profiles
    for p in PROFILES:
        conn.execute(
            "INSERT OR IGNORE INTO profiles (id, company_id, full_name, email, role, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (p["id"], p["company_id"], p["full_name"], p["email"], p["role"], now),
        )
    print(f"  profiles:  {len(PROFILES)} 件")

    # properties
    for p in PROPERTIES:
        conn.execute(
            """INSERT OR IGNORE INTO properties
               (id, company_id, created_by, address, latitude, longitude, property_name, notes, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (p["id"], p["company_id"], p["created_by"], p["address"],
             p["latitude"], p["longitude"], p["property_name"], p["notes"], now),
        )
    print(f"  properties: {len(PROPERTIES)} 件")

    # hazard_reports
    reports = make_hazard_reports()
    for r in reports:
        conn.execute(
            """INSERT OR IGNORE INTO hazard_reports
               (id, property_id, flood_risk, landslide_risk, tsunami_risk, ground_risk, risk_summary, fetched_at, expires_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (r["id"], r["property_id"], r["flood_risk"], r["landslide_risk"],
             r["tsunami_risk"], r["ground_risk"], r["risk_summary"], now, r["expires_at"]),
        )
    print(f"  hazard_reports: {len(reports)} 件 (豊洲・由比ガ浜)")

    conn.commit()
    conn.close()
    print(f"\nシードデータ投入完了: {db_path}")
    print("\n--- 登録内容 ---")
    print("会社: サンプル不動産株式会社 (standard), テスト住宅販売 (free)")
    print("ユーザー: 山田太郎(admin), 鈴木花子(agent), 佐藤次郎(admin)")
    print("物件: 豊洲・成城・由比ガ浜・西新宿・山下町 の5件")
    print("レポート生成済み: 豊洲（洪水・液状化高）, 由比ガ浜（津波高）")


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "/tmp/hazardbrief.db"
    seed(path)
