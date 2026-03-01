# nkflow — 日経225 投資分析基盤 設計書 (AWS版)

> **このドキュメントはClaude Code CLIで段階的に実装するための設計書です。**
> Phase順に上から実装してください。

---

## 1. プロジェクト概要

日経平均225構成銘柄の日次騰落率・値幅データを収集し、グラフDB（KùzuDB）で銘柄間の関係性・資金フローの方向性・予測シグナルを分析する個人向け投資分析基盤。

### 設計方針

- **AWS無料枠 + 従量課金最小化**（目標: 月額 $0-2）
- **バッチ処理主体**（日次1回、東証クローズ後に実行）
- **Lambda コンテナで全計算をローカルI/O完結**
- **永続化はS3（SQLite + KùzuDB スナップショット）**
- **UIはVue3 SPA (Vite) 静的ホスティング（S3 + CloudFront）**
- **IaCはAWS CDK（TypeScript）**

---

## 2. アーキテクチャ全体図

```
                      [EventBridge Scheduler]
                              │
                        毎営業日 18:00 JST
                              │
                              ▼
┌───────────────────────────────────────────────────────┐
│              Lambda (コンテナイメージ)                   │
│              メモリ: 2048MB / タイムアウト: 900s          │
│                                                       │
│  1. S3 → /tmp/ に SQLite + KùzuDB ダウンロード          │
│                                                       │
│  2. J-Quants API → 当日 OHLCV 取得                     │
│                                                       │
│  3. DuckDB (インメモリ)                                 │
│     ATTACH SQLite → 計算 → SQLite に書き戻し            │
│                                                       │
│  4. Python 統計計算                                     │
│     グレンジャー因果 / リードラグ / 資金フロー推定        │
│                                                       │
│  5. KùzuDB グラフ構築・探索                              │
│     DuckDB → LOAD FROM → ノード/エッジ更新              │
│     Cypher クエリで因果連鎖・クラスター探索              │
│     結果 → SQLite signals テーブルに書き戻し             │
│                                                       │
│  6. /tmp/ の SQLite + KùzuDB → S3 にアップロード        │
└───────────────────────────────────────────────────────┘


┌───────────────────────────────────────────────────────┐
│             API Lambda (コンテナ or zip)                │
│             Lambda Function URL                        │
│                                                       │
│  起動時: S3 → /tmp/ に SQLite ダウンロード              │
│  (初回コールドスタート時のみ。以降はキャッシュ)           │
│                                                       │
│  FastAPI (Mangum アダプタ)                              │
│    GET /api/summary          日次サマリ                 │
│    GET /api/prices/:code     時系列データ                │
│    GET /api/signals          シグナル一覧               │
│    GET /api/network/:type    ネットワークデータ          │
│    GET /api/stock/:code      銘柄詳細                   │
└───────────────────────────────────────────────────────┘


┌───────────────────────────────────────────────────────┐
│           S3 + CloudFront (静的ホスティング)             │
│                                                       │
│  Vue3 SPA (Vite + vue-router)                         │
│    ├─ / (Overview)        日次サマリ                    │
│    ├─ /timeseries         時系列チャート                 │
│    ├─ /network            ネットワーク可視化             │
│    ├─ /signals            予測シグナル一覧               │
│    └─ /stock/:code        銘柄詳細                      │
│                                                       │
│  → API Lambda を fetch で呼び出し                       │
└───────────────────────────────────────────────────────┘


┌───────────────────────────────────────────────────────┐
│                    S3 Bucket                           │
│              s3://nkflow-data-{account}/                │
│                                                       │
│  data/                                                │
│    ├─ stocks.db              ← SQLite 本体             │
│    └─ kuzu_db.tar.gz         ← KùzuDB スナップショット  │
│                                                       │
│  frontend/                                             │
│    └─ (Vite ビルド成果物 dist/)   ← CloudFront Origin   │
└───────────────────────────────────────────────────────┘
```

---

## 3. ディレクトリ構成

```
nkflow/
├── README.md
├── .gitignore
│
├── cdk/                          # AWS CDK (IaC)
│   ├── package.json
│   ├── tsconfig.json
│   ├── cdk.json
│   ├── bin/
│   │   └── nkflow.ts             # CDKエントリポイント
│   └── lib/
│       └── nkflow-stack.ts       # スタック定義
│
├── backend/                      # Python バックエンド
│   ├── pyproject.toml            # uv
│   ├── Dockerfile.batch          # バッチLambda用
│   ├── Dockerfile.api            # API Lambda用
│   ├── src/
│   │   ├── __init__.py
│   │   ├── config.py             # 環境変数・定数管理
│   │   ├── batch/
│   │   │   ├── __init__.py
│   │   │   ├── handler.py        # Lambda ハンドラ (エントリポイント)
│   │   │   ├── fetch.py          # J-Quants API データ取得
│   │   │   ├── compute.py        # DuckDB 計算
│   │   │   ├── statistics.py     # グレンジャー因果・リードラグ
│   │   │   ├── graph.py          # KùzuDB グラフ構築・探索
│   │   │   ├── signals.py        # 予測シグナル生成
│   │   │   └── storage.py        # S3 ダウンロード/アップロード
│   │   └── api/
│   │       ├── __init__.py
│   │       ├── handler.py        # Lambda ハンドラ (Mangum)
│   │       ├── main.py           # FastAPI アプリ定義
│   │       ├── routers/
│   │       │   ├── summary.py    # GET /api/summary
│   │       │   ├── prices.py     # GET /api/prices/:code
│   │       │   ├── signals.py    # GET /api/signals
│   │       │   ├── network.py    # GET /api/network/:type
│   │       │   └── stock.py      # GET /api/stock/:code
│   │       └── storage.py        # S3からSQLiteロード (キャッシュ付き)
│   ├── tests/
│   │   ├── test_fetch.py
│   │   ├── test_compute.py
│   │   ├── test_statistics.py
│   │   ├── test_graph.py
│   │   └── fixtures/
│   │       └── sample_prices.csv
│   └── scripts/
│       ├── init_sqlite.py        # SQLite 初期スキーマ
│       ├── init_kuzu.py          # KùzuDB スキーマ
│       └── backfill.py           # 過去データバックフィル
│
└── frontend/                     # Vue3 SPA (Vite)
    ├── package.json
    ├── vite.config.ts
    ├── tsconfig.json
    ├── index.html                # Vite エントリ
    ├── src/
    │   ├── App.vue
    │   ├── main.ts               # createApp + router
    │   ├── router/
    │   │   └── index.ts          # vue-router 定義
    │   ├── views/
    │   │   ├── OverviewView.vue   # /
    │   │   ├── TimeseriesView.vue # /timeseries
    │   │   ├── NetworkView.vue    # /network
    │   │   ├── SignalsView.vue    # /signals
    │   │   └── StockView.vue      # /stock/:code
    │   ├── components/
    │   │   ├── charts/
    │   │   │   ├── PriceChart.vue    # 株価チャート (Chart.js)
    │   │   │   ├── HeatMap.vue       # セクターヒートマップ
    │   │   │   └── ReturnDist.vue    # 騰落率分布
    │   │   └── network/
    │   │       └── GraphView.vue     # ネットワーク可視化 (vis-network)
    │   ├── composables/
    │   │   └── useApi.ts             # API呼び出しフック
    │   └── types/
    │       └── index.ts              # TypeScript 型定義
    └── public/
        └── favicon.ico
```

---

## 4. 技術スタック

| カテゴリ | 技術 | 用途 |
|---|---|---|
| **IaC** | AWS CDK (TypeScript) | 全AWSリソース定義 |
| **バッチ** | Lambda コンテナ (Python 3.12) | 日次データ処理 |
| **API** | Lambda コンテナ + Function URL | REST API |
| **API FW** | FastAPI + Mangum | Lambda上でASGI |
| **スケジュール** | EventBridge Scheduler | 日次トリガー |
| **ストレージ** | S3 | SQLite / KùzuDB / フロントエンド |
| **CDN** | CloudFront | SPA配信 |
| **シークレット** | SSM Parameter Store (SecureString) | J-Quantsクレデンシャル |
| **計算** | DuckDB | OLAP計算エンジン |
| **時系列DB** | SQLite | OHLCV・分析結果 |
| **グラフDB** | KùzuDB | 銘柄間関係性グラフ |
| **統計** | statsmodels, scipy | グレンジャー因果・クロス相関 |
| **グラフ分析** | networkx | コミュニティ検出 |
| **フロントエンド** | Vue3 + Vite + vue-router | SPA |
| **チャート** | Chart.js (vue-chartjs) | 時系列・分布チャート |
| **ネットワーク可視化** | vis-network | グラフ描画 |

---

## 5. SQLite スキーマ

`backend/scripts/init_sqlite.py` で作成する。

```sql
-- === マスタ ===
CREATE TABLE IF NOT EXISTS stocks (
    code        TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    sector      TEXT NOT NULL
);

-- === 日次価格データ ===
CREATE TABLE IF NOT EXISTS daily_prices (
    code        TEXT NOT NULL REFERENCES stocks(code),
    date        TEXT NOT NULL,
    open        REAL,
    high        REAL,
    low         REAL,
    close       REAL,
    volume      INTEGER,
    return_rate REAL,
    price_range REAL,
    range_pct   REAL,
    relative_strength REAL,
    PRIMARY KEY (code, date)
);

CREATE INDEX IF NOT EXISTS idx_dp_date ON daily_prices(date);
CREATE INDEX IF NOT EXISTS idx_dp_code_date ON daily_prices(code, date DESC);

-- === グラフ分析結果 (KùzuDB から書き戻し) ===

CREATE TABLE IF NOT EXISTS graph_causality (
    source      TEXT NOT NULL,
    target      TEXT NOT NULL,
    lag_days    INTEGER NOT NULL,
    p_value     REAL NOT NULL,
    f_stat      REAL NOT NULL,
    period      TEXT NOT NULL,
    calc_date   TEXT NOT NULL,
    PRIMARY KEY (source, target, period, calc_date)
);

CREATE TABLE IF NOT EXISTS graph_correlations (
    stock_a     TEXT NOT NULL,
    stock_b     TEXT NOT NULL,
    coefficient REAL NOT NULL,
    period      TEXT NOT NULL,
    calc_date   TEXT NOT NULL,
    PRIMARY KEY (stock_a, stock_b, period, calc_date)
);

CREATE TABLE IF NOT EXISTS graph_fund_flows (
    sector_from    TEXT NOT NULL,
    sector_to      TEXT NOT NULL,
    volume_delta   REAL,
    return_spread  REAL,
    date           TEXT NOT NULL,
    PRIMARY KEY (sector_from, sector_to, date)
);

CREATE TABLE IF NOT EXISTS graph_communities (
    code           TEXT NOT NULL,
    community_id   INTEGER NOT NULL,
    calc_date      TEXT NOT NULL,
    PRIMARY KEY (code, calc_date)
);

-- === 予測シグナル ===
CREATE TABLE IF NOT EXISTS signals (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    date           TEXT NOT NULL,
    signal_type    TEXT NOT NULL,
    code           TEXT,
    sector         TEXT,
    direction      TEXT NOT NULL,
    confidence     REAL NOT NULL,
    reasoning      TEXT NOT NULL,
    created_at     TEXT DEFAULT (datetime('now'))
);

-- signal_type:
--   'causality_chain'   因果連鎖による追随予測
--   'fund_flow'         セクター間資金フロー
--   'regime_shift'      マーケットレジーム変化
--   'lead_lag'          リードラグ関係
--   'cluster_breakout'  クラスター内乖離

CREATE INDEX IF NOT EXISTS idx_signals_date ON signals(date DESC);
CREATE INDEX IF NOT EXISTS idx_signals_code ON signals(code, date DESC);

-- === 日次サマリ ===
CREATE TABLE IF NOT EXISTS daily_summary (
    date            TEXT PRIMARY KEY,
    nikkei_close    REAL,
    nikkei_return   REAL,
    regime          TEXT,
    top_gainers     TEXT,
    top_losers      TEXT,
    active_signals  INTEGER,
    sector_rotation TEXT
);
```

---

## 6. KùzuDB グラフスキーマ

`backend/scripts/init_kuzu.py` で作成する。

```python
import kuzu, os

def init_kuzu(db_path: str = "/tmp/kuzu_db"):
    os.makedirs(db_path, exist_ok=True)
    db = kuzu.Database(db_path)
    conn = kuzu.Connection(db)

    # ノード
    conn.execute("""
        CREATE NODE TABLE IF NOT EXISTS Stock(
            code STRING, name STRING, sector STRING,
            market_cap_tier STRING, community_id INT64,
            PRIMARY KEY(code)
        )
    """)
    conn.execute("""
        CREATE NODE TABLE IF NOT EXISTS Sector(
            name STRING, PRIMARY KEY(name)
        )
    """)
    conn.execute("""
        CREATE NODE TABLE IF NOT EXISTS TradingDay(
            date DATE, nikkei_close DOUBLE,
            nikkei_return DOUBLE, regime STRING,
            PRIMARY KEY(date)
        )
    """)

    # エッジ
    conn.execute("CREATE REL TABLE IF NOT EXISTS BELONGS_TO(FROM Stock TO Sector)")
    conn.execute("""
        CREATE REL TABLE IF NOT EXISTS CORRELATED(
            FROM Stock TO Stock,
            coefficient DOUBLE, period STRING, calc_date DATE
        )
    """)
    conn.execute("""
        CREATE REL TABLE IF NOT EXISTS GRANGER_CAUSES(
            FROM Stock TO Stock,
            lag_days INT64, p_value DOUBLE, f_stat DOUBLE,
            period STRING, calc_date DATE
        )
    """)
    conn.execute("""
        CREATE REL TABLE IF NOT EXISTS LEADS(
            FROM Stock TO Stock,
            lag_days INT64, cross_corr DOUBLE,
            period STRING, calc_date DATE
        )
    """)
    conn.execute("""
        CREATE REL TABLE IF NOT EXISTS FUND_FLOW(
            FROM Sector TO Sector,
            direction STRING, volume_delta DOUBLE,
            return_spread DOUBLE, date DATE
        )
    """)
    conn.execute("""
        CREATE REL TABLE IF NOT EXISTS TRADED_ON(
            FROM Stock TO TradingDay,
            return_rate DOUBLE, price_range DOUBLE,
            volume INT64, relative_strength DOUBLE
        )
    """)

    conn.close()
    return db
```

---

## 7. 各モジュール実装仕様

### 7.1 `backend/src/config.py`

```python
"""環境変数と定数"""
import os

# AWS
S3_BUCKET = os.environ["S3_BUCKET"]
S3_SQLITE_KEY = "data/stocks.db"
S3_KUZU_KEY = "data/kuzu_db.tar.gz"

# J-Quants (SSM Parameter Store から取得)
# Lambda起動時にSSMから読み込む
JQUANTS_EMAIL = os.environ.get("JQUANTS_EMAIL", "")
JQUANTS_PASSWORD = os.environ.get("JQUANTS_PASSWORD", "")

# ローカルパス (Lambda の /tmp)
SQLITE_PATH = "/tmp/stocks.db"
KUZU_PATH = "/tmp/kuzu_db"

# 分析パラメータ
CORRELATION_PERIODS = [20, 60, 120]
GRANGER_MAX_LAG = 5
GRANGER_P_THRESHOLD = 0.05
CORRELATION_THRESHOLD = 0.5
COMMUNITY_RESOLUTION = 1.0
```

---

### 7.2 `backend/src/batch/storage.py` — S3 永続化

```
機能:
  Lambda の /tmp (最大10GB) を作業領域として使用。
  S3 との間でファイルをやり取りする。

  download():
    1. boto3 で S3 から /tmp/stocks.db をダウンロード
       初回は存在しないので ClientError をキャッチし、
       init_sqlite.py でスキーマ初期化
    2. S3 から /tmp/kuzu_db.tar.gz をダウンロード → /tmp/kuzu_db に展開
       初回は新規作成

  upload():
    1. /tmp/stocks.db を S3 にアップロード
    2. /tmp/kuzu_db を tar.gz に圧縮して S3 にアップロード

  SSMからクレデンシャル取得:
    boto3 SSM client で以下を取得
    - /nkflow/jquants-email
    - /nkflow/jquants-password

実装の注意:
  - Lambda /tmp は最大 10GB (エフェメラルストレージ設定)
  - コールドスタート時は毎回ダウンロードが必要
  - SQLite は WAL モードで使用 (wal ファイルも考慮)
  - アップロード前に VACUUM を実行してファイルサイズを最小化
```

---

### 7.3 `backend/src/batch/handler.py` — Lambda ハンドラ

```python
"""
バッチ Lambda のエントリポイント。
EventBridge Scheduler から呼び出される。

実行順序:
  1. storage.get_credentials()   - SSMからJ-Quantsクレデンシャル取得
  2. storage.download()          - S3から復元
  3. fetch.fetch_daily()         - J-Quantsからデータ取得
  4. compute.compute_all()       - DuckDB計算
  5. statistics.run_all()        - 統計分析
  6. graph.update_and_query()    - グラフ更新・探索
  7. signals.generate()          - シグナル生成
  8. storage.upload()            - S3へ永続化

エラーハンドリング:
  - 各ステップを try/except で囲む
  - 失敗しても upload() は finally で必ず実行
  - 取引日でない場合は fetch で早期リターン
  - CloudWatch Logs に自動出力

Lambda レスポンス:
  {
    "statusCode": 200,
    "body": {
      "date": "2025-05-01",
      "stocks_updated": 225,
      "signals_generated": 12,
      "errors": []
    }
  }
"""

def handler(event, context):
    ...
```

---

### 7.4 `backend/src/batch/fetch.py` — データ取得

```
機能:
  - J-Quants APIから日経225全銘柄の当日OHLCVを取得
  - SQLite daily_prices テーブルにINSERT OR REPLACE
  - stocksマスタが未登録なら listed_info から自動登録

注意事項:
  - jquants-api-client ライブラリを使用
  - 取引日でない場合は早期リターン (Falseを返す)
  - Lambda は外部HTTP通信可能 (VPC外で実行)

参考: https://github.com/J-Quants/jquants-api-client-python
```

---

### 7.5 `backend/src/batch/compute.py` — DuckDB計算

```
機能:
  DuckDBからSQLiteをATTACHし、以下を計算:
    1. 騰落率 (return_rate)
    2. 値幅 (price_range)
    3. 値幅率 (range_pct)
    4. 対日経225相対強度 (relative_strength)
    5. ローリング相関行列 (20日/60日/120日)
    6. セクター別平均騰落率・出来高集計

実装:
  - DuckDB の ATTACH '/tmp/stocks.db' AS sq (TYPE SQLITE)
  - 相関行列は pandas .corr() を使用
  - stock_a < stock_b に正規化
  - |coefficient| < CORRELATION_THRESHOLD は保存しない
```

---

### 7.6 `backend/src/batch/statistics.py` — 統計分析

```
機能:
  1. グレンジャー因果検定
     - 全銘柄ペア (225C2 = 25,200通り) に双方向テスト
     - statsmodels.tsa.stattools.grangercausalitytests
     - p_value < GRANGER_P_THRESHOLD のみ保存
     - 直近60営業日のデータで計算

  2. リードラグ分析 (クロス相関)
     - lag -5 ~ +5 のクロス相関
     - |cross_corr| > 0.3 かつ lag ≠ 0 を保存

  3. 資金フロー推定 (セクターレベル)
     - 出来高変化率 + 騰落率で inflow/outflow 判定

  4. マーケットレジーム判定
     - 日経225の直近20日ボラティリティとリターンで分類

パフォーマンス注意:
  - 25,200ペアのグレンジャー検定は重い
  - joblib で並列化を検討
  - Lambda 2048MB / 900s で収まるか検証が必要
  - 収まらない場合: ペア数を削減 (同セクターのみ等)
    またはLambda メモリを3008MBに上げる
```

---

### 7.7 `backend/src/batch/graph.py` — KùzuDB グラフ構築・探索

```
機能:
  1. グラフ更新
     - statistics.py の結果を KùzuDB エッジとして投入
     - DuckDB LOAD FROM を活用
     - 古いエッジを削除

  2. グラフ探索 (Cypher) → 結果をSQLiteに書き戻し

     a. 因果連鎖:
        MATCH path = (leader:Stock)-[:GRANGER_CAUSES*1..3]->(follower:Stock)
        WHERE ALL(r IN rels(path) WHERE r.p_value < 0.05)

     b. セクター間資金フロー経路:
        MATCH path = (src:Sector)-[:FUND_FLOW*1..3]->(dst:Sector)

     c. 相関クラスター:
        CORRELATED エッジ → networkx louvain_communities()

     d. レジーム別パフォーマンス集計
```

---

### 7.8 `backend/src/batch/signals.py` — 予測シグナル生成

```
機能:
  graph.py の結果から actionable なシグナルを生成。

  1. causality_chain: 当日大幅変動銘柄から因果連鎖を辿り追随予測
  2. fund_flow: セクター間資金フローから流入先銘柄をシグナル
  3. regime_shift: レジーム変化時に過去アウトパフォーム銘柄を提示
  4. cluster_breakout: クラスター内乖離から平均回帰を期待

  結果を signals テーブル + daily_summary テーブルに保存。
```

---

### 7.9 `backend/src/api/` — API Lambda

```
FastAPI + Mangum で Lambda 上に REST API を構築。

handler.py:
  from mangum import Mangum
  from src.api.main import app
  handler = Mangum(app)

main.py:
  FastAPI アプリ定義。起動時に S3 から SQLite を /tmp にダウンロード。
  Lambda のウォームスタート中は /tmp のキャッシュを再利用。

エンドポイント:

  GET /api/summary
    - daily_summary テーブルから直近N日分を返す
    - レスポンス: { date, nikkei_close, nikkei_return, regime,
                    top_gainers, top_losers, active_signals }

  GET /api/prices/{code}?from=YYYY-MM-DD&to=YYYY-MM-DD
    - daily_prices テーブルから時系列データを返す
    - レスポンス: [{ date, open, high, low, close, volume,
                     return_rate, price_range }]

  GET /api/signals?date=YYYY-MM-DD&type=causality_chain&direction=bullish
    - signals テーブルからフィルタして返す
    - レスポンス: [{ id, date, signal_type, code, direction,
                     confidence, reasoning }]

  GET /api/network/{type}?period=20d&threshold=0.7
    - type: "correlation" | "causality" | "fund_flow"
    - graph_correlations / graph_causality / graph_fund_flows から取得
    - レスポンス: { nodes: [...], edges: [...] }
      vis-network が直接描画できるフォーマット

  GET /api/stock/{code}
    - 銘柄詳細: 直近データ + 因果連鎖 + 相関銘柄 + 所属クラスター
    - 複数テーブルを JOIN して返す

CORS:
  - CloudFront のドメインを許可
  - 開発時は localhost:3000 も許可

SQLite キャッシュ戦略 (storage.py):
  - /tmp にファイルが存在し、更新時刻が1時間以内ならキャッシュ使用
  - それ以外は S3 から再ダウンロード
  - 読み取り専用で開く (mode=ro)
```

---

## 8. フロントエンド仕様

### 8.1 Vite + Vue3 設定

```typescript
// vite.config.ts
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:8000',  // ローカル開発時
        changeOrigin: true,
      }
    }
  }
})
```

```typescript
// src/main.ts
import { createApp } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'
import App from './App.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/',           component: () => import('./views/OverviewView.vue') },
    { path: '/timeseries', component: () => import('./views/TimeseriesView.vue') },
    { path: '/network',    component: () => import('./views/NetworkView.vue') },
    { path: '/signals',    component: () => import('./views/SignalsView.vue') },
    { path: '/stock/:code', component: () => import('./views/StockView.vue'), props: true },
  ]
})

createApp(App).use(router).mount('#app')
```

### 8.2 API呼び出し

```typescript
// src/composables/useApi.ts
import axios from 'axios'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE || '',
  timeout: 10000,
})

export const useApi = () => ({
  getSummary: (days?: number) =>
    api.get('/api/summary', { params: days ? { days } : undefined }).then(r => r.data),
  getPrices: (code: string, from?: string, to?: string) =>
    api.get(`/api/prices/${code}`, { params: { from, to } }).then(r => r.data),
  getSignals: (params?: Record<string, string>) =>
    api.get('/api/signals', { params }).then(r => r.data),
  getNetwork: (type: string, period?: string, threshold?: string) =>
    api.get(`/api/network/${type}`, { params: { period, threshold } }).then(r => r.data),
  getStock: (code: string) =>
    api.get(`/api/stock/${code}`).then(r => r.data),
})
```

### 8.3 型定義

```typescript
// src/types/index.ts
export interface Stock {
  code: string
  name: string
  sector: string
}

export interface DailyPrice {
  code: string
  date: string
  open: number
  high: number
  low: number
  close: number
  volume: number
  return_rate: number
  price_range: number
}

export interface Signal {
  id: number
  date: string
  signal_type: string
  code: string | null
  sector: string | null
  direction: 'bullish' | 'bearish'
  confidence: number
  reasoning: Record<string, unknown>
}

export interface NetworkData {
  nodes: { id: string; label: string; group: string; size: number }[]
  edges: { from: string; to: string; value: number; arrows?: string }[]
}

export interface DailySummary {
  date: string
  nikkei_close: number
  nikkei_return: number
  regime: string
  top_gainers: Stock & { return_rate: number }[]
  top_losers: Stock & { return_rate: number }[]
  active_signals: number
}
```
```

### 8.4 ページ仕様

```
views/OverviewView.vue (/)
  - 当日のレジーム表示 (risk_on/risk_off/neutral)
  - 日経225騰落率
  - 騰落率上位/下位5銘柄
  - アクティブシグナル数 → クリックで /signals へ
  - セクター騰落率ヒートマップ

views/TimeseriesView.vue (/timeseries)
  - 銘柄セレクタ (検索可能ドロップダウン)
  - Chart.js で OHLC + 出来高チャート
  - 騰落率・値幅の時系列
  - 期間選択 (1M / 3M / 6M / 1Y)

views/NetworkView.vue (/network)
  - 表示モード切替: 相関 / 因果 / 資金フロー
  - 期間選択: 20d / 60d / 120d
  - 閾値スライダー
  - vis-network でインタラクティブグラフ描画
  - ノード色: セクター別
  - エッジ太さ: 相関係数 or f_stat
  - 因果エッジは矢印付き
  - ノードクリック → サイドパネルに詳細

views/SignalsView.vue (/signals)
  - フィルタ: 日付 / シグナルタイプ / 方向 / confidence
  - テーブル一覧表示
  - reasoning の JSON を展開表示

views/StockView.vue (/stock/:code)
  - 銘柄基本情報 (名前, セクター)
  - 直近騰落率チャート
  - 因果連鎖 (この銘柄から/この銘柄への)
  - 相関が高い銘柄リスト
  - 所属クラスターの他銘柄
  - 関連シグナル
```

---

## 9. AWS CDK スタック定義

```typescript
// cdk/lib/nkflow-stack.ts
//
// 以下のリソースを定義する:
//
// 1. S3 Bucket
//    - バケット名: nkflow-data-{account}
//    - ライフサイクル: なし (データは永続)
//    - 静的ホスティング有効 (dist/ を S3 にアップロード)
//
// 2. Lambda (バッチ)
//    - ランタイム: コンテナイメージ (ECR)
//    - メモリ: 2048MB
//    - タイムアウト: 900s (15分 = Lambda最大)
//    - エフェメラルストレージ: 2048MB (/tmp 拡張)
//    - 環境変数: S3_BUCKET
//    - IAMポリシー: S3 読み書き, SSM パラメータ読み取り
//
// 3. Lambda (API)
//    - ランタイム: コンテナイメージ (ECR)
//    - メモリ: 512MB
//    - タイムアウト: 30s
//    - Function URL 有効 (AuthType: NONE → CloudFront経由で制御)
//    - 環境変数: S3_BUCKET
//    - IAMポリシー: S3 読み取り
//
// 4. EventBridge Scheduler
//    - スケジュール: cron(0 9 ? * MON-FRI *)  ← UTC 09:00 = JST 18:00
//    - ターゲット: バッチ Lambda
//
// 5. CloudFront Distribution
//    - オリジン1: S3 (frontend/) → デフォルトビヘイビア
//    - オリジン2: API Lambda Function URL → /api/* ビヘイビア
//    - デフォルトルートオブジェクト: index.html
//    - カスタムエラーレスポンス: 403,404 → /index.html (SPA対応)
//
// 6. SSM Parameter Store
//    - /nkflow/jquants-email (SecureString)
//    - /nkflow/jquants-password (SecureString)
//    ※ 値は手動で設定 (CDKでは枠だけ作る or cdk.json のcontext)
//
// 7. ECR Repository
//    - nkflow-batch
//    - nkflow-api
```

---

## 10. Dockerfile

### 10.1 `backend/Dockerfile.batch`

```dockerfile
FROM public.ecr.aws/lambda/python:3.12

# システム依存
RUN dnf install -y tar gzip && dnf clean all

WORKDIR ${LAMBDA_TASK_ROOT}

# Python 依存
COPY pyproject.toml .
RUN pip install uv && uv pip install --system -r pyproject.toml

# ソースコード
COPY src/ src/
COPY scripts/ scripts/

# Lambda ハンドラ
CMD ["src.batch.handler.handler"]
```

### 10.2 `backend/Dockerfile.api`

```dockerfile
FROM public.ecr.aws/lambda/python:3.12

WORKDIR ${LAMBDA_TASK_ROOT}

COPY pyproject.toml .
RUN pip install uv && uv pip install --system -r pyproject.toml

COPY src/ src/

CMD ["src.api.handler.handler"]
```

---

## 11. pyproject.toml

```toml
[project]
name = "nkflow"
version = "0.1.0"
requires-python = ">=3.12"

dependencies = [
    # データ取得
    "jquants-api-client",
    # 計算
    "duckdb>=1.1",
    "pandas>=2.2",
    "numpy>=1.26",
    # グラフDB
    "kuzu>=0.7",
    # 統計
    "statsmodels>=0.14",
    "scipy>=1.13",
    # グラフ分析
    "networkx>=3.3",
    # API
    "fastapi>=0.115",
    "mangum>=0.19",
    # AWS
    "boto3>=1.34",
    # ユーティリティ
    "joblib>=1.4",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-cov",
    "moto[s3,ssm]",    # AWS モック
    "httpx",            # FastAPI テスト
    "ruff",
]
```

---

## 12. Lambda /tmp の容量設計

```
Lambda /tmp 制限: 最大 10,240MB (設定で拡張)
本プロジェクトの設定: 2,048MB

容量試算:
  stocks.db       : ~100MB (225銘柄 × 10年分でも余裕)
  kuzu_db.tar.gz  : ~50MB  (展開後 ~150MB)
  DuckDB ワーク   : ~200MB (インメモリだが一部spillあり)
  合計            : ~500MB → 2GB で十分

制約:
  - /tmp はコールドスタートごとにクリアされる
  - 必ず S3 からのダウンロードが必要
  - stocks.db (100MB) の S3 転送: ~2-3秒
```

---

## 13. コスト試算

| リソース | 無料枠 | 本プロジェクト使用量 | 月額 |
|---|---|---|---|
| Lambda (バッチ) | 100万リクエスト + 40万GB秒 | 22回/月 × 15分 × 2GB = 660GB秒 | $0 |
| Lambda (API) | 同上 | ~1000リクエスト/月 × 0.5GB × 1秒 | $0 |
| S3 ストレージ | 5GB (12ヶ月) | ~200MB | $0 |
| S3 リクエスト | 20,000 GET / 2,000 PUT | ~2,000 | $0 |
| CloudFront | 1TB転送/月 | ~1GB | $0 |
| EventBridge | 無料 | 22回/月 | $0 |
| SSM Parameter | 標準パラメータ無料 | 2個 | $0 |
| ECR | 500MB無料 | ~500MB | $0 |
| **合計** | | | **$0** |

※ 無料枠は12ヶ月限定のものあり。12ヶ月後もLambda/EventBridge/SSMは永久無料。
  S3/CloudFront/ECRは微額の従量課金 (~$0.5-2/月) になる。

---

## 14. Phase 0: GCP→AWS 事前準備チェックリスト

> **Claude Code に入る前に、以下を手動で完了させること。**

```
□ AWS アカウント作成 (まだなら)
□ IAM ユーザー作成 (AdministratorAccess、CLIアクセス用)
□ AWS CLI インストール & aws configure
□ Node.js インストール (CDK用、v18+)
□ AWS CDK CLI インストール: npm install -g aws-cdk
□ CDK ブートストラップ: cdk bootstrap aws://{ACCOUNT_ID}/ap-northeast-1
□ J-Quants API アカウント登録
□ SSM Parameter Store に手動登録:
    aws ssm put-parameter --name /nkflow/jquants-email \
      --type SecureString --value "your@email.com"
    aws ssm put-parameter --name /nkflow/jquants-password \
      --type SecureString --value "your_password"
□ Docker Desktop インストール (Lambda コンテナビルド用)
```

---

## 15. 実装順序 (Claude Code CLI への指示順)

### Phase 1: プロジェクト初期化 + CDK

```
指示: この設計書 (nkflow-spec.md) に基づいて、プロジェクトの初期構造を作成してください。

1. ディレクトリ構成を設計書通りに作成
2. backend/pyproject.toml を作成
3. backend/src/config.py を作成
4. backend/scripts/init_sqlite.py を作成 (設計書のスキーマ)
5. backend/scripts/init_kuzu.py を作成 (設計書のスキーマ)
6. cdk/ ディレクトリを `cdk init app --language typescript` で初期化
7. cdk/lib/nkflow-stack.ts を設計書のリソース定義に従って実装
   - S3 バケット
   - Lambda (バッチ) + EventBridge Scheduler
   - Lambda (API) + Function URL
   - CloudFront Distribution (S3 + API Lambda)
   - ECR リポジトリ x2
   - IAM ロール/ポリシー
8. 全ファイルに適切な __init__.py を配置
```

### Phase 2: データ取得 + S3永続化

```
指示: backend/src/batch/fetch.py と backend/src/batch/storage.py を実装してください。

storage.py:
  - boto3 で S3 からの SQLite/KùzuDB ダウンロード
  - S3 へのアップロード (VACUUM後)
  - SSM Parameter Store からクレデンシャル取得

fetch.py:
  - J-Quants APIで日経225全銘柄のOHLCV取得
  - stocks マスタ自動登録
  - daily_prices へ INSERT OR REPLACE
  - 取引日判定

テスト: tests/test_fetch.py (moto でS3/SSMモック)
```

### Phase 3: DuckDB計算

```
指示: backend/src/batch/compute.py を実装してください。

- DuckDB で SQLite を ATTACH
- 騰落率・値幅・値幅率・相対強度の計算
- ローリング相関行列 (20d/60d/120d)
- 結果をSQLiteに書き戻し

テスト: tests/test_compute.py (fixtures/sample_prices.csv使用)
```

### Phase 4: 統計分析

```
指示: backend/src/batch/statistics.py を実装してください。

- グレンジャー因果検定 (全ペア双方向、並列化)
- リードラグ分析 (クロス相関)
- セクター資金フロー推定
- マーケットレジーム判定
- Lambda 15分制限を意識したパフォーマンス最適化

テスト: tests/test_statistics.py
```

### Phase 5: グラフ構築・探索

```
指示: backend/src/batch/graph.py を実装してください。

- KùzuDB にノード/エッジ投入 (DuckDB LOAD FROM)
- 因果連鎖 Cypher クエリ
- セクター間資金フロー経路 Cypher クエリ
- networkx コミュニティ検出
- レジーム別パフォーマンス集計
- 結果を SQLite に書き戻し

テスト: tests/test_graph.py
```

### Phase 6: シグナル生成 + バッチ統合

```
指示: backend/src/batch/signals.py と backend/src/batch/handler.py を実装してください。

signals.py:
  - 4種のシグナル生成ロジック
  - signals + daily_summary テーブル更新

handler.py:
  - Lambda ハンドラ (全ステップ統合)
  - エラーハンドリング (finally で upload)
  - CloudWatch Logs 出力

テスト: tests/test_signals.py
```

### Phase 7: API Lambda

```
指示: backend/src/api/ 以下を全て実装してください。

- FastAPI + Mangum でLambda上REST API
- 5つのエンドポイント (summary, prices, signals, network, stock)
- S3 → SQLite キャッシュ戦略
- CORS 設定
- vis-network 互換の nodes/edges フォーマット

テスト: httpx + moto でAPIテスト
```

### Phase 8: フロントエンド

```
指示: frontend/ 以下を全て実装してください。

- npm create vite@latest で Vue3 + TypeScript プロジェクト初期化
- vite.config.ts (開発時プロキシ設定)
- vue-router でルーティング
- src/composables/useApi.ts
- src/types/index.ts
- 5ページ (views/):
    OverviewView, TimeseriesView, NetworkView, SignalsView, StockView
- Chart.js でチャート (vue-chartjs)
- vis-network でネットワーク可視化
- Tailwind CSS でスタイリング
- レスポンシブ対応
- 環境変数: VITE_API_BASE (本番はCloudFrontのAPI Lambda Function URL)

package.json の dependencies:
  vue, vue-router, axios, vue-chartjs, chart.js, vis-network, vis-data

devDependencies:
  vite, @vitejs/plugin-vue, tailwindcss, postcss, autoprefixer, typescript
```

### Phase 9: Docker + デプロイ

```
指示: Dockerfile.batch, Dockerfile.api を実装し、デプロイ可能な状態にしてください。

1. backend/Dockerfile.batch (設計書仕様)
2. backend/Dockerfile.api (設計書仕様)
3. frontend の vite build でビルド (dist/ に出力)
4. CDK でデプロイ手順を README.md に記載:
   - docker build でイメージビルド
   - ECR にプッシュ
   - cdk deploy
   - S3 にフロントエンドアップロード
   - CloudFront キャッシュ無効化
```

### Phase 10: テスト + バックフィル

```
指示: backend/scripts/backfill.py を実装し、全テストを通してください。

backfill.py:
  - J-Quantsから取得可能な過去データを一括取得
  - 全計算パイプラインを過去データに対して実行
  - 進捗表示付き
  - ローカル実行用 (Lambda外で直接実行)

テスト:
  - 全テストがパスすることを確認
  - pytest --cov でカバレッジ確認
```

---

## 16. Phase 10 完了後のロードマップ

| Phase | 内容 | 優先度 |
|---|---|---|
| **11** | シグナル的中率の自動追跡・レポート | 最優先 |
| **12** | LINE Notify / Slack 通知 (Lambda → SNS → Lambda) | 高 |
| **13** | 信用残・為替データの追加 | 中 |
| **14** | バックテストエンジン | 中 |
| **15** | ポートフォリオ連携 | 低 |

---

## 17. 進捗トラッカー

> **Claude Code CLI への指示:**
> 各 Phase の作業が完了したら、このセクションの該当チェックボックスを
> `- [ ]` → `- [x]` に更新し、完了日時をメモしてください。
>
> ```
> 例: Phase 1 完了時の指示
> 「Phase 1 が完了しました。nkflow-spec.md の進捗トラッカーの Phase 1 にチェックを入れ、完了日を記入してください。」
> ```

### Phase 0: 事前準備 (手動)

- [ ] AWS アカウント作成
- [ ] IAM ユーザー作成 + AWS CLI 設定
- [ ] Node.js + CDK CLI インストール
- [ ] CDK ブートストラップ実行
- [ ] J-Quants API アカウント登録
- [ ] SSM Parameter Store にクレデンシャル登録
- [ ] Docker Desktop インストール

### Phase 1〜10: 実装

- [x] **Phase 1** : プロジェクト初期化 + CDK — 完了日: 2026-03-01
- [x] **Phase 2** : データ取得 + S3永続化 — 完了日: 2026-03-01
- [x] **Phase 3** : DuckDB計算 — 完了日: 2026-03-01
- [x] **Phase 4** : 統計分析 — 完了日: 2026-03-01
- [x] **Phase 5** : グラフ構築・探索 — 完了日: 2026-03-01
- [x] **Phase 6** : シグナル生成 + バッチ統合 — 完了日: 2026-03-01
- [x] **Phase 7** : API Lambda — 完了日: 2026-03-01
- [x] **Phase 8** : フロントエンド — 完了日: 2026-03-01
- [x] **Phase 9** : Docker + デプロイ — 完了日: 2026-03-01
- [x] **Phase 10**: テスト + バックフィル — 完了日: 2026-03-01

### Phase 11〜15: 拡張 (Phase 10 完了後)

- [ ] **Phase 11**: シグナル的中率の自動追跡 — 完了日:
- [ ] **Phase 12**: LINE / Slack 通知 — 完了日:
- [ ] **Phase 13**: 信用残・為替データ追加 — 完了日:
- [x] **Phase 14**: バックテストエンジン — 完了日: 2026-03-01
- [ ] **Phase 15**: ポートフォリオ連携 — 完了日:

### 現在のステータス

```
最終更新: 2026-03-01
進行中Phase: -
ブロッカー: なし
備考:
  - Phase 1〜10 全て完了 (master)
  - Phase 14 完了 (feature/phase-14-backtest)
  - CDK の CloudFront Distribution は TODO (AWSアカウント有効化待ち)
  - テスト: 121件全通過
  - Phase 0 (AWS環境準備) は手動作業のため未チェック
  - Phase 14: backtest_runs/backtest_trades/backtest_results テーブル追加、
              backtest.py 新規 (simulate_trades/calc_metrics/run_backtest)、
              scripts/run_backtest.py CLI 新規、
              GET /api/backtest, /api/backtest/{run_id}, /api/backtest/{run_id}/trades 追加
```
