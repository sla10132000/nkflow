# HazardBrief — Claude Code 指示書

防災×不動産 SaaS。住所を入力すると複数の公的ハザードデータを統合した防災レポートを自動生成する不動産会社向け営業支援ツール。

---

## 技術スタック

- **Frontend**: Vue 3 (Composition API + `<script setup>`) + Vite + TypeScript + Tailwind CSS + Auth0
- **Backend**: FastAPI + Mangum (AWS Lambda)
- **DB**: SQLite (S3 保存、nkflow と同じパターン)
- **Auth**: Auth0
- **Infra**: AWS CDK (Lambda + API Gateway + S3)
- **地図**: Leaflet (vue-leaflet / @vue-leaflet/vue-leaflet)

---

## ディレクトリ構成

```
hazardbrief/
├── CLAUDE.md
├── feature_plan/HazardBrief.md
├── docs/
│   ├── er_diagram.md
│   ├── api_reference.md
│   ├── screen_design.md
│   └── test_design.md
├── backend/
│   ├── pyproject.toml
│   ├── src/
│   │   ├── config.py
│   │   └── api/
│   │       ├── main.py
│   │       ├── handler.py
│   │       ├── storage.py
│   │       └── routers/
│   │           ├── properties.py
│   │           ├── hazard.py
│   │           ├── report.py
│   │           └── companies.py
│   ├── lib/
│   │   └── hazard/
│   │       ├── __init__.py
│   │       ├── geocoding.py
│   │       ├── flood.py
│   │       ├── landslide.py
│   │       ├── tsunami.py
│   │       └── ground.py
│   ├── scripts/
│   │   └── init_sqlite.py
│   └── tests/
│       ├── conftest.py
│       ├── test_properties.py
│       └── test_hazard.py
├── frontend/
│   ├── package.json
│   ├── vite.config.ts
│   ├── tsconfig.json
│   ├── tailwind.config.js
│   ├── biome.json
│   ├── index.html
│   └── src/
│       ├── main.ts
│       ├── App.vue
│       ├── router/index.ts
│       ├── stores/useAuthStore.ts
│       ├── composables/
│       │   ├── useApi.ts
│       │   └── useAuth.ts
│       ├── types/
│       │   ├── hazard.ts
│       │   ├── property.ts
│       │   └── report.ts
│       ├── views/
│       │   ├── LoginView.vue
│       │   ├── DashboardView.vue
│       │   ├── PropertyNewView.vue
│       │   ├── PropertyDetailView.vue
│       │   └── SettingsView.vue
│       ├── components/
│       │   ├── layout/
│       │   │   ├── AppHeader.vue
│       │   │   └── Sidebar.vue
│       │   ├── map/
│       │   │   └── HazardMap.vue
│       │   ├── report/
│       │   │   ├── RiskSummaryCard.vue
│       │   │   └── HazardDetail.vue
│       │   └── shared/
│       │       └── LoadingSpinner.vue
│       └── utils/
│           └── formatters.ts
└── cdk/
    ├── package.json
    ├── cdk.json
    ├── tsconfig.json
    ├── bin/hazardbrief.ts
    └── lib/hazardbrief-stack.ts
```

---

## コマンド

### Backend

```bash
cd hazardbrief/backend
uv pip install -e ".[dev]"
.venv/bin/python -m pytest tests/ -v
.venv/bin/ruff check src/ tests/
```

### Frontend

```bash
cd hazardbrief/frontend
npm install
npm run dev
npm run build
npm run lint
npx vitest run
```

### CDK

```bash
cd hazardbrief/cdk
npm ci
npx cdk deploy HazardBriefStack --require-approval never
```

---

## UIの原則 (HazardBrief.md から)

1. リスクを「危険/安全」の二項対立で見せない
2. 「リスクの説明」と「対策の可能性」をセットで表示
3. カラー: 赤を避け、オレンジ〜黄色系でリスクレベルを表現
4. 外部API取得失敗はフォールバック表示（graceful degradation）
5. 免責事項を必ずUIに表示

---

## コーディング規約

- TypeScript strict mode
- Vue 3 Composition API + `<script setup>`
- Python: FastAPI + async/await
- エラーハンドリング: try-catch / HTTPException
- 環境変数は config.py に集約

---

## 外部 API (無料)

| API | 用途 | URL |
|---|---|---|
| 国土地理院ジオコーダー | 住所→緯度経度 | https://msearch.gsi.go.jp/address-search/AddressSearch |
| 国交省 不動産情報ライブラリ | 洪水・土砂 GeoJSON | https://www.reinfolib.mlit.go.jp/ex-api/external/ |
| 国土地理院 標高API | 地盤情報 | https://cyberjapandata2.gsi.go.jp/general/dem/scripts/getelevation.php |

---

## 免責事項 (必須)

```
本レポートは公的機関が公表するデータを基に作成しています。
ハザードマップは想定最大規模の災害を示すものであり、
実際の被害程度は地形・建物構造・気象条件等により異なります。
物件の安全性判断は、現地確認・専門家への相談と合わせてご活用ください。
データ出典: 国土交通省ハザードマップポータルサイト
```
