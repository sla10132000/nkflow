# Raw Data Layer 仕様書

## 概要

全 ingestion ソースの API レスポンスを S3 に不変 JSON ファイルとして保存するレイヤー。
正規化 (SQLite への書き込み) の前に保存されるため、後から再処理・デバッグが可能。

---

## S3 キー構造

統一フォーマット: `raw/{category}/{subcategory}/{source}/{data_type}/{YYYY-MM-DD}.json`

```
s3://nkflow-data-{account}/
└── raw/
    ├── market/                                         # 金融市場データ
    │   ├── equity/                                     # 株式
    │   │   └── jquants/
    │   │       ├── daily_prices/{YYYY-MM-DD}.json      # 日次 OHLCV
    │   │       └── stock_master/{YYYY-MM-DD}.json      # 銘柄マスタ (全銘柄フル)
    │   ├── fx/                                         # 為替
    │   │   └── yahoo_finance/
    │   │       └── exchange_rates/{YYYY-MM-DD}.json    # 為替レート (USDJPY, EURUSD)
    │   ├── index/                                      # 指数
    │   │   └── yahoo_finance/
    │   │       ├── nikkei/{YYYY-MM-DD}.json            # 日経225 OHLC
    │   │       └── us_indices/{YYYY-MM-DD}.json        # 米国指数・VIX・セクター ETF
    │   ├── sentiment/                                  # センチメント
    │   │   └── yahoo_finance/
    │   │       └── crypto_fng/{YYYY-MM-DD}.json        # BTC Fear & Greed Index
    │   └── credit/                                     # 信用
    │       └── jquants_margin/
    │           └── margin_balance/{YYYY-MM-DD}.json    # 信用残高 (週次)
    │
    ├── disaster/                                       # 災害データ
    │   ├── natural/                                    # 自然災害
    │   │   ├── jma/
    │   │   │   ├── earthquake_list/{YYYY-MM-DD}.json   # JMA 地震リスト (日次)
    │   │   │   ├── earthquake_detail/{YYYY-MM-DD}.json # JMA 地震詳細 (震度4+のみ)
    │   │   │   ├── warning_map/{YYYY-MM-DD}.json       # JMA 気象警報 (警報以上のみ)
    │   │   │   └── tsunami/{YYYY-MM-DD}.json           # JMA 津波警報
    │   │   └── usgs/
    │   │       └── earthquake/{YYYY-MM-DD}.json        # USGS 日本周辺 M3.0+ (GeoJSON)
    │   └── infra/                                      # インフラ障害 (将来)
    │       └── tepco/
    │           └── outage/{YYYY-MM-DD}.json
    │
    ├── news/                                           # ニュース (将来統一)
    │   └── feed/
    │       └── rss/
    │           └── articles/{YYYY-MM-DD}.json
    │
    └── macro/                                          # マクロ経済 (将来)
        └── stats/
            └── estat/
                └── gdp/{YYYY-MM-DD}.json
```

### カテゴリ一覧

| カテゴリ | サブカテゴリ | 説明 | 状態 |
|---|---|---|---|
| `market` | `equity` | 個別株式 (OHLCV, マスタ) | 実装済み |
| `market` | `fx` | 為替レート | 実装済み |
| `market` | `index` | 株価指数 (日経225, S&P 500 等) | 実装済み |
| `market` | `sentiment` | 市場センチメント (Fear & Greed 等) | 実装済み |
| `market` | `credit` | 信用取引 (信用残高) | 実装済み |
| `disaster` | `natural` | 自然災害 (地震, 気象, 津波) | 実装済み |
| `disaster` | `infra` | インフラ障害 (停電等) | 将来 |
| `news` | `feed` | ニュースフィード | 将来 |
| `macro` | `stats` | マクロ経済統計 | 将来 |

---

## JSON ファイル形式

全ファイル共通のエンベロープ:

```json
{
  "saved_at": "2026-03-06T09:00:00+00:00",
  "category": "market",
  "subcategory": "equity",
  "source": "jquants",
  "data_type": "daily_prices",
  "date": "2026-03-06",
  "data": [ ... ]
}
```

| フィールド | 説明 |
|---|---|
| `saved_at` | 保存日時 (UTC ISO 8601) |
| `category` | ドメインカテゴリ |
| `subcategory` | サブカテゴリ |
| `source` | データソース名 |
| `data_type` | データ種別 |
| `date` | 対象日 (YYYY-MM-DD) |
| `data` | API レスポンスそのまま (DataFrame は records 形式のリスト) |
| `reconstructed` | (オプション) `true` の場合、SQLite から再構成されたバックフィルデータ |

---

## ソース別仕様

### market / equity / jquants / daily_prices

| 項目 | 値 |
|---|---|
| 取得元 | J-Quants API (`get_eq_bars_daily`) |
| 取得頻度 | 毎営業日 1回 |
| 取得範囲 | 対象日 1日分 |
| `data` 形式 | records リスト (`[{"Code": "72030", "Date": "20260306", "O": 2500, ...}]`) |
| 保存タイミング | 正規化前・非取引日はスキップ |

### market / equity / jquants / stock_master

| 項目 | 値 |
|---|---|
| 取得元 | J-Quants API (`get_eq_master`) |
| 取得頻度 | 毎営業日 1回 |
| 取得範囲 | プライム市場全銘柄 (フル取得) |
| `data` 形式 | records リスト (`[{"Code": "72030", "CoName": "トヨタ自動車", "S33Nm": "輸送用機器", ...}]`) |
| 保存タイミング | 正規化前 |

### market / fx / yahoo_finance / exchange_rates

| 項目 | 値 |
|---|---|
| 取得元 | Yahoo Finance REST API |
| 対象 | USDJPY=X, EURUSD=X |
| 取得頻度 | 毎営業日 1回 |
| 取得範囲 | 直近30日分 (毎回フル取得) |
| `data` 形式 | `{"USDJPY": [{"date": "2026-03-06", "open": 149.5, ...}], "EURUSD": [...]}` |

### market / index / yahoo_finance / nikkei

| 項目 | 値 |
|---|---|
| 取得元 | Yahoo Finance REST API (`^N225`) |
| 取得頻度 | 毎営業日 1回 |
| 取得範囲 | 直近5日分 |
| `data` 形式 | records リスト |

### market / index / yahoo_finance / us_indices

| 項目 | 値 |
|---|---|
| 取得元 | Yahoo Finance REST API |
| 対象 | ^GSPC, ^DJI, ^IXIC, ^VIX, XLK, XLF, XLV, XLE, XLI, XLY, XLP, XLU, XLB, XLRE, XLC (15 ticker) |
| 取得頻度 | 毎営業日 1回 |
| 取得範囲 | **差分更新** (初回は過去10年、以降は前回最新日の翌日〜今日) |
| `data` 形式 | `{"^GSPC": [{"date": "2026-03-06", "open": 5700, ...}], ...}` |

### market / sentiment / yahoo_finance / crypto_fng

| 項目 | 値 |
|---|---|
| 取得元 | Alternative.me FNG API (`https://api.alternative.me/fng/`) |
| 取得頻度 | 毎営業日 1回 |
| 取得範囲 | 直近30日分 (毎回フル取得) |
| `data` 形式 | Alternative.me API レスポンス全体 (`{"data": [{"value": "45", "value_classification": "Fear", "timestamp": "..."}], ...}`) |

### market / credit / jquants_margin / margin_balance

| 項目 | 値 |
|---|---|
| 取得元 | J-Quants API (`get_mkt_margin_interest_range`) |
| 取得頻度 | 毎営業日 1回 |
| 取得範囲 | 直近14日 (DB に8週未満の場合は180日バックフィル) |
| `data` 形式 | records リスト (`[{"Code": "72030", "Date": "20260228", "LongVol": 1000000, "ShrtVol": 100000}]`) |
| 注意 | 週次データのため、毎日保存されるが内容は週1回しか更新されない |

### disaster / natural / jma / earthquake_list

| 項目 | 値 |
|---|---|
| 取得元 | JMA 防災情報 (`https://www.jma.go.jp/bosai/quake/data/list.json`) |
| 認証 | なし (公開 API) |
| 取得頻度 | 毎日 1回 (取引日に依存しない) |
| 取得範囲 | list.json から target_date の地震イベントをフィルタ |
| `data` 形式 | `[{"eid": "...", "at": "2026-03-06T...", "anm": "北海道北西沖", "mag": "5.2", "maxi": "4", ...}]` |
| 保存条件 | 対象日にイベントがある場合のみ |

### disaster / natural / jma / earthquake_detail

| 項目 | 値 |
|---|---|
| 取得元 | JMA 防災情報 (`https://www.jma.go.jp/bosai/quake/data/{filename}`) |
| 取得頻度 | earthquake_list に震度4以上がある場合のみ |
| `data` 形式 | 詳細 JSON のリスト (`[{"Head": {...}, "Body": {"Earthquake": {...}}}]`) |

### disaster / natural / jma / warning_map

| 項目 | 値 |
|---|---|
| 取得元 | JMA 防災情報 (`https://www.jma.go.jp/bosai/warning/data/warning/map.json`) |
| 認証 | なし |
| 取得頻度 | 毎日 1回 |
| `data` 形式 | 警報以上のエリアリスト (`[{"code": "011000", "warnings": [{"code": "03", "status": "発表"}], ...}]`) |
| 保存条件 | 警報以上が発表中の場合のみ (注意報のみの日は保存しない) |
| 注意 | 元の map.json は約235KB。警報以上のエリアのみ抽出して保存 |

### disaster / natural / jma / tsunami

| 項目 | 値 |
|---|---|
| 取得元 | JMA 防災情報 (`https://www.jma.go.jp/bosai/tsunami/data/list.json`) |
| 認証 | なし |
| 取得頻度 | 毎日 1回 |
| `data` 形式 | 津波警報リスト |
| 保存条件 | 空配列でない場合のみ (津波警報は稀) |

### disaster / natural / usgs / earthquake

| 項目 | 値 |
|---|---|
| 取得元 | USGS FDSNWS (`https://earthquake.usgs.gov/fdsnws/event/1/query`) |
| 認証 | なし |
| 取得頻度 | 毎日 1回 |
| パラメータ | `format=geojson`, 日本周辺 (lat 30-46, lon 128-146), M3.0+, target_date |
| `data` 形式 | GeoJSON FeatureCollection (`{"type": "FeatureCollection", "features": [{"properties": {"mag": 4.7, "sig": 340, ...}, "geometry": {...}}]}`) |
| 保存条件 | features が空でない場合のみ |

---

## 実装詳細

### モジュール

`datalake/src/pipeline/raw_store.py`

```python
save_raw(
    category: str,
    subcategory: str,
    source: str,
    data_type: str,
    date_str: str,
    payload: Any,
    *,
    overwrite: bool = False,
    reconstructed: bool = False,
) -> Optional[str]
```

- `payload` が `pd.DataFrame` の場合は `to_dict(orient="records")` で自動変換
- `overwrite=False` (デフォルト): 同じキーが既存の場合はスキップ (immutable)
- `reconstructed=True`: エンベロープに `"reconstructed": true` を追加 (バックフィル用)
- 保存失敗は `None` を返してログ出力のみ (パイプラインは継続)

### 保存タイミング

```
API 呼び出し
    ↓
レスポンス受信 (DataFrame / dict)
    ↓
save_raw() ← ここで S3 に保存
    ↓
正規化・SQLite INSERT
```

---

## バックフィル

### スクリプト

`datalake/scripts/backfill_raw.py`

```bash
# 全ソースをバックフィル
python scripts/backfill_raw.py --db-path /tmp/stocks.db

# 特定ソースのみ
python scripts/backfill_raw.py --db-path /tmp/stocks.db --source jquants/daily_prices

# ドライラン (保存せずに対象日数を確認)
python scripts/backfill_raw.py --db-path /tmp/stocks.db --dry-run

# 各ソース最大5日分だけ
python scripts/backfill_raw.py --db-path /tmp/stocks.db --limit 5
```

### バックフィル方法 (ソース別)

| ソース | 方法 | 理由 |
|---|---|---|
| jquants/daily_prices | SQLite から再構成 | J-Quants API は過去データの再取得に制限あり |
| jquants/stock_master | スキップ | 銘柄マスタは現時点のスナップショットのみ意味がある |
| yahoo_finance/exchange_rates | SQLite から再構成 | DB に既にある |
| yahoo_finance/nikkei | SQLite から再構成 (us_indices テーブルの ^N225) | DB に既にある |
| yahoo_finance/us_indices | SQLite から再構成 | DB に既にある |
| yahoo_finance/crypto_fng | スクリプト未対応 (Alternative.me API で再取得可能) | 将来対応 |
| jquants_margin/margin_balance | SQLite から再構成 | J-Quants API は取得期間に制限あり |

### 再構成データのフォーマット

SQLite から再構成したデータは `"reconstructed": true` フラグで区別:

```json
{
  "saved_at": "2026-03-06T...",
  "category": "market",
  "subcategory": "equity",
  "source": "jquants",
  "data_type": "daily_prices",
  "date": "2024-01-15",
  "reconstructed": true,
  "data": [
    {"code": "7203", "date": "2024-01-15", "open": 2500, ...}
  ]
}
```

---

## 設計方針

| 項目 | 決定 | 理由 |
|---|---|---|
| フォーマット | JSON | API レスポンスの構造をそのまま保持。Parquet はスキーマ定義が必要で raw に不向き |
| 上書きポリシー | デフォルト不可 (immutable) | `overwrite=True` フラグで明示的に上書き可能 |
| 失敗時 | 非致命的 (log + 継続) | raw 保存失敗でパイプラインを止めない |
| 正規化は raw から読むか | いいえ (サイドエフェクト保存) | バッチ Lambda はメモリ上にデータがあるため S3 往復は不要 |
| ニュースとの違い | ニュースは raw → 正規化の2段構成 | ニュースは別 Lambda が raw を書き、バッチが読む構成のため |
| キー構造 | 4層 (category/subcategory/source/data_type) | 金融以外のドメイン (災害・マクロ等) にも統一的に拡張可能 |

---

## スコープ外 (将来対応)

- 既存 `news/raw/` の `raw/news/feed/rss/articles/` への統一
- raw からの再処理 (replay) スクリプト: `datalake/scripts/replay_from_raw.py`
- S3 Lifecycle ポリシー (Glacier への移行・自動削除)
- gzip 圧縮 (データ量が増えた場合)
- crypto_fng のバックフィル (Alternative.me API `limit` パラメータ使用)

---

最終更新: 2026-03-06
