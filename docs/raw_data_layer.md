# Raw Data Layer 仕様書

## 概要

全 ingestion ソースの API レスポンスを S3 に不変 JSON ファイルとして保存するレイヤー。
正規化 (SQLite への書き込み) の前に保存されるため、後から再処理・デバッグが可能。

---

## S3 キー構造

```
s3://nkflow-data-{account}/
└── raw/
    ├── jquants/
    │   ├── stock_master/{YYYY-MM-DD}.json    # 銘柄マスタ (全銘柄フル)
    │   └── daily_prices/{YYYY-MM-DD}.json    # 日次 OHLCV
    ├── yahoo_finance/
    │   ├── exchange_rates/{YYYY-MM-DD}.json  # 為替レート (USDJPY, EURUSD)
    │   ├── nikkei/{YYYY-MM-DD}.json          # 日経225 OHLC
    │   ├── us_indices/{YYYY-MM-DD}.json      # 米国指数・VIX・セクター ETF
    │   └── crypto_fng/{YYYY-MM-DD}.json      # BTC Fear & Greed Index
    ├── jquants_margin/
    │   └── margin_balance/{YYYY-MM-DD}.json  # 信用残高 (週次)
    └── (参考: 既存)
        # news/raw/{YYYY-MM-DD}.json はニュース Lambda が別途管理
```

---

## JSON ファイル形式

全ファイル共通のエンベロープ:

```json
{
  "saved_at": "2026-03-06T09:00:00+00:00",
  "source": "jquants",
  "data_type": "daily_prices",
  "date": "2026-03-06",
  "data": [ ... ]
}
```

| フィールド | 説明 |
|---|---|
| `saved_at` | 保存日時 (UTC ISO 8601) |
| `source` | データソース名 |
| `data_type` | データ種別 |
| `date` | 対象日 (YYYY-MM-DD) |
| `data` | API レスポンスそのまま (DataFrame は records 形式のリスト) |

---

## ソース別仕様

### jquants / daily_prices

| 項目 | 値 |
|---|---|
| 取得元 | J-Quants API (`get_eq_bars_daily`) |
| 取得頻度 | 毎営業日 1回 |
| 取得範囲 | 対象日 1日分 |
| `data` 形式 | records リスト (`[{"Code": "72030", "Date": "20260306", "O": 2500, ...}]`) |
| 保存タイミング | 正規化前・非取引日はスキップ |

### jquants / stock_master

| 項目 | 値 |
|---|---|
| 取得元 | J-Quants API (`get_eq_master`) |
| 取得頻度 | 毎営業日 1回 |
| 取得範囲 | プライム市場全銘柄 (フル取得) |
| `data` 形式 | records リスト (`[{"Code": "72030", "CoName": "トヨタ自動車", "S33Nm": "輸送用機器", ...}]`) |
| 保存タイミング | 正規化前 |

### yahoo_finance / exchange_rates

| 項目 | 値 |
|---|---|
| 取得元 | Yahoo Finance REST API |
| 対象 | USDJPY=X, EURUSD=X |
| 取得頻度 | 毎営業日 1回 |
| 取得範囲 | 直近30日分 (毎回フル取得) |
| `data` 形式 | `{"USDJPY": [{"date": "2026-03-06", "open": 149.5, ...}], "EURUSD": [...]}` |

### yahoo_finance / nikkei

| 項目 | 値 |
|---|---|
| 取得元 | Yahoo Finance REST API (`^N225`) |
| 取得頻度 | 毎営業日 1回 |
| 取得範囲 | 直近5日分 |
| `data` 形式 | records リスト |

### yahoo_finance / us_indices

| 項目 | 値 |
|---|---|
| 取得元 | Yahoo Finance REST API |
| 対象 | ^GSPC, ^DJI, ^IXIC, ^VIX, XLK, XLF, XLV, XLE, XLI, XLY, XLP, XLU, XLB, XLRE, XLC (15 ticker) |
| 取得頻度 | 毎営業日 1回 |
| 取得範囲 | **差分更新** (初回は過去10年、以降は前回最新日の翌日〜今日) |
| `data` 形式 | `{"^GSPC": [{"date": "2026-03-06", "open": 5700, ...}], ...}` |

### yahoo_finance / crypto_fng

| 項目 | 値 |
|---|---|
| 取得元 | Alternative.me FNG API (`https://api.alternative.me/fng/`) |
| 取得頻度 | 毎営業日 1回 |
| 取得範囲 | 直近30日分 (毎回フル取得) |
| `data` 形式 | Alternative.me API レスポンス全体 (`{"data": [{"value": "45", "value_classification": "Fear", "timestamp": "..."}], ...}`) |

### jquants_margin / margin_balance

| 項目 | 値 |
|---|---|
| 取得元 | J-Quants API (`get_mkt_margin_interest_range`) |
| 取得頻度 | 毎営業日 1回 |
| 取得範囲 | 直近14日 (DB に8週未満の場合は180日バックフィル) |
| `data` 形式 | records リスト (`[{"Code": "72030", "Date": "20260228", "LongVol": 1000000, "ShrtVol": 100000}]`) |
| 注意 | 週次データのため、毎日保存されるが内容は週1回しか更新されない |

---

## 実装詳細

### モジュール

`datalake/src/pipeline/raw_store.py`

```python
save_raw(
    source: str,
    data_type: str,
    date_str: str,
    payload: Any,
    *,
    overwrite: bool = False,
) -> Optional[str]
```

- `payload` が `pd.DataFrame` の場合は `to_dict(orient="records")` で自動変換
- `overwrite=False` (デフォルト): 同じキーが既存の場合はスキップ (immutable)
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

## 設計方針

| 項目 | 決定 | 理由 |
|---|---|---|
| フォーマット | JSON | API レスポンスの構造をそのまま保持。Parquet はスキーマ定義が必要で raw に不向き |
| 上書きポリシー | デフォルト不可 (immutable) | `overwrite=True` フラグで明示的に上書き可能 |
| 失敗時 | 非致命的 (log + 継続) | raw 保存失敗でパイプラインを止めない |
| 正規化は raw から読むか | いいえ (サイドエフェクト保存) | バッチ Lambda はメモリ上にデータがあるため S3 往復は不要 |
| ニュースとの違い | ニュースは raw → 正規化の2段構成 | ニュースは別 Lambda が raw を書き、バッチが読む構成のため |

---

## スコープ外 (将来対応)

- 既存 `news/raw/` の `raw/news/articles/` への統一 (ニュースの raw パスが他と異なる)
- raw からの再処理 (replay) スクリプト: `datalake/scripts/replay_from_raw.py`
- S3 Lifecycle ポリシー (Glacier への移行・自動削除)
- gzip 圧縮 (データ量が増えた場合)

---

最終更新: 2026-03-06
