# Phase 23b: 米国セクター別パフォーマンス (Sector ETF)

## 概要

SPDR セクター ETF (XLK, XLF, XLE 等) の日次 OHLCV を取得し、米国市場のセクター別パフォーマンスを可視化する。Phase 23 (米国個別銘柄ランキング) の補完機能として、セクターレベルでの資金動向を把握する。

**目的**:
- 米国市場のセクター間の強弱を一覧で把握
- 日本株セクターローテーション (Phase 17) との連動性を視覚的に確認
- 概要ページの米国株セクションに組み込み、日米セクター比較を一画面で提供

---

## 対象 ETF

### Select Sector SPDR ETFs (11本)

S&P 500 を構成する 11 セクターに対応する SPDR ETF。

| ティッカー | セクター名 | 日本語名 | 対応する日本株セクター例 |
|---|---|---|---|
| XLK | Technology | テクノロジー | 電気機器, 情報通信 |
| XLF | Financials | 金融 | 銀行業, 証券 |
| XLV | Health Care | ヘルスケア | 医薬品 |
| XLE | Energy | エネルギー | 石油・石炭, 鉱業 |
| XLI | Industrials | 資本財 | 機械, 輸送用機器 |
| XLY | Consumer Discretionary | 一般消費財 | 小売業 |
| XLP | Consumer Staples | 生活必需品 | 食料品, 化学 |
| XLU | Utilities | 公益 | 電気・ガス |
| XLB | Materials | 素材 | 鉄鋼, 非鉄金属, 化学 |
| XLRE | Real Estate | 不動産 | 不動産業 |
| XLC | Communication Services | 通信 | 情報通信 |

> **拡張性**: `config.py` の辞書で管理するため、ETF の追加・削除はコード変更なしで可能。

---

## アーキテクチャ

### 既存 `us_indices` テーブルへの統合

セクター ETF は指数と同じ OHLCV 構造のため、**既存の `us_indices` テーブルに統合する**。新テーブルは作成しない。

理由:
- `us_indices` テーブルのスキーマ (date, ticker, name, OHLCV) がそのまま使える
- `_fetch_index_ohlcv()` をそのまま再利用できる
- API エンドポイントも既存の `/api/us-indices` に統合可能
- フロントエンドの表示で指数とセクター ETF を同じデータソースから取得できる

### 変更ファイル一覧

```
backend/src/
├── config.py                      # ← US_SECTOR_ETF_TICKERS 定数追加
├── batch/
│   └── fetch_external.py          # ← fetch_us_indices() にセクター ETF を追加
└── api/
    └── routers/
        └── us_indices.py          # ← /api/us-sectors/performance エンドポイント追加

frontend/src/
├── types/index.ts                 # ← UsSectorPerformance 型追加
├── composables/useApi.ts          # ← getUsSectorPerformance() 追加
└── views/OverviewView.vue         # ← 米国セクターパフォーマンスセクション追加

docs/
├── er_diagram.md                  # ← 変更なし (us_indices テーブル流用)
├── screen_design.md               # ← 概要ページに米国セクターセクション追記
└── api_reference.md               # ← /api/us-sectors/* エンドポイント追記
```

### データフロー

```
Lambda: nkflow-batch
    │ (ステップ 3.5 に統合: 既存 fetch_us_indices を拡張)
    │
    │ Yahoo Finance REST API
    │   https://query1.finance.yahoo.com/v8/finance/chart/{symbol}
    │   × 11 ETF (既存指数 4 本 + セクターETF 11 本 = 計 15 本)
    │   → OHLCV 取得 (差分更新)
    │   → SQLite us_indices テーブルに INSERT
    │
    └──► S3: data/stocks.db に含めて保存

API Gateway
    │ GET /api/us-sectors/performance
    ▼
Lambda: nkflow-api
    │ SQLite クエリで騰落率計算
    │ 11 セクター ETF の当日パフォーマンス + 週次/月次推移
    └──► JSON レスポンス
```

---

## 実装仕様

### 1. config.py — 定数追加

```python
US_SECTOR_ETF_TICKERS: dict[str, dict[str, str]] = {
    "XLK":  {"name": "Technology Select Sector SPDR",           "sector": "テクノロジー"},
    "XLF":  {"name": "Financial Select Sector SPDR",            "sector": "金融"},
    "XLV":  {"name": "Health Care Select Sector SPDR",          "sector": "ヘルスケア"},
    "XLE":  {"name": "Energy Select Sector SPDR",               "sector": "エネルギー"},
    "XLI":  {"name": "Industrial Select Sector SPDR",           "sector": "資本財"},
    "XLY":  {"name": "Consumer Discretionary Select Sector SPDR", "sector": "一般消費財"},
    "XLP":  {"name": "Consumer Staples Select Sector SPDR",     "sector": "生活必需品"},
    "XLU":  {"name": "Utilities Select Sector SPDR",            "sector": "公益"},
    "XLB":  {"name": "Materials Select Sector SPDR",            "sector": "素材"},
    "XLRE": {"name": "Real Estate Select Sector SPDR",          "sector": "不動産"},
    "XLC":  {"name": "Communication Services Select Sector SPDR", "sector": "通信"},
}
```

### 2. SQLite テーブル — 変更なし

既存の `us_indices` テーブルをそのまま使用。セクター ETF も `(date, ticker)` の複合主キーで管理される。

```sql
-- 既存テーブル (変更不要)
CREATE TABLE IF NOT EXISTS us_indices (
    date      TEXT    NOT NULL,
    ticker    TEXT    NOT NULL,
    name      TEXT    NOT NULL,
    open      REAL,
    high      REAL,
    low       REAL,
    close     REAL    NOT NULL,
    volume    INTEGER,
    PRIMARY KEY (date, ticker)
);
```

### 3. fetch_external.py — fetch_us_indices() 拡張

既存の `fetch_us_indices()` を拡張し、セクター ETF も取得対象に含める。

```python
def fetch_us_indices(db_path: str) -> dict:
    """
    米国指数 + セクター ETF の OHLCV を取得し SQLite に保存する。

    変更点:
    - combined_tickers に US_SECTOR_ETF_TICKERS を追加
    - セクター ETF は name を US_SECTOR_ETF_TICKERS[ticker]["name"] から取得
    """
    combined_tickers: dict[str, str] = {
        **US_INDEX_TICKERS,
        **FEAR_INDEX_TICKERS,
        # 新規追加: セクター ETF
        **{k: v["name"] for k, v in US_SECTOR_ETF_TICKERS.items()},
    }
    # 以降のロジックは既存のまま (差分更新 + INSERT OR REPLACE)
```

**実装ポイント**:
- 既存の `_fetch_index_ohlcv()` をそのまま再利用
- 15 本 (指数 4 + セクター ETF 11) を順次取得
- 15 本 × 0.5 秒間隔 = 約 7.5 秒で完了
- `US_INDEX_INITIAL_PERIOD = "10y"` を共用 (セクター ETF も 10 年分)

### 4. API エンドポイント — `routers/us_indices.py` に追加

#### `GET /api/us-sectors/performance`

セクター ETF の当日パフォーマンス (騰落率 + 週次/月次変化率) を返す。

**Query Parameters**

| パラメータ | 型 | デフォルト | 説明 |
|---|---|---|---|
| `period` | string | `1d` | `1d` / `1w` / `1m` / `3m` |

**Response** `200 OK`

```json
{
  "date": "2026-03-04",
  "period": "1d",
  "sectors": [
    {
      "ticker": "XLK",
      "name": "Technology Select Sector SPDR",
      "sector": "テクノロジー",
      "close": 220.50,
      "change_pct": 1.85,
      "volume": 12500000
    },
    {
      "ticker": "XLE",
      "name": "Energy Select Sector SPDR",
      "sector": "エネルギー",
      "close": 88.20,
      "change_pct": -0.95,
      "volume": 8200000
    }
  ]
}
```

**SQL ロジック (期間別騰落率)**:

```sql
-- period=1d の場合
WITH latest AS (
    SELECT MAX(date) AS max_date FROM us_indices
    WHERE ticker IN ('XLK','XLF','XLV','XLE','XLI','XLY','XLP','XLU','XLB','XLRE','XLC')
),
base AS (
    -- 1d: 前営業日, 1w: 5営業日前, 1m: 約21営業日前, 3m: 約63営業日前
    SELECT ticker, close AS base_close
    FROM us_indices
    WHERE date = (
        SELECT MAX(date) FROM us_indices
        WHERE date < (SELECT max_date FROM latest)
          AND ticker IN ('XLK','XLF','XLV','XLE','XLI','XLY','XLP','XLU','XLB','XLRE','XLC')
    )
)
SELECT
    t.ticker, t.name, t.close, t.volume,
    ROUND((t.close - b.base_close) / b.base_close * 100, 2) AS change_pct
FROM us_indices t
JOIN base b ON b.ticker = t.ticker
WHERE t.date = (SELECT max_date FROM latest)
ORDER BY change_pct DESC
```

#### `GET /api/us-sectors/heatmap`

セクター ETF の週次/月次パフォーマンスをヒートマップ用に返す。
既存の日本株 `/api/sector-rotation/heatmap` と同様の構造。

**Query Parameters**

| パラメータ | 型 | デフォルト | 説明 |
|---|---|---|---|
| `periods` | int | 12 | 取得する期間数 |
| `period_type` | string | `weekly` | `weekly` / `monthly` |

**Response** `200 OK`

```json
{
  "periods": ["2026-W08", "2026-W09", "2026-W10"],
  "sectors": [
    {
      "ticker": "XLK",
      "sector": "テクノロジー",
      "values": [1.2, -0.5, 2.3]
    },
    {
      "ticker": "XLE",
      "sector": "エネルギー",
      "values": [-1.0, 0.8, -0.3]
    }
  ]
}
```

### 5. フロントエンド — 型定義

```typescript
// types/index.ts
export interface UsSectorPerformanceItem {
  ticker: string;
  name: string;
  sector: string;
  close: number;
  change_pct: number;
  volume: number;
}

export interface UsSectorPerformance {
  date: string;
  period: string;
  sectors: UsSectorPerformanceItem[];
}

export interface UsSectorHeatmapSector {
  ticker: string;
  sector: string;
  values: number[];
}

export interface UsSectorHeatmap {
  periods: string[];
  sectors: UsSectorHeatmapSector[];
}
```

### 6. フロントエンド — API composable

```typescript
// useApi.ts
getUsSectorPerformance: (period = '1d') =>
  api.get("/api/us-sectors/performance", { params: { period } }).then((r) => r.data),

getUsSectorHeatmap: (periods = 12, periodType = 'weekly') =>
  api.get("/api/us-sectors/heatmap", { params: { periods, period_type: periodType } }).then((r) => r.data),
```

### 7. フロントエンド — OverviewView 変更

概要ページに米国セクターパフォーマンスセクションを追加。Phase 23 の米国株ランキングと並べて配置。

```
┌─────────────────────────────────────────────────────┐
│  (既存) 日経平均概要カード                             │
│  (既存) 上昇上位 / 下落上位 / 年初来高値圏             │
│  (既存) セクターヒートマップ                           │
│                                                     │
│ ┌──── 米国セクター (2026-03-04) ───────────────────┐ │
│ │  期間: [1D] [1W] [1M] [3M]                       │ │
│ │                                                  │ │
│ │ ┌──────────────────────────────────────────────┐ │ │
│ │ │  XLK テクノロジー   ██████████████  +1.85%   │ │ │
│ │ │  XLI 資本財         ████████████    +1.20%   │ │ │
│ │ │  XLF 金融           ██████████      +0.85%   │ │ │
│ │ │  XLP 生活必需品      ████████       +0.45%   │ │ │
│ │ │  XLU 公益            ██████         +0.20%   │ │ │
│ │ │  XLRE 不動産         ████           +0.10%   │ │ │
│ │ │  XLC 通信            ██            -0.15%    │ │ │
│ │ │  XLB 素材            ██            -0.30%    │ │ │
│ │ │  XLV ヘルスケア                    -0.55%    │ │ │
│ │ │  XLY 一般消費財                    -0.70%    │ │ │
│ │ │  XLE エネルギー                    -0.95%    │ │ │
│ │ └──────────────────────────────────────────────┘ │ │
│ └──────────────────────────────────────────────────┘ │
│                                                     │
│  (Phase 23) 米国株ランキング (上昇上位 / 下落上位)    │
│  (既存) ニュース / 恐怖指数                           │
└─────────────────────────────────────────────────────┘
```

**表示仕様**:
- 騰落率順にソートされた横棒グラフ (水平バーチャート)
- 正の値は緑系、負の値は赤系のバー
- セクター名 (日本語) + ティッカーを左端に表示
- 騰落率の数値を右端に表示
- 期間切替ボタン (1D / 1W / 1M / 3M)
- 棒の長さは最大変化率に対する相対値

**実装**: CSS のみで描画 (Chart.js 不要)。各バーは `div` + `width: ${Math.abs(pct) / maxPct * 100}%` で制御。

---

## テスト

### バックエンド: `tests/test_fetch_us_sector_etf.py`

```python
def test_fetch_us_indices_includes_sector_etfs():
    """fetch_us_indices() がセクター ETF も取得すること"""

def test_sector_etf_data_in_us_indices_table():
    """セクター ETF データが us_indices テーブルに保存されること"""

def test_sector_etf_incremental_update():
    """既存データがある場合、差分のみ取得すること"""
```

### バックエンド: `tests/test_router_us_sectors.py`

```python
def test_performance_returns_all_sectors():
    """パフォーマンス API が全 11 セクターを返すこと"""

def test_performance_period_parameter():
    """period パラメータで期間切替できること"""

def test_performance_sorts_by_change_pct():
    """騰落率降順でソートされること"""

def test_heatmap_returns_weekly_data():
    """週次ヒートマップが正しい形式で返ること"""

def test_performance_empty_data():
    """データがない場合に空リストを返すこと"""
```

### フロントエンド: `tests/OverviewView.test.ts` 更新

```typescript
it('renders US sector performance section', async () => {
  // 米国セクターセクションが表示されること
})

it('displays sector bars with correct colors', async () => {
  // 上昇は緑、下落は赤のバーで表示されること
})

it('switches period on button click', async () => {
  // 期間ボタンクリックで再取得されること
})
```

---

## Phase 23 (米国個別銘柄ランキング) との関係

| 項目 | Phase 23 (個別銘柄) | Phase 23b (セクター ETF) |
|---|---|---|
| テーブル | `us_stocks` (新規) | `us_indices` (既存流用) |
| 取得関数 | `fetch_us_stocks()` (新規) | `fetch_us_indices()` (拡張) |
| 対象数 | 30 銘柄 | 11 ETF |
| 表示形式 | 上昇/下落ランキング (テーブル) | 横棒グラフ (ソート済み) |
| 概要ページ配置 | セクター ETF の下 | セクターヒートマップの下 |

**実装順序**: Phase 23b (セクター ETF) を先に実装する方が効率的。
- `us_indices` テーブルの流用で新テーブル不要
- `fetch_us_indices()` の拡張のみで取得完了
- Phase 23 の実装時に参考にできるパターンが増える

---

## 注意事項

### Yahoo Finance レート制限

- 既存 4 本 + セクター ETF 11 本 = 15 本
- 15 本 × 0.5 秒間隔 = 約 7.5 秒 (Lambda 900 秒に余裕あり)
- Phase 23 の個別銘柄 30 本と合わせても 45 本 × 0.5 秒 = 約 22.5 秒

### データの鮮度

- セクター ETF は米国市場で取引されるため、バッチ実行 (JST 18:00) 時点で前日のデータが取得可能
- SPY セクター ETF は流動性が高く、Yahoo Finance でのデータ欠損リスクは低い

### 初回取得

- `US_INDEX_INITIAL_PERIOD = "10y"` を共用
- セクター ETF は 2000 年代前半から存在 (XLRE: 2015年, XLC: 2018年 が最も新しい)
- 初回バッチで約 10 年分のヒストリカルデータが蓄積される

---

## 実装タスク

### タスク 1: バックエンド — データ取得拡張

1. `config.py` に `US_SECTOR_ETF_TICKERS` 追加
2. `batch/fetch_external.py` の `fetch_us_indices()` を拡張 (セクター ETF を含める)
3. `tests/test_fetch_us_sector_etf.py` 作成
4. `tests/test_fetch_us_indices.py` が引き続きパスすることを確認

### タスク 2: バックエンド — API エンドポイント

1. `api/routers/us_indices.py` に `/api/us-sectors/performance` エンドポイント追加
2. `api/routers/us_indices.py` に `/api/us-sectors/heatmap` エンドポイント追加
3. `tests/test_router_us_sectors.py` 作成
4. `docs/api_reference.md` 更新

### タスク 3: フロントエンド — 概要ページ表示

1. `types/index.ts` に `UsSectorPerformance` 型追加
2. `composables/useApi.ts` に `getUsSectorPerformance()` 追加
3. `views/OverviewView.vue` に米国セクターパフォーマンスセクション追加
4. `tests/OverviewView.test.ts` 更新
5. `docs/screen_design.md` 更新

### タスク 4: 動作確認

1. ローカルで Yahoo Finance API の動作確認 (Spike スクリプト)
2. `make test` & `make test-frontend` 全テスト通過
3. Playwright で概要ページの表示確認

---

## 将来の拡張

- **日米セクター対照表**: 米国セクター ETF と日本株セクターのリターンを並べて表示
- **セクター相関分析**: XLK ↔ 電気機器 等のセクター間相関を計算
- **グローバルセクターローテーション**: 日米セクターの回転パターンを統合分析
- **セクター ETF 詳細ページ**: 個別 ETF の時系列チャート + 構成銘柄
