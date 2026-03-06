# Phase 18: GDELT ニュース取得機能

## 概要

GDELT DOC 2.0 API を使い、日本株市場・世界経済・コモディティ関連ニュースを日次取得する。
将来的に銘柄紐付け・センチメント分析・フロントエンド表示へ拡張できる基盤を作る。

- GDELT DOC 2.0 API: 無料・認証不要
- パラメータ: `sort=DateDesc`, `timespan=1d`, `mode=artlist`, `format=json`

---

## アーキテクチャ: 2-Lambda 分離

ニュース取得は外部 I/O で失敗しやすいため、メインバッチと分離する。

```
EventBridge 17:50 JST (08:50 UTC)
  → Lambda: nkflow-news-fetch (新規)
     1. GDELT API で 4 カテゴリのニュースを取得
     2. S3 に raw JSON を保存
        s3://<bucket>/news/raw/YYYY-MM-DD.json

EventBridge 18:00 JST (09:00 UTC)
  → Lambda: nkflow-batch (既存)
     0. fetch_news.normalize()  ← 追加ステップ (非ブロッキング)
        S3 raw JSON → SQLite news_articles テーブルに正規化
     1. fetch_daily()           # J-Quants
     2. compute_all()           # DuckDB
     3. statistics.run_all()
     4. graph.update_and_query()
     5. signals.generate()
     ...
```

### 利点

| 項目 | 効果 |
|------|------|
| 障害分離 | ニュース API 障害がメインバッチに波及しない |
| 再処理性 | raw データが S3 に残るため再処理可能 |
| コスト最適 | news-fetch Lambda は軽量 (256MB, 60s) |

---

## GDELT クエリ設計

4 カテゴリ × 最大 50 件 = 最大 200 件/日 (URL 重複排除後はそれ以下)

| # | カテゴリ | クエリ | 目的 |
|---|----------|--------|------|
| 1 | 日本株 | `"Nikkei" OR "Tokyo Stock Exchange" OR "Japanese stocks"` | 日本市場の直接ニュース |
| 2 | 日本経済 | `"Japan economy" OR "Bank of Japan" OR "Japanese yen"` | 金融政策・為替 |
| 3 | 世界マクロ | `"Wall Street" OR "Federal Reserve" OR "global markets"` | 米国・世界経済 |
| 4 | コモディティ | `"crude oil" OR "gold price" OR "wheat corn" OR "natural gas" OR "commodity markets"` | エネルギー・貴金属・穀物 |

- `sourcelang=English` で英語記事に絞る
- クエリリストは `config.py` に定義 → 追加・変更が容易

---

## SQLite スキーマ

### news_articles

```sql
CREATE TABLE IF NOT EXISTS news_articles (
    id            TEXT PRIMARY KEY,   -- URL の SHA256[:16]
    published_at  TEXT NOT NULL,      -- ISO 8601
    source        TEXT NOT NULL,      -- ドメイン名 (reuters.com 等)
    source_name   TEXT,               -- GDELT sourcename
    title         TEXT NOT NULL,
    url           TEXT NOT NULL UNIQUE,
    language      TEXT DEFAULT 'en',
    image_url     TEXT,
    tickers_json  TEXT DEFAULT '[]',  -- 紐付け銘柄コード (将来)
    sentiment     REAL,               -- -1.0 〜 1.0 (将来)
    created_at    TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_news_published ON news_articles(published_at DESC);
CREATE INDEX IF NOT EXISTS idx_news_source ON news_articles(source);
```

### news_ticker_map (将来の銘柄紐付け用)

```sql
CREATE TABLE IF NOT EXISTS news_ticker_map (
    article_id  TEXT NOT NULL REFERENCES news_articles(id),
    ticker      TEXT NOT NULL,
    PRIMARY KEY (article_id, ticker)
);
CREATE INDEX IF NOT EXISTS idx_ntm_ticker ON news_ticker_map(ticker);
```

### 設計ポイント

- `id`: GDELT は固有 ID を返さないため URL の SHA256 先頭 16 文字を使用
- `INSERT OR REPLACE` で冪等に保存 (同じ記事を再取得しても安全)
- `sentiment`, `tickers_json` は将来拡張用 (Phase 1 では NULL)

---

## 新規ファイル一覧

### Backend

| ファイル | 役割 |
|----------|------|
| `backend/src/news/__init__.py` | パッケージ |
| `backend/src/news/gdelt.py` | GDELT API クライアント |
| `backend/src/news/handler.py` | news-fetch Lambda エントリポイント |
| `backend/src/batch/fetch_news.py` | S3 raw → SQLite 正規化 |
| `backend/Dockerfile.news` | news-fetch Lambda イメージ |
| `backend/scripts/migrate_phase18_news.py` | マイグレーション |

### Frontend

| ファイル | 役割 |
|----------|------|
| `frontend/src/views/NewsView.vue` | ニュース一覧画面 |

### テスト

| ファイル | 役割 |
|----------|------|
| `backend/tests/test_gdelt.py` | GDELT API モック |
| `backend/tests/test_fetch_news.py` | normalize_news テスト |

---

## 変更ファイル一覧

| ファイル | 変更内容 |
|----------|----------|
| `backend/scripts/init_sqlite.py` | news_articles, news_ticker_map テーブル追加 |
| `backend/src/batch/handler.py` | Step 0 に fetch_news.normalize() 追加 |
| `backend/src/api/main.py` | news ルーター登録 |
| `cdk/lib/nkflow-stack.ts` | news-fetch Lambda + EventBridge 追加 |
| `frontend/src/types/index.ts` | NewsArticle 型追加 |
| `frontend/src/composables/useApi.ts` | getNews(), getNewsSummary() 追加 |
| `frontend/src/router/index.ts` | /news ルート追加 |

---

## モジュール詳細設計

### gdelt.py

```python
GDELT_BASE = "https://api.gdeltproject.org/api/v2/doc/doc"

def fetch_articles(
    queries: list[str] | None = None,
    timespan: str = "1d",
    max_records: int = 50,
    source_lang: str = "English",
) -> list[dict]:
    """
    GDELT DOC 2.0 API から記事を取得。URL ベースで重複排除して返す。

    戻り値の各 dict:
      - url, title, seendate, socialimage, domain, language, sourcecountry
    """
```

- 複数クエリを順次実行し、URL ベースで重複排除
- タイムアウト: 15 秒/リクエスト
- エラー時は空リスト返却 (ログ出力 + 継続)

### news/handler.py

```python
def lambda_handler(event, context):
    date_str = event.get("date") or date.today().isoformat()
    articles = gdelt.fetch_articles()
    s3_key = f"news/raw/{date_str}.json"
    s3.put_object(Bucket=S3_BUCKET, Key=s3_key, Body=json.dumps(articles))
    return {"statusCode": 200, "body": {"date": date_str, "articles": len(articles)}}
```

### batch/fetch_news.py

```python
def normalize_news(conn: sqlite3.Connection, target_date: str) -> int:
    """
    S3 の raw JSON を読み、news_articles に INSERT OR REPLACE。

    - S3 に raw がなければ 0 を返す (news-fetch 未実行 or 失敗)
    - 各記事に SHA256[:16] の ID を付与
    - fetch_external.py と同じパターン (非ブロッキング、行数返却)
    """
```

### api/routers/news.py

```python
@router.get("/news")
def get_news(date: str = None, ticker: str = None,
             limit: int = 50, conn = Depends(get_connection)):
    """ニュース記事一覧 (日付・銘柄でフィルタ可能)"""

@router.get("/news/summary")
def get_news_summary(date: str = None, conn = Depends(get_connection)):
    """日次ニュースまとめ (件数・ソース分布)"""
```

---

## CDK 追加リソース

| リソース | 設定 |
|----------|------|
| Lambda `nkflow-news-fetch` | メモリ 256MB, タイムアウト 60s, Dockerfile.news |
| EventBridge Rule | `cron(50 8 ? * MON-FRI *)` UTC = JST 17:50 |
| IAM | S3 `news/raw/*` への PutObject + GetObject |
| SSM | 不要 (GDELT は認証なし) |

---

## 実装順序 (レイヤー分離)

各ステップは独立したコミットとする。

```
1. DB:       migrate_phase18_news.py + init_sqlite.py
2. Backend:  src/news/gdelt.py + handler.py + Dockerfile.news
3. Backend:  src/batch/fetch_news.py + handler.py 変更
4. Test:     test_gdelt.py + test_fetch_news.py
5. CDK:      nkflow-stack.ts
6. Backend:  src/api/routers/news.py + main.py
7. Frontend: 型・API・NewsView・ルーター
8. Docs:     設計書
```

---

## 検証方法

1. `make test` — 全テスト通過
2. ローカルで GDELT API を直接叩いて記事取得を確認
3. `npx cdk diff NkflowStack` で CDK 差分確認
4. デプロイ後、CloudWatch Logs で news-fetch Lambda の実行ログ確認
5. API `GET /api/news?date=YYYY-MM-DD` でデータ返却を確認

---

## 将来拡張ポイント

| 拡張 | 内容 |
|------|------|
| 銘柄紐付け | MeCab + 企業名辞書でルールベースマッチング → `news_ticker_map` に保存 |
| センチメント分析 | Amazon Comprehend / Bedrock で `sentiment` カラム更新 |
| 追加ニュースソース | RSS (適時開示/TDnet)、Bing News API を同一インターフェースで追加 |
| シグナル統合 | ニュース件数・センチメントを既存シグナル生成 (`signals.py`) に入力 |
| 銘柄ページ連携 | StockView に「関連ニュース」セクションを追加 |
