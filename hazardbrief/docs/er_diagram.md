# ER図 — HazardBrief データベーススキーマ

## hazardbrief.db

```mermaid
erDiagram

    %% ========== テナント ==========
    companies {
        TEXT id PK
        TEXT name
        TEXT plan
        TEXT created_at
    }

    %% ========== ユーザー ==========
    profiles {
        TEXT id PK
        TEXT company_id FK
        TEXT full_name
        TEXT email
        TEXT role
        TEXT created_at
    }

    %% ========== 物件 ==========
    properties {
        TEXT id PK
        TEXT company_id FK
        TEXT created_by FK
        TEXT address
        REAL latitude
        REAL longitude
        TEXT property_name
        TEXT notes
        TEXT created_at
    }

    %% ========== ハザードレポートキャッシュ ==========
    hazard_reports {
        TEXT id PK
        TEXT property_id FK
        TEXT flood_risk
        TEXT landslide_risk
        TEXT tsunami_risk
        TEXT ground_risk
        TEXT risk_summary
        TEXT fetched_at
        TEXT expires_at
    }

    %% ========== リレーション ==========
    companies ||--o{ profiles : "1社 : Nユーザー"
    companies ||--o{ properties : "1社 : N物件"
    profiles ||--o{ properties : "1ユーザー : N物件"
    properties ||--o{ hazard_reports : "1物件 : Nレポートキャッシュ"
```

## テーブル詳細

### companies (会社・テナント)

| カラム | 型 | 説明 |
|--------|-----|------|
| id | TEXT | UUID (random hex) |
| name | TEXT | 会社名 |
| plan | TEXT | プラン (free/standard/enterprise) |
| created_at | TEXT | 作成日時 |

### profiles (ユーザー)

| カラム | 型 | 説明 |
|--------|-----|------|
| id | TEXT | Auth0 ユーザーID |
| company_id | TEXT | 所属会社 FK |
| full_name | TEXT | 氏名 |
| email | TEXT | メールアドレス |
| role | TEXT | 権限 (admin/agent) |
| created_at | TEXT | 作成日時 |

### properties (物件)

| カラム | 型 | 説明 |
|--------|-----|------|
| id | TEXT | UUID |
| company_id | TEXT | 会社 FK |
| created_by | TEXT | 作成者プロファイル FK |
| address | TEXT | 住所 |
| latitude | REAL | 緯度 (ジオコーディング結果) |
| longitude | REAL | 経度 (ジオコーディング結果) |
| property_name | TEXT | 物件名 (任意) |
| notes | TEXT | メモ (任意) |
| created_at | TEXT | 作成日時 |

### hazard_reports (ハザードレポートキャッシュ)

| カラム | 型 | 説明 |
|--------|-----|------|
| id | TEXT | UUID |
| property_id | TEXT | 物件 FK |
| flood_risk | TEXT | 洪水リスク JSON |
| landslide_risk | TEXT | 土砂災害リスク JSON |
| tsunami_risk | TEXT | 津波リスク JSON |
| ground_risk | TEXT | 地盤リスク JSON |
| risk_summary | TEXT | 統合サマリー JSON |
| fetched_at | TEXT | 取得日時 |
| expires_at | TEXT | キャッシュ有効期限 (90日) |

---

最終更新: 2026-03-06
