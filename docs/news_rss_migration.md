# ニュース取得 RSS 移行 設計書

> 最終更新: 2026-03-03
> ステータス: 設計中

---

## 1. 背景と目的

Phase 18 で導入した GDELT DOC 2.0 API ベースのニュース取得 (`nkflow-news-fetch`) が、
**GDELT API サーバーへの TCP 接続タイムアウト**により恒常的に失敗している。

- Lambda (ap-northeast-1) からもローカル (日本 IP) からも `api.gdeltproject.org:443` に接続不可
- CloudWatch Logs 上で全クエリが Connect/Read timeout → Lambda 60秒タイムアウトで強制終了
- S3 に `news/raw/` が一度も保存されていない → `news_articles` テーブルは 0 件

**対策**: GDELT を廃止し、認証不要・無制限の **RSS フィード直接取得**に切り替える。

---

## 2. RSS フィードソース

### 2.1 採用フィード一覧

| ID | ソース | カテゴリ | 言語 | URL | 更新頻度 |
|---|---|---|---|---|---|
| `nhk_biz` | NHK ビジネス | 日本経済 | JP | `https://www3.nhk.or.jp/rss/news/cat6.xml` | ~1分 |
| `nikkei_asia` | 日経アジア | 日本・アジア市場 | EN | `https://asia.nikkei.com/rss/feed/nar` | ~5分 |
| `investing_fx` | Investing.com FX | 為替 | EN | `https://www.investing.com/rss/news_25.rss` | リアルタイム |
| `investing_jp` | Investing.com 日本 | 日本市場 | EN | `https://www.investing.com/rss/news_301.rss` | リアルタイム |
| `cnbc_markets` | CNBC Markets | 米国市場 | EN | `https://www.cnbc.com/id/15838459/device/rss/rss.html` | ~15秒 |
| `mw_top` | MarketWatch | ヘッドライン | EN | `https://feeds.content.dowjones.io/public/rss/mw_topstories` | リアルタイム |
| `ft_markets` | Financial Times | グローバル市場 | EN | `https://www.ft.com/markets?format=rss` | ~15分 |

### 2.2 実地テスト結果 (2026-03-03)

全フィードを `feedparser` で取得し動作確認済み。

| ID | HTTP | 記事数 | 取得時間 | 日付フィールド | 画像 |
|---|---|---|---|---|---|
| `nhk_biz` | 200 | 130 | 0.19s | RFC 2822 (`published`) | なし |
| `nikkei_asia` | 200 | 50 | 0.30s | **なし** (title/link/id のみ) | なし |
| `investing_fx` | 200 | 10 | 0.34s | `YYYY-MM-DD HH:MM:SS` (`published`) | あり |
| `investing_jp` | 200 | 10 | 0.17s | `YYYY-MM-DD HH:MM:SS` (`published`) | なし |
| `cnbc_markets` | 200 | 30 | 0.36s | RFC 2822 (`published`) | なし |
| `mw_top` | 200 | 10 | 0.56s | RFC 2822 (`published`) | あり |
| `ft_markets` | 200 | 25 | 0.60s | RFC 2822 (`published`) | なし |

**合計 265 件 / 約 2.5 秒** (GDELT: 0 件 / 60秒タイムアウト)

> **注意: `nikkei_asia`** は RSS エントリに `published` / `updated` フィールドがない。
> 取得時刻 (`datetime.now(UTC).isoformat()`) をフォールバック日付として使用する。

### 2.3 不採用ソースと理由

| ソース | 理由 |
|---|---|
| Reuters | 2020年に RSS 全廃。公式フィードなし |
| Bloomberg | `businessweek/news.rss` のみ存続。金融カバー範囲が狭い |
| Yahoo Finance | RSS 基盤が事実上停止。安定性なし |
| 日経 (日本語版) | RSS なし。完全ペイウォール |
| WSJ | Bot 検出 (DataDome) でブロック。有料契約必要 |

---

## 3. アーキテクチャ

### 3.1 変更範囲

```
変更するファイル:
  backend/src/news/rss.py          ← 新規: RSS クライアント (gdelt.py を置換)
  backend/src/news/handler.py      ← 修正: gdelt → rss に切り替え
  backend/src/batch/fetch_news.py  ← 修正: seendate → pubDate フォーマット対応

削除するファイル:
  backend/src/news/gdelt.py        ← 廃止

テスト:
  backend/tests/test_rss.py        ← 新規: RSS クライアントテスト
  backend/tests/test_gdelt.py      ← 廃止 (test_rss.py で置換)
  backend/tests/test_news_handler.py ← 修正: モック対象を差し替え

変更なし:
  backend/src/api/routers/news.py  ← 変更不要 (SQLite スキーマ同一)
  frontend/src/views/NewsView.vue  ← 変更不要
  cdk/lib/nkflow-stack.ts          ← 変更不要 (Lambda 設定そのまま)
```

### 3.2 データフロー (変更後)

```
EventBridge Scheduler (08:50 UTC = JST 17:50)
    ↓
nkflow-news-fetch Lambda
    ├─→ src.news.rss.fetch_feeds()     [7 フィード並列取得]
    │     ├─ feedparser でパース
    │     ├─ URL ベースで重複排除
    │     └─ published_parsed → ISO 8601 に正規化
    └─→ S3: news/raw/{date}.json       [正規化済み JSON]
                ↓
Batch Lambda (09:00 UTC)
    ├─→ src.batch.fetch_news.normalize_news()
    └─→ SQLite: news_articles テーブル
                ↓
API Lambda
    └─→ GET /api/news, GET /api/news/summary
                ↓
Frontend (NewsView.vue)
```

---

## 4. 実装詳細

### 4.1 `backend/src/news/rss.py` (新規)

```python
"""RSS フィードクライアント: 複数の金融ニュース RSS を取得・正規化"""
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Optional

import feedparser

logger = logging.getLogger(__name__)

FEEDS: dict[str, str] = {
    "nhk_biz":       "https://www3.nhk.or.jp/rss/news/cat6.xml",
    "nikkei_asia":   "https://asia.nikkei.com/rss/feed/nar",
    "investing_fx":  "https://www.investing.com/rss/news_25.rss",
    "investing_jp":  "https://www.investing.com/rss/news_301.rss",
    "cnbc_markets":  "https://www.cnbc.com/id/15838459/device/rss/rss.html",
    "mw_top":        "https://feeds.content.dowjones.io/public/rss/mw_topstories",
    "ft_markets":    "https://www.ft.com/markets?format=rss",
}

REQUEST_TIMEOUT = 10  # 秒


def _parse_date(entry: dict) -> str:
    """RSS エントリの日付を ISO 8601 文字列に変換する。"""
    # feedparser が parsed tuple を提供する場合
    if entry.get("published_parsed"):
        try:
            dt = datetime(*entry["published_parsed"][:6], tzinfo=timezone.utc)
            return dt.isoformat()
        except Exception:
            pass
    # RFC 2822 文字列をフォールバック
    raw = entry.get("published") or entry.get("updated", "")
    if raw:
        try:
            return parsedate_to_datetime(raw).isoformat()
        except Exception:
            return raw
    # nikkei_asia 等: 日付フィールドなし → 取得時刻を使用
    return datetime.now(timezone.utc).isoformat()


def _fetch_one(feed_id: str, url: str) -> list[dict]:
    """単一フィードを取得してパースする。"""
    try:
        feed = feedparser.parse(
            url,
            request_headers={"User-Agent": "nkflow-news/1.0"},
        )
        if feed.bozo and not feed.entries:
            logger.warning(f"RSS パース失敗 ({feed_id}): {feed.bozo_exception}")
            return []

        articles = []
        for entry in feed.entries:
            link = entry.get("link", "")
            title = entry.get("title", "")
            if not link or not title:
                continue

            articles.append({
                "url": link,
                "title": title,
                "seendate": _parse_date(entry),
                "domain": feed_id,
                "sourcename": feed.feed.get("title", feed_id),
                "language": "Japanese" if feed_id.startswith("nhk") else "English",
                "socialimage": _extract_image(entry),
            })
        logger.info(f"RSS {feed_id}: {len(articles)} 件取得")
        return articles
    except Exception as e:
        logger.warning(f"RSS 取得失敗 ({feed_id}): {e}")
        return []


def _extract_image(entry: dict) -> Optional[str]:
    """RSS エントリからサムネイル画像 URL を抽出する。"""
    # media:thumbnail
    for media in entry.get("media_thumbnail", []):
        if media.get("url"):
            return media["url"]
    # media:content
    for media in entry.get("media_content", []):
        if media.get("url") and "image" in media.get("type", "image"):
            return media["url"]
    # enclosure
    for enc in entry.get("enclosures", []):
        if enc.get("type", "").startswith("image"):
            return enc.get("href") or enc.get("url")
    return None


def fetch_feeds(
    feeds: dict[str, str] | None = None,
    max_workers: int = 4,
) -> list[dict]:
    """全フィードを並列取得し、URL ベースで重複排除して返す。

    Returns:
        GDELT 互換の記事リスト (handler.py / fetch_news.py と同じ構造)
    """
    if feeds is None:
        feeds = FEEDS

    seen_urls: set[str] = set()
    all_articles: list[dict] = []

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(_fetch_one, fid, url): fid
            for fid, url in feeds.items()
        }
        for future in as_completed(futures):
            fid = futures[future]
            try:
                articles = future.result()
            except Exception as e:
                logger.warning(f"RSS {fid} 例外: {e}")
                continue

            for art in articles:
                if art["url"] not in seen_urls:
                    seen_urls.add(art["url"])
                    all_articles.append(art)

    logger.info(f"RSS 合計: {len(all_articles)} 件 (フィード数={len(feeds)})")
    return all_articles
```

### 4.2 `backend/src/news/handler.py` の変更

```diff
-from src.news import gdelt
+from src.news import rss

 def lambda_handler(event: dict, context) -> dict:
     date_str = event.get("date") or date.today().isoformat()

-    articles = gdelt.fetch_articles()
+    articles = rss.fetch_feeds()
```

変更は **import と 1 行の呼び出し**のみ。S3 保存ロジックはそのまま。

### 4.3 `backend/src/batch/fetch_news.py` の変更

`seendate` フィールドの日付フォーマットが GDELT (`20260303T180000Z`) から
ISO 8601 (`2026-03-03T18:00:00+00:00`) に変わるため、SQLite の `date()` 関数が
正しく動作するようになる。**コード変更不要** (既存コードが両方のフォーマットを処理可能)。

### 4.4 依存パッケージ

```toml
# pyproject.toml に追加
dependencies = [
    ...
    "feedparser>=6.0",
]
```

`feedparser` は Pure Python で外部 C ライブラリ依存なし。Lambda Docker イメージで問題なく動作する。

---

## 5. SQLite スキーマ

**変更なし**。既存の `news_articles` テーブルをそのまま使用する。

```sql
-- 既存スキーマ (変更不要)
CREATE TABLE IF NOT EXISTS news_articles (
    id            TEXT PRIMARY KEY,           -- SHA256[:16] of URL
    published_at  TEXT NOT NULL,              -- ISO 8601 datetime ← RSS では正しい ISO 形式
    source        TEXT NOT NULL,              -- フィード ID (nhk_biz, cnbc_markets 等)
    source_name   TEXT,                       -- フィードタイトル (NHK, CNBC 等)
    title         TEXT NOT NULL,
    url           TEXT NOT NULL UNIQUE,
    language      TEXT DEFAULT 'en',
    image_url     TEXT,
    tickers_json  TEXT DEFAULT '[]',
    sentiment     REAL,                       -- 将来実装 (Phase 19 以降)
    created_at    TEXT DEFAULT (datetime('now'))
);
```

---

## 6. GDELT との差異

| 項目 | GDELT (旧) | RSS (新) |
|---|---|---|
| 取得方式 | REST API (JSON) | RSS/Atom フィードパース |
| 認証 | 不要 | 不要 |
| レート制限 | なし (だが接続不可) | なし |
| ソース数 | GDELT 内部ソース群 | 7 フィード (拡張可能) |
| 言語 | English のみ | Japanese + English |
| センチメント | なし | なし (将来対応可) |
| 画像 | `socialimage` フィールド | `media:thumbnail` / `enclosure` |
| 日付形式 | `20260303T180000Z` | ISO 8601 (SQLite 互換) |
| 安定性 | 接続不可 | 各フィード独立、部分障害に強い |
| 依存ライブラリ | `requests` | `feedparser` (追加) |

---

## 7. エラーハンドリング

- 個別フィードの障害は他フィードに影響しない (`ThreadPoolExecutor` + try/except)
- 全フィード失敗時のみ SNS 通知 (既存の `handler.py` ロジックをそのまま利用)
- `feedparser` はパースエラーでも `bozo=True` を返すだけで例外を投げない
- Lambda タイムアウト (120秒) に対し、全フィード取得は通常 5〜15 秒で完了

---

## 8. テスト方針

| テストファイル | 内容 |
|---|---|
| `tests/test_rss.py` | `_parse_date`, `_extract_image`, `_fetch_one` (feedparser モック), `fetch_feeds` (統合) |
| `tests/test_news_handler.py` | `gdelt.fetch_articles` → `rss.fetch_feeds` にモック差し替え |
| `tests/test_fetch_news.py` | 変更不要 (入力 JSON 構造が同一) |

---

## 9. 実装手順

1. `feedparser` を `pyproject.toml` に追加
2. `backend/src/news/rss.py` を新規作成
3. `backend/tests/test_rss.py` を新規作成・テスト通過確認
4. `backend/src/news/handler.py` の import を切り替え
5. `backend/tests/test_news_handler.py` のモック対象を更新
6. `backend/src/news/gdelt.py` + `backend/tests/test_gdelt.py` を削除
7. `Dockerfile.news` に feedparser が含まれることを確認 (uv pip install で自動)
8. ローカルテスト全件パス確認 (`make test`)
9. CDK デプロイ (`make deploy-cdk`)
10. 翌営業日に CloudWatch Logs で動作確認

---

## 10. 将来拡張

- **センチメント分析**: 記事タイトルに対するキーワードベースまたは LLM ベースのスコアリング (Phase 19)
- **フィード追加**: `FEEDS` dict にエントリを追加するだけで拡張可能
- **日本語フィード拡張**: 時事通信、共同通信 RSS 等
- **ティッカーマッピング**: タイトル中の銘柄名を正規表現で抽出 → `news_ticker_map` に登録
