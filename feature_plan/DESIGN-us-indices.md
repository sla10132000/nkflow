# Phase XX: 米国株インデックス（S&P500 / ダウ / ナスダック）取得

## 概要

既存の `fetch_external.py`（Yahoo Finance 為替取得）を拡張し、米国主要株価指数の OHLCV データを日次バッチで取得・保存する。日本株との相関分析・リードラグ分析の基盤とする。

---

## 対象ティッカー

| 指数名 | ティッカー | 用途 |
|---|---|---|
| S&P 500 | `^GSPC` | 米国大型株全体の指標 |
| ダウ平均 | `^DJI` | 米国主要30銘柄 |
| ナスダック総合 | `^IXIC` | テック中心の指標 |

必要に応じて追加可能: ナスダック100 (`^NDX`)、VIX (`^VIX`)、米10年債利回り (`^TNX`)

---

## アーキテクチャ変更

### 変更ファイル一覧

```
backend/src/
├── batch/
│   ├── fetch_external.py   # ← 米国指数取得関数を追加
│   ├── handler.py          # ← ステップ 3.5 に米国指数取得を追加
│   ├── compute.py          # ← (Phase 2) 米国指数の騰落率計算を追加
│   └── statistics.py       # ← (Phase 2) 日米相関・リードラグ分析を追加
├── api/
│   └── routers/
│       └── us_indices.py   # ← 新規: 米国指数 API エンドポイント
└── config.py               # ← 定数追加 (US_INDEX_TICKERS)
```

### データフロー

```
Lambda: nkflow-batch
    │ (既存ステップ 3.5 に統合)
    │
    │ yfinance.download(["^GSPC","^DJI","^IXIC"])
    │   → OHLCV 取得 (直近 5 年分 or 差分更新)
    │   → DuckDB / SQLite に INSERT
    │
    └──► S3: data/stocks.db に含めて保存
```

---

## 実装仕様

### 1. config.py — 定数追加

```python
US_INDEX_TICKERS = {
    "^GSPC": "S&P 500",
    "^DJI": "Dow Jones",
    "^IXIC": "NASDAQ Composite",
}

# 初回取得期間 (それ以降は差分更新)
US_INDEX_INITIAL_PERIOD = "5y"
```

### 2. fetch_external.py — 取得関数

```python
def fetch_us_indices(db_path: str) -> dict:
    """
    米国主要株価指数の OHLCV を取得し SQLite に保存する。

    - テーブル: us_indices
    - カラム: date, ticker, name, open, high, low, close, volume
    - 差分更新: テーブル内の最新日付以降のみ取得
    - 初回: 直近 5 年分を一括取得
    - リトライ: yfinance 失敗時は 3 回まで retry (exponential backoff)
    - 戻り値: {"status": "ok", "rows_inserted": N, "tickers": [...]}
    """
```

**要件:**

- `yfinance.download()` でまとめて取得（1 銘柄ずつではなく一括）
- 既存データがあれば `start=最新日付+1日` で差分のみ取得
- 取引日のみ保存（NaN 行はスキップ）
- タイムゾーン: 日付は UTC ベースで保存（米国市場基準）
- エラー時も他ティッカーの処理は継続（個別に try-except）

### 3. SQLite テーブル定義

```sql
CREATE TABLE IF NOT EXISTS us_indices (
    date      TEXT    NOT NULL,  -- YYYY-MM-DD (UTC)
    ticker    TEXT    NOT NULL,  -- ^GSPC, ^DJI, ^IXIC
    name      TEXT    NOT NULL,  -- S&P 500, Dow Jones, etc.
    open      REAL,
    high      REAL,
    low       REAL,
    close     REAL    NOT NULL,
    volume    INTEGER,
    PRIMARY KEY (date, ticker)
);

CREATE INDEX IF NOT EXISTS idx_us_indices_ticker ON us_indices(ticker);
CREATE INDEX IF NOT EXISTS idx_us_indices_date ON us_indices(date);
```

### 4. handler.py — バッチステップ追加

```python
# ステップ 3.5 の既存処理（為替・信用残）の直後に追加
# ステップ 3.6: 米国株指数取得
logger.info("Step 3.6: Fetching US indices")
us_result = fetch_us_indices(db_path)
logger.info(f"US indices: {us_result}")
```

### 5. API エンドポイント — `routers/us_indices.py`

```python
# GET /api/us-indices
# クエリパラメータ:
#   ticker: str (optional, default: 全指数)
#   days: int (optional, default: 90)
#
# レスポンス例:
# {
#   "data": [
#     {"date": "2025-03-03", "ticker": "^GSPC", "name": "S&P 500",
#      "close": 5954.50, "change_pct": 0.52},
#     ...
#   ]
# }

# GET /api/us-indices/summary
# 各指数の最新値・前日比・年初来リターンを返す
```

### 6. main.py — ルーター登録

```python
from .routers import us_indices
app.include_router(us_indices.router, prefix="/api")
```

---

## テスト

### テストファイル: `tests/test_fetch_us_indices.py`

```python
def test_fetch_us_indices_creates_table():
    """空の DB に対して実行し、テーブルが作成されること"""

def test_fetch_us_indices_inserts_data():
    """3 ティッカー分のデータが INSERT されること"""

def test_fetch_us_indices_incremental():
    """既存データがある場合、差分のみ取得すること"""

def test_fetch_us_indices_handles_error():
    """yfinance エラー時に例外を投げず、エラー情報を返すこと"""
```

実行:

```bash
.venv/bin/python -m pytest tests/test_fetch_us_indices.py -v
```

---

## フロントエンド（任意・後続フェーズ）

Vue SPA に米国指数セクションを追加する場合:

- `/us-indices` ページ: 3 指数のチャート表示（recharts or Chart.js）
- ダッシュボード: 日経平均との相関係数を表示
- 実装後は `make deploy-frontend` を忘れないこと

---

## 注意事項

- **yfinance は非公式 API** — レート制限やデータ欠損の可能性あり。バッチ処理では適切な sleep とリトライを入れること
- **Lambda タイムアウト** — 既存 900 秒の中に収まるか確認。米国指数 3 銘柄は数秒で完了するため問題ないはず
- **Dockerfile.batch の変更は不要** — yfinance は既に依存に含まれている（為替取得で使用中）
- **差分更新のエッジケース** — 米国祝日や半日取引日の扱いは yfinance 側で自動的にハンドルされる
- **CDK 変更は不要** — DB スキーマの変更のみで、インフラ変更なし

---

## 実行手順

```bash
# 1. fetch_external.py に関数追加
# 2. handler.py にステップ追加
# 3. API ルーター追加
# 4. テスト実行
make test

# 5. デプロイ
make deploy
```
