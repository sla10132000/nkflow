# 防災×不動産 SaaS フェーズ1 実装プラン

## プロジェクト概要

**プロダクト名（仮）**: HazardBrief（ハザードブリーフ）  
**コンセプト**: 不動産会社が防災情報を「商談の武器」にするための営業支援SaaS  
**フェーズ1ゴール**: 中小不動産会社 10〜20社でのPMF検証。住所入力→防災レポート自動生成のコア機能をリリースする。

---

## フェーズ1 スコープ

### IN SCOPE
- 住所入力による物件防災レポートの自動生成
- ハザードマップデータ（洪水・土砂・津波・高潮）の統合表示
- 地盤リスク情報の取得・表示
- エージェント向けPDF出力
- 物件の保存・一覧管理
- ユーザー認証（不動産会社アカウント）

### OUT OF SCOPE（フェーズ2以降）
- 保険料概算の自動取得
- 対策コスト試算
- 物件横断リスク比較
- 顧客向けポータル
- 提携業者へのリード送客

---

## 技術スタック

```
Frontend:  Next.js 14 (App Router) + TypeScript + Tailwind CSS
Backend:   Next.js API Routes (初期はモノレポ構成)
DB:        PostgreSQL (Supabase)
Auth:      Supabase Auth
PDF生成:   Puppeteer or React-PDF
地図:      Mapbox GL JS or Leaflet
Hosting:   Vercel
```

### 外部データソース（無償API）
- **国土交通省 ハザードマップポータル API**: 洪水・土砂・高潮・津波
- **国土交通省 不動産情報ライブラリ API**: 地価・用途地域
- **地理院タイル (国土地理院)**: 地形・標高データ
- **法務省 登記情報**: 任意（フェーズ2以降）

---

## ディレクトリ構成

```
hazard-brief/
├── CLAUDE.md                  # Claude Code用プロジェクト指示書
├── README.md
├── .env.local                 # 環境変数（gitignore）
├── .env.example
├── package.json
├── tsconfig.json
├── next.config.ts
│
├── app/                       # Next.js App Router
│   ├── layout.tsx
│   ├── page.tsx               # LP / ログイン導線
│   ├── (auth)/
│   │   ├── login/page.tsx
│   │   └── signup/page.tsx
│   └── (dashboard)/
│       ├── layout.tsx         # 認証済みレイアウト
│       ├── dashboard/page.tsx # 物件一覧
│       ├── properties/
│       │   ├── new/page.tsx   # 物件登録（住所入力）
│       │   └── [id]/
│       │       ├── page.tsx   # レポート表示
│       │       └── report/    # PDF出力
│       └── settings/page.tsx
│
├── components/
│   ├── ui/                    # 汎用UIコンポーネント
│   ├── map/                   # 地図コンポーネント
│   ├── report/                # レポート関連コンポーネント
│   └── layout/
│
├── lib/
│   ├── supabase/              # Supabase client
│   ├── hazard/                # ハザードデータ取得ロジック
│   │   ├── flood.ts           # 洪水リスク取得
│   │   ├── landslide.ts       # 土砂災害リスク取得
│   │   ├── tsunami.ts         # 津波リスク取得
│   │   ├── ground.ts          # 地盤リスク取得
│   │   └── index.ts           # 統合インターフェース
│   ├── geocoding.ts           # 住所→緯度経度変換
│   └── pdf/                   # PDF生成ロジック
│
├── types/
│   ├── hazard.ts
│   ├── property.ts
│   └── report.ts
│
└── supabase/
    └── migrations/            # DBマイグレーション
```

---

## CLAUDE.md（プロジェクト指示書）

> このファイルをプロジェクトルートに配置する。Claude Codeがコンテキストとして読み込む。

```markdown
# HazardBrief - Claude Code 指示書

## プロジェクト概要
不動産会社向け防災情報レポート自動生成SaaS。
住所を入力すると、複数の公的ハザードデータを統合した防災レポートを生成し、
PDF出力まで行う。

## 技術スタック
- Next.js 14 (App Router), TypeScript, Tailwind CSS
- Supabase (PostgreSQL + Auth)
- 外部API: 国土交通省ハザードAPI, 国土地理院API

## コーディング規約
- TypeScriptのstrict modeを使用
- コンポーネントはServer Componentsを優先し、インタラクティブな部分のみClient Components
- APIルートはapp/api/以下に配置
- エラーハンドリングは必ずtry-catchで行い、ユーザーフレンドリーなメッセージを返す
- 環境変数は.env.localを使用し、.env.exampleにキーのみ記載

## データモデルの原則
- 外部APIのレスポンスはキャッシュしてDBに保存（API制限対策）
- ハザードデータの取得失敗はフォールバック表示（取得不可と明示）

## UIの原則
- リスクを「危険/安全」の二項対立で見せない
- 必ず「リスクの説明」と「対策の可能性」をセットで表示
- カラー: 赤を避け、オレンジ〜黄色系でリスクレベルを表現
```

---

## データモデル（Supabase）

```sql
-- 会社（テナント）
create table companies (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  plan text default 'free',  -- free | standard | enterprise
  created_at timestamptz default now()
);

-- ユーザー（エージェント）
create table profiles (
  id uuid primary key references auth.users,
  company_id uuid references companies(id),
  full_name text,
  role text default 'agent',  -- admin | agent
  created_at timestamptz default now()
);

-- 物件
create table properties (
  id uuid primary key default gen_random_uuid(),
  company_id uuid references companies(id),
  created_by uuid references profiles(id),
  address text not null,
  latitude float8,
  longitude float8,
  property_name text,
  notes text,
  created_at timestamptz default now()
);

-- ハザードレポート（取得結果キャッシュ）
create table hazard_reports (
  id uuid primary key default gen_random_uuid(),
  property_id uuid references properties(id),
  flood_risk jsonb,       -- 洪水リスクデータ
  landslide_risk jsonb,   -- 土砂災害リスクデータ
  tsunami_risk jsonb,     -- 津波リスクデータ
  ground_risk jsonb,      -- 地盤リスクデータ
  risk_summary jsonb,     -- 統合サマリー
  fetched_at timestamptz default now(),
  expires_at timestamptz  -- キャッシュ有効期限（90日）
);
```

---

## 実装タスク一覧

### MILESTONE 0: セットアップ（1〜2日）

```
[ ] Next.js + TypeScript プロジェクト作成
[ ] Supabase プロジェクト作成・環境変数設定
[ ] Tailwind CSS セットアップ
[ ] DBマイグレーション実行
[ ] Supabase Auth 設定（メール認証）
[ ] Vercel デプロイ設定
[ ] CLAUDE.md 配置
```

### MILESTONE 1: 認証・基本UI（3〜4日）

```
[ ] ログイン画面 (app/(auth)/login)
[ ] サインアップ画面 (app/(auth)/signup)
[ ] 認証済みルートのミドルウェア設定
[ ] ダッシュボード骨格 (app/(dashboard)/layout.tsx)
[ ] 物件一覧画面 - 空の状態から実装 (dashboard/page.tsx)
[ ] サイドバーナビゲーション
```

### MILESTONE 2: ジオコーディング + 地図（3〜4日）

```
[ ] 住所→緯度経度変換 (lib/geocoding.ts)
    - 国土地理院ジオコーダーAPI or Google Maps Geocoding API
[ ] 物件登録フォーム (properties/new/page.tsx)
    - 住所入力 + オートコンプリート
    - 地図プレビュー（Mapbox or Leaflet）
[ ] 物件登録API (app/api/properties/route.ts)
[ ] 登録後のリダイレクト処理
```

### MILESTONE 3: ハザードデータ取得（5〜7日）

```
[ ] 国交省APIクライアント実装 (lib/hazard/)
    [ ] flood.ts - 洪水浸水想定区域
        - エンドポイント: 国土数値情報 洪水浸水想定区域API
        - 緯度経度からポリゴンデータを取得
        - 浸水深レベル（0.5m未満〜20m以上）を返す
    [ ] landslide.ts - 土砂災害警戒区域
        - 特別警戒区域（レッドゾーン）/ 警戒区域（イエローゾーン）
    [ ] tsunami.ts - 津波浸水想定
    [ ] ground.ts - 地盤情報
        - 国土地理院 土地条件図API
        - 液状化リスク

[ ] ハザードデータ取得API (app/api/hazard/[propertyId]/route.ts)
    - 非同期並列取得（Promise.allSettled）
    - 取得失敗は graceful degradation（部分的に表示）
    - 結果をhazard_reportsテーブルにキャッシュ

[ ] データ取得中のローディングUI
[ ] エラー時のフォールバックUI
```

### MILESTONE 4: レポート表示画面（4〜5日）

```
[ ] レポート画面 (properties/[id]/page.tsx)
[ ] リスクサマリーカード
    - 各リスク項目をスコアではなくレベル（低/中/高/要確認）で表示
    - 「なぜこのレベルか」の根拠テキスト
    - 「このレベルでできる対策」のヒント
[ ] ハザードマップ表示コンポーネント
    - 物件を中心に洪水・土砂etc.のリスクエリアをオーバーレイ
    - レイヤー切り替えUI
[ ] 地形・標高情報の表示
[ ] データソース・更新日時の明示（透明性確保）
```

### MILESTONE 5: PDF出力（3〜4日）

```
[ ] PDFレイアウト設計 (components/report/)
    - 表紙: 物件名・住所・作成日・会社名
    - ページ1: リスクサマリー
    - ページ2: 洪水リスク詳細 + 地図スクリーンショット
    - ページ3: 土砂・津波・地盤リスク
    - 最終ページ: データソース・免責事項

[ ] PDF生成API (app/api/report/[propertyId]/pdf/route.ts)
    - React-PDF or Puppeteer で実装
    - 会社ロゴ・担当者名をヘッダーに入れる

[ ] PDFダウンロードボタン
[ ] 印刷プレビュー
```

### MILESTONE 6: 磨き込み・ベータリリース（3〜5日）

```
[ ] レスポンシブ対応（タブレット重視）
[ ] 物件一覧の検索・フィルター
[ ] 物件削除・アーカイブ
[ ] メモ機能（エージェントが商談メモを残せる）
[ ] 利用規約・免責事項ページ
[ ] オンボーディングフロー（初回ログイン後のガイド）
[ ] エラーモニタリング (Sentry)
[ ] アクセス解析 (Vercel Analytics)
```

---

## 外部API 詳細

### 国土交通省 不動産情報ライブラリ API
```
ベースURL: https://www.reinfolib.mlit.go.jp/ex-api/external/
認証: APIキー（無料取得可）
用途: 洪水浸水想定区域, 土砂災害警戒区域

エンドポイント例:
GET /XIT001?response_format=geojson&datum=wgs84
    &lat={緯度}&lon={経度}&zoom=15
```

### 国土地理院 標高API
```
ベースURL: https://cyberjapandata2.gsi.go.jp/general/dem/scripts/getelevation.php
認証: 不要
用途: 任意の緯度経度の標高取得

GET ?lon={経度}&lat={緯度}&outtype=JSON
```

### 国土地理院 地形分類データ（タイル）
```
ベースURL: https://cyberjapandata.gsi.go.jp/xyz/
用途: 土地条件図・地形分類（平野部/台地/山地など）
形式: ベクトルタイル or ラスタータイル
```

---

## 免責事項の設計（重要）

Zillowの失敗から学び、以下を必ずUIに組み込む。

```
表示すべきテキスト:
「本レポートは公的機関が公表するデータを基に作成しています。
ハザードマップは想定最大規模の災害を示すものであり、
実際の被害程度は地形・建物構造・気象条件等により異なります。
物件の安全性判断は、現地確認・専門家への相談と合わせてご活用ください。
データ出典: 国土交通省ハザードマップポータルサイト（更新日: YYYY/MM/DD）」
```

---

## PMF検証指標

フェーズ1終了時に以下を計測する。

| 指標 | 目標値 |
|------|--------|
| 導入社数 | 10〜20社 |
| 月間レポート生成数/社 | 20件以上 |
| 継続率（3ヶ月） | 70%以上 |
| NPS（エージェントへのヒアリング） | +30以上 |
| 「防災説明が楽になった」回答率 | 80%以上 |

---

## 開発開始手順

```bash
# 1. プロジェクト作成
npx create-next-app@latest hazard-brief --typescript --tailwind --app --src-dir

# 2. 依存パッケージ追加
cd hazard-brief
npm install @supabase/supabase-js @supabase/ssr
npm install leaflet react-leaflet @types/leaflet
npm install @react-pdf/renderer
npm install lucide-react
npm install date-fns

# 3. Supabase CLI
npm install -D supabase
npx supabase init
npx supabase start  # ローカル開発環境起動

# 4. Claude Code 起動
claude
```

---

## 参考リソース

- [国土交通省 不動産情報ライブラリ API仕様](https://www.reinfolib.mlit.go.jp/help/apiManual/)
- [ハザードマップポータルサイト](https://disaportal.gsi.go.jp/)
- [国土地理院 地理院タイル](https://maps.gsi.go.jp/development/ichiran.html)
- [Supabase ドキュメント](https://supabase.com/docs)
- [Next.js App Router ドキュメント](https://nextjs.org/docs/app)
