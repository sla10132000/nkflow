# Phase 23: 米国個別銘柄 上昇/下落ランキング

## 概要

Yahoo Finance から米国主要個別銘柄の日次 OHLCV を取得し、騰落率ランキング（上昇上位・下落上位）を提供する。既存の日本株ランキング (`daily_summary.top_gainers/top_losers`) と同様の仕組みを米国株にも展開する。

**目的**:
- 米国個別銘柄の日次動向を一覧で把握
- 日本株との連動性（米国テック→日本電気機器 等）を視覚的に確認
- 概要ページに米国株セクションを追加し、日米市場の全体像を一画面で提供

---

## 対象銘柄

### Tier 1: 主要大型株 (約30銘柄)

S&P 500 の時価総額上位 + 日本市場への影響が大きい銘柄を厳選。

| セクター | ティッカー | 企業名 |
|---|---|---|
| テクノロジー | AAPL | Apple |
| テクノロジー | MSFT | Microsoft |
| テクノロジー | GOOGL | Alphabet (Google) |
| テクノロジー | AMZN | Amazon |
| テクノロジー | META | Meta Platforms |
| テクノロジー | NVDA | NVIDIA |
| テクノロジー | TSLA | Tesla |
| テクノロジー | AVGO | Broadcom |
| テクノロジー | AMD | Advanced Micro Devices |
| テクノロジー | CRM | Salesforce |
| 金融 | JPM | JPMorgan Chase |
| 金融 | V | Visa |
| 金融 | MA | Mastercard |
| 金融 | BAC | Bank of America |
| 金融 | GS | Goldman Sachs |
| ヘルスケア | UNH | UnitedHealth Group |
| ヘルスケア | JNJ | Johnson & Johnson |
| ヘルスケア | LLY | Eli Lilly |
| 通信 | NFLX | Netflix |
| 通信 | DIS | Walt Disney |
| 消費財 | KO | Coca-Cola |
| 消費財 | PG | Procter & Gamble |
| 消費財 | WMT | Walmart |
| 消費財 | COST | Costco |
| エネルギー | XOM | Exxon Mobil |
| エネルギー | CVX | Chevron |
| 工業 | CAT | Caterpillar |
| 工業 | BA | Boeing |
| 半導体 | INTC | Intel |
| 半導体 | QCOM | Qualcomm |

> **拡張性**: `config.py` の辞書で管理するため、銘柄の追加・削除はコード変更なしで可能。

---

## アーキテクチャ変更

### 変更ファイル一覧

```
backend/src/
├── config.py                      # ← US_STOCK_TICKERS 定数追加
├── batch/
│   ├── fetch_external.py          # ← fetch_us_stocks() 関数追加
│   └── handler.py                 # ← ステップ 3.7 に米国個別株取得を追加
├── api/
│   └── routers/
│       └── us_indices.py          # ← /api/us-stocks/ranking エンドポイント追加
└── scripts/
    └── init_sqlite.py             # ← us_stocks テーブル定義追加

frontend/src/
├── types/index.ts                 # ← UsStockRanking 型追加
├── composables/useApi.ts          # ← getUsStockRanking() 追加
└── views/OverviewView.vue         # ← 米国株ランキングセクション追加

docs/
├── er_diagram.md                  # ← us_stocks テーブル追記
├── screen_design.md               # ← 概要ページに米国株セクション追記
└── api_reference.md               # ← /api/us-stocks/* エンドポイント追記
```

### データフロー

```
Lambda: nkflow-batch
    │ (ステップ 3.7: 米国個別株取得)
    │
    │ Yahoo Finance REST API
    │   https://query1.finance.yahoo.com/v8/finance/chart/{symbol}
    │   × 30銘柄 (1銘柄ずつ, 0.5秒間隔)
    │   → OHLCV 取得 (差分更新)
    │   → SQLite us_stocks テーブルに INSERT
    │
    └──► S3: data/stocks.db に含めて保存

API Gateway
    │ GET /api/us-stocks/ranking
    ▼
Lambda: nkflow-api
    │ SQLite クエリで騰落率計算
    │ 上昇上位10 + 下落上位10 を返却
    └──► JSON レスポンス
```

---

## 実装仕様

### 1. config.py — 定数追加

```python
US_STOCK_TICKERS = {
    "AAPL": {"name": "Apple", "sector": "テクノロジー"},
    "MSFT": {"name": "Microsoft", "sector": "テクノロジー"},
    "GOOGL": {"name": "Alphabet", "sector": "テクノロジー"},
    "AMZN": {"name": "Amazon", "sector": "テクノロジー"},
    "META": {"name": "Meta Platforms", "sector": "テクノロジー"},
    "NVDA": {"name": "NVIDIA", "sector": "テクノロジー"},
    "TSLA": {"name": "Tesla", "sector": "テクノロジー"},
    "AVGO": {"name": "Broadcom", "sector": "テクノロジー"},
    "AMD": {"name": "AMD", "sector": "テクノロジー"},
    "CRM": {"name": "Salesforce", "sector": "テクノロジー"},
    "JPM": {"name": "JPMorgan Chase", "sector": "金融"},
    "V": {"name": "Visa", "sector": "金融"},
    "MA": {"name": "Mastercard", "sector": "金融"},
    "BAC": {"name": "Bank of America", "sector": "金融"},
    "GS": {"name": "Goldman Sachs", "sector": "金融"},
    "UNH": {"name": "UnitedHealth", "sector": "ヘルスケア"},
    "JNJ": {"name": "J&J", "sector": "ヘルスケア"},
    "LLY": {"name": "Eli Lilly", "sector": "ヘルスケア"},
    "NFLX": {"name": "Netflix", "sector": "通信"},
    "DIS": {"name": "Disney", "sector": "通信"},
    "KO": {"name": "Coca-Cola", "sector": "消費財"},
    "PG": {"name": "P&G", "sector": "消費財"},
    "WMT": {"name": "Walmart", "sector": "消費財"},
    "COST": {"name": "Costco", "sector": "消費財"},
    "XOM": {"name": "Exxon Mobil", "sector": "エネルギー"},
    "CVX": {"name": "Chevron", "sector": "エネルギー"},
    "CAT": {"name": "Caterpillar", "sector": "工業"},
    "BA": {"name": "Boeing", "sector": "工業"},
    "INTC": {"name": "Intel", "sector": "半導体"},
    "QCOM": {"name": "Qualcomm", "sector": "半導体"},
}

US_STOCK_INITIAL_PERIOD = "1y"   # 初回取得: 1年分
US_STOCK_FETCH_INTERVAL = 0.5    # 取得間隔 (秒) — レート制限対策
```

### 2. SQLite テーブル定義

```sql
CREATE TABLE IF NOT EXISTS us_stocks (
    date      TEXT    NOT NULL,  -- YYYY-MM-DD (UTC)
    ticker    TEXT    NOT NULL,  -- AAPL, MSFT, etc.
    name      TEXT    NOT NULL,  -- Apple, Microsoft, etc.
    sector    TEXT,              -- テクノロジー, 金融, etc.
    open      REAL,
    high      REAL,
    low       REAL,
    close     REAL    NOT NULL,
    volume    INTEGER,
    PRIMARY KEY (date, ticker)
);

CREATE INDEX IF NOT EXISTS idx_us_stocks_ticker ON us_stocks(ticker);
CREATE INDEX IF NOT EXISTS idx_us_stocks_date ON us_stocks(date);
```

### 3. fetch_external.py — 取得関数

```python
def fetch_us_stocks(db_path: str) -> dict:
    """
    米国主要個別銘柄の OHLCV を取得し SQLite に保存する。

    - テーブル: us_stocks
    - 差分更新: ティッカーごとに最新日付以降のみ取得
    - 初回: 直近 1 年分を一括取得
    - 既存の _fetch_index_ohlcv() を再利用 (Yahoo Finance REST API)
    - 30銘柄を順次取得 (0.5秒間隔でレート制限対策)
    - エラー時は個別にスキップして他の銘柄は継続
    - 戻り値: {"status": "ok", "rows_inserted": N, "tickers_ok": [...], "tickers_failed": [...]}
    """
```

**実装ポイント**:
- 既存の `_fetch_index_ohlcv()` をそのまま再利用可能（同じ Yahoo Finance REST API）
- `us_indices` とは別テーブル（指数 vs 個別株の分離）
- `time.sleep(US_STOCK_FETCH_INTERVAL)` で Yahoo Finance のレート制限を回避
- 30銘柄 × 0.5秒 = 約15秒で完了（Lambda 900秒に余裕あり）

### 4. handler.py — バッチステップ追加

```python
# ステップ 3.7: 米国個別株取得
logger.info("Step 3.7: Fetching US stocks")
us_stocks_result = fetch_us_stocks(db_path)
logger.info(f"US stocks: {us_stocks_result}")
```

### 5. API エンドポイント — `routers/us_indices.py` に追加

#### `GET /api/us-stocks/ranking`

最新取引日の米国株騰落率ランキングを返す。

**Query Parameters**

| パラメータ | 型 | デフォルト | 説明 |
|---|---|---|---|
| `limit` | int | 10 | 上位/下位それぞれの件数 (1〜30) |

**Response** `200 OK`

```json
{
  "date": "2026-03-04",
  "gainers": [
    {
      "ticker": "NVDA",
      "name": "NVIDIA",
      "sector": "テクノロジー",
      "close": 890.50,
      "change_pct": 5.23
    }
  ],
  "losers": [
    {
      "ticker": "BA",
      "name": "Boeing",
      "sector": "工業",
      "close": 178.30,
      "change_pct": -3.15
    }
  ]
}
```

**SQL ロジック (騰落率計算)**:

```sql
WITH latest AS (
    SELECT MAX(date) AS max_date FROM us_stocks
),
prev AS (
    SELECT MAX(date) AS prev_date FROM us_stocks
    WHERE date < (SELECT max_date FROM latest)
),
ranked AS (
    SELECT
        t.ticker, t.name, t.sector, t.close,
        ROUND((t.close - p.close) / p.close * 100, 2) AS change_pct
    FROM us_stocks t
    JOIN us_stocks p ON p.ticker = t.ticker AND p.date = (SELECT prev_date FROM prev)
    WHERE t.date = (SELECT max_date FROM latest)
)
-- gainers: ORDER BY change_pct DESC LIMIT ?
-- losers:  ORDER BY change_pct ASC  LIMIT ?
```

#### `GET /api/us-stocks/prices/{ticker}`

指定銘柄の時系列データを返す（将来の銘柄詳細ページ用）。

**Query Parameters**

| パラメータ | 型 | デフォルト | 説明 |
|---|---|---|---|
| `days` | int | 90 | 取得日数 (1〜365) |

**Response** `200 OK`

```json
[
  {
    "date": "2026-03-04",
    "open": 880.0,
    "high": 895.0,
    "low": 875.0,
    "close": 890.50,
    "volume": 45000000,
    "change_pct": 5.23
  }
]
```

### 6. フロントエンド — 型定義

```typescript
// types/index.ts
export interface UsStockRankingItem {
  ticker: string;
  name: string;
  sector: string;
  close: number;
  change_pct: number;
}

export interface UsStockRanking {
  date: string;
  gainers: UsStockRankingItem[];
  losers: UsStockRankingItem[];
}
```

### 7. フロントエンド — API composable

```typescript
// useApi.ts
getUsStockRanking: (limit = 10) =>
  api.get("/api/us-stocks/ranking", { params: { limit } }).then((r) => r.data),
```

### 8. フロントエンド — OverviewView 変更

概要ページの既存レイアウトに米国株ランキングセクションを追加。

```
┌─────────────────────────────────────────────────────┐
│  (既存) 日経平均概要カード                             │
│  (既存) 上昇上位 / 下落上位 / 年初来高値圏             │
│  (既存) セクターヒートマップ                           │
│                                                     │
│ ┌──── 米国株ランキング (2026-03-04) ─────────────┐  │
│ │                                                │  │
│ │ ┌──── 上昇上位 ────┐  ┌──── 下落上位 ────┐     │  │
│ │ │ NVDA +5.23%      │  │ BA   -3.15%     │     │  │
│ │ │ TSLA +4.10%      │  │ INTC -2.80%     │     │  │
│ │ │ AMD  +3.55%      │  │ DIS  -1.95%     │     │  │
│ │ │ ...              │  │ ...             │     │  │
│ │ └─────────────────┘  └─────────────────┘     │  │
│ └────────────────────────────────────────────────┘  │
│                                                     │
│  (既存) ニュース / 恐怖指数                           │
└─────────────────────────────────────────────────────┘
```

**表示仕様**:
- 2カラムレイアウト (上昇上位 / 下落上位)
- 各5件表示（デフォルト）
- ティッカー・企業名・セクター・終値・騰落率
- 騰落率は色分け (緑/赤)
- セクターはバッジ表示

---

## テスト

### バックエンド: `tests/test_fetch_us_stocks.py`

```python
def test_fetch_us_stocks_creates_table():
    """空の DB に対して実行し、us_stocks テーブルが作成されること"""

def test_fetch_us_stocks_inserts_data():
    """複数ティッカーのデータが INSERT されること"""

def test_fetch_us_stocks_incremental():
    """既存データがある場合、差分のみ取得すること"""

def test_fetch_us_stocks_handles_individual_error():
    """特定ティッカーの取得失敗時に他は継続すること"""

def test_fetch_us_stocks_rate_limiting():
    """取得間隔が設定値以上であること (time.sleep のモック)"""
```

### バックエンド: `tests/test_router_us_stocks.py`

```python
def test_ranking_returns_gainers_and_losers():
    """ランキング API が上昇/下落上位を返すこと"""

def test_ranking_limit_parameter():
    """limit パラメータで件数制御できること"""

def test_ranking_empty_data():
    """データがない場合に空リストを返すこと"""

def test_prices_returns_timeseries():
    """銘柄別時系列 API が OHLCV を返すこと"""
```

### フロントエンド: `tests/OverviewView.test.ts` 更新

```typescript
it('renders US stock ranking section', async () => {
  // 米国株ランキングセクションが表示されること
})

it('displays gainers and losers with correct colors', async () => {
  // 上昇は緑、下落は赤で表示されること
})
```

---

## 注意事項

### Yahoo Finance レート制限

- 30銘柄を 0.5秒間隔で取得 → 約15秒
- Yahoo Finance の非公式 API は厳密なレート制限が不明
- 429 エラーが頻発する場合は間隔を 1.0秒に引き上げる
- Lambda バッチの総実行時間 (900秒) には十分な余裕あり

### データの鮮度

- バッチ実行は JST 18:00 (UTC 09:00)
- 米国市場クローズは JST 06:00 (EST 16:00)
- → バッチ実行時点で前日の米国市場データが取得可能

### 既存 `us_indices` テーブルとの分離

- `us_indices`: 指数データ (S&P 500, Dow, NASDAQ, VIX) — 既存
- `us_stocks`: 個別銘柄データ (AAPL, MSFT, ...) — **今回新規**
- テーブルを分離することで既存機能への影響を最小化

### 銘柄の追加・削除

- `config.py` の `US_STOCK_TICKERS` を編集するだけで対応可能
- バッチは辞書のキーを順次処理するため、追加銘柄は次回バッチから自動取得
- 削除した銘柄の過去データは DB に残る（自動削除しない）

---

## 実装タスク

### タスク 1: バックエンド — データ取得 & テーブル

1. `config.py` に `US_STOCK_TICKERS`, `US_STOCK_INITIAL_PERIOD`, `US_STOCK_FETCH_INTERVAL` 追加
2. `scripts/init_sqlite.py` に `us_stocks` テーブル定義追加
3. `batch/fetch_external.py` に `fetch_us_stocks()` 実装
4. `batch/handler.py` にステップ 3.7 追加
5. `tests/test_fetch_us_stocks.py` 作成
6. `docs/er_diagram.md` 更新

### タスク 2: バックエンド — API エンドポイント

1. `api/routers/us_indices.py` にランキング & 時系列エンドポイント追加
2. `api/main.py` のルーター登録は既存のまま（同じファイルに追加）
3. `tests/test_router_us_stocks.py` 作成
4. `docs/api_reference.md` 更新

### タスク 3: フロントエンド — 概要ページ表示

1. `types/index.ts` に `UsStockRanking` 型追加
2. `composables/useApi.ts` に `getUsStockRanking()` 追加
3. `views/OverviewView.vue` に米国株ランキングセクション追加
4. `tests/OverviewView.test.ts` 更新
5. `docs/screen_design.md` 更新

### タスク 4: 動作確認 & デプロイ

1. ローカルで Yahoo Finance API の動作確認 (Spike スクリプト)
2. `make test` & `make test-frontend` 全テスト通過
3. `make deploy` (CDK + バッチ Lambda)
4. `make deploy-frontend` (Vue SPA)
5. Playwright で概要ページの表示確認

---

## 実行手順

```bash
# 0. Spike: Yahoo Finance で個別株が取得可能か確認
python -c "
import requests
url = 'https://query1.finance.yahoo.com/v8/finance/chart/AAPL'
params = {'interval': '1d', 'range': '5d'}
headers = {'User-Agent': 'Mozilla/5.0'}
resp = requests.get(url, params=params, headers=headers, timeout=15)
print(resp.status_code, resp.json()['chart']['result'][0]['indicators']['quote'][0]['close'])
"

# 1. バックエンド実装 & テスト
make test

# 2. フロントエンド実装 & テスト
make test-frontend
make lint-frontend

# 3. デプロイ
make deploy
make deploy-frontend
```
