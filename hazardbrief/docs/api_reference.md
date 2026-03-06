# HazardBrief API リファレンス

Base URL: `https://<api-gateway-url>/prod/api`

---

## 目次

1. [Properties — 物件管理](#1-properties--物件管理)
2. [Hazard — ハザードデータ取得](#2-hazard--ハザードデータ取得)
3. [Report — レポート生成](#3-report--レポート生成)
4. [Companies — 会社管理](#4-companies--会社管理)

---

## 1. Properties — 物件管理

### `GET /api/properties`

物件一覧を返す。

**Query Parameters**

| パラメータ | 型 | デフォルト | 説明 |
|---|---|---|---|
| `company_id` | string | — | 会社IDでフィルタ |
| `limit` | int | 50 | 最大取得件数 (1〜200) |

**Response** `200 OK`

```json
[
  {
    "id": "abc123",
    "company_id": "company-1",
    "created_by": null,
    "address": "東京都千代田区丸の内1-1-1",
    "latitude": 35.6812,
    "longitude": 139.7671,
    "property_name": "丸の内ビル",
    "notes": "商談メモ",
    "created_at": "2026-03-06T10:00:00"
  }
]
```

---

### `GET /api/properties/{id}`

物件詳細を返す。

**Error** `404` — 物件が見つからない場合

---

### `POST /api/properties`

物件を登録する。緯度経度が省略された場合は国土地理院ジオコーダーで自動取得。

**Request Body**

```json
{
  "address": "東京都千代田区丸の内1-1-1",
  "property_name": "丸の内ビル",
  "notes": "メモ",
  "company_id": "company-1",
  "latitude": 35.6812,
  "longitude": 139.7671
}
```

| フィールド | 型 | 必須 | 説明 |
|---|---|---|---|
| `address` | string | Yes | 住所 |
| `property_name` | string | No | 物件名 |
| `notes` | string | No | メモ |
| `company_id` | string | No | 会社ID |
| `latitude` | float | No | 緯度 (省略時は自動取得) |
| `longitude` | float | No | 経度 (省略時は自動取得) |

**Response** `201 Created`

---

### `DELETE /api/properties/{id}`

物件を削除する (関連ハザードレポートも削除)。

**Response** `200 OK`

```json
{ "property_id": "abc123", "status": "deleted" }
```

**Error** `404` — 物件が見つからない場合

---

## 2. Hazard — ハザードデータ取得

### `GET /api/hazard/{property_id}`

ハザードデータを取得する。キャッシュがある場合はそれを返す (有効期間: 90日)。

**Query Parameters**

| パラメータ | 型 | デフォルト | 説明 |
|---|---|---|---|
| `force_refresh` | bool | false | キャッシュを無視して再取得 |

**Response** `200 OK`

```json
{
  "property_id": "abc123",
  "flood_risk": {
    "level": "medium",
    "depth": "2",
    "depth_label": "0.5〜1.0m未満（床上浸水）",
    "river_name": "多摩川",
    "source": "国土交通省 不動産情報ライブラリ",
    "available": true
  },
  "landslide_risk": {
    "level": "low",
    "zone_type": "none",
    "zone_label": "警戒区域外",
    "disaster_type": null,
    "disaster_type_label": null,
    "source": "国土交通省 不動産情報ライブラリ",
    "available": true
  },
  "tsunami_risk": {
    "level": "low",
    "depth": "0",
    "depth_label": "浸水なし（想定区域外）",
    "source": "国土交通省 不動産情報ライブラリ",
    "available": true
  },
  "ground_risk": {
    "level": "low",
    "elevation": 15.5,
    "description": "標高が高く、地盤リスクは相対的に低い傾向です",
    "liquefaction_note": "標高から判断する限り液状化リスクは標準的です。",
    "source": "国土地理院 標高API",
    "available": true
  },
  "risk_summary": {
    "overall_level": "medium",
    "levels": {
      "flood": "medium",
      "landslide": "low",
      "tsunami": "low",
      "ground": "low"
    },
    "unavailable_count": 0,
    "has_partial_data": false,
    "disclaimer": "本レポートは公的機関が公表するデータを基に..."
  },
  "fetched_at": "2026-03-06T10:00:00",
  "from_cache": false
}
```

**リスクレベル**

| level | 意味 |
|-------|------|
| `low` | 低リスク |
| `medium` | 中程度のリスク |
| `high` | 高リスク |
| `unknown` | データ取得不可 (graceful degradation) |

**Error** `404` — 物件が見つからない場合
**Error** `422` — 緯度経度が設定されていない場合

---

## 3. Report — レポート生成

### `GET /api/report/{property_id}`

防災レポートを生成して返す。事前に `/api/hazard/{id}` の呼び出しが必要。

**Response** `200 OK`

```json
{
  "property": {
    "id": "abc123",
    "address": "東京都千代田区丸の内1-1-1",
    "property_name": "丸の内ビル"
  },
  "report": {
    "cards": [
      {
        "risk_type": "flood",
        "title": "洪水リスク",
        "level": "medium",
        "level_label": "中",
        "level_color": "yellow",
        "available": true,
        "details": {
          "depth_label": "0.5〜1.0m未満（床上浸水）",
          "river_name": "多摩川",
          "source": "国土交通省 不動産情報ライブラリ"
        },
        "description": "想定浸水深: 0.5〜1.0m未満（床上浸水）（多摩川）",
        "mitigation": "床上浸水の可能性があります。家財の高所保管、止水板の設置を検討してください。"
      }
    ],
    "risk_summary": { ... },
    "fetched_at": "2026-03-06T10:00:00",
    "expires_at": "2026-06-04T10:00:00",
    "generated_at": "2026-03-06T10:00:00"
  },
  "disclaimer": "本レポートは公的機関が公表するデータを基に作成しています。..."
}
```

**Error** `404` — 物件が見つからない / ハザードレポートが未取得の場合

---

## 4. Companies — 会社管理

### `GET /api/companies`

会社一覧を返す。

### `GET /api/companies/{id}`

会社詳細を返す。

### `POST /api/companies`

会社を登録する。

**Request Body**

```json
{ "name": "テスト不動産株式会社", "plan": "free" }
```

**Response** `201 Created`

---

## 共通仕様

### エラーレスポンス

```json
{ "detail": "エラーメッセージ" }
```

| ステータスコード | 説明 |
|---|---|
| `400` | リクエストパラメータ不正 |
| `404` | リソースが見つからない |
| `422` | バリデーションエラー |
| `500` | サーバー内部エラー |

---

最終更新: 2026-03-06
