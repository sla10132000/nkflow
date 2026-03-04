# nkflow API リファレンス

Base URL: `https://<api-gateway-url>/prod/api`

全エンドポイントは `GET` (読み取り専用) が基本。ポートフォリオ関連のみ `POST` / `DELETE` を使用。

---

## 目次

1. [Summary — 日次サマリ](#1-summary--日次サマリ)
2. [Prices — 株価時系列](#2-prices--株価時系列)
3. [Stock — 銘柄詳細](#3-stock--銘柄詳細)
4. [Network — ネットワークグラフ](#4-network--ネットワークグラフ)
5. [Fund Flow — 資金フロー分析](#5-fund-flow--資金フロー分析)
6. [Market Pressure — 市場圧力指標](#6-market-pressure--市場圧力指標)
7. [Forex — 為替レート](#7-forex--為替レート)
8. [Margin — 信用残高](#8-margin--信用残高)
9. [Backtest — バックテスト結果](#9-backtest--バックテスト結果)
10. [Portfolio — ポートフォリオ管理](#10-portfolio--ポートフォリオ管理)
11. [Sector Rotation — セクターローテーション分析](#11-sector-rotation--セクターローテーション分析)
12. [News — ニュース記事](#12-news--ニュース記事)
13. [US Indices — 米国株価指数](#13-us-indices--米国株価指数)

---

## 1. Summary — 日次サマリ

### `GET /api/summary`

直近 N 日分の日次マーケットサマリを返す。

**Query Parameters**

| パラメータ | 型 | デフォルト | 説明 |
|---|---|---|---|
| `days` | int | 30 | 取得日数 |

**Response** `200 OK` — `DailySummary[]`

```json
[
  {
    "date": "2026-03-03",
    "nikkei_close": 37500.0,
    "nikkei_return": -0.012,
    "regime": "risk_off",
    "top_gainers": [
      { "code": "7203", "name": "トヨタ自動車", "sector": "輸送用機器", "return_rate": 0.035 }
    ],
    "top_losers": [
      { "code": "6758", "name": "ソニーグループ", "sector": "電気機器", "return_rate": -0.028 }
    ],
    "active_signals": 5,
    "sector_rotation": [
      { "sector": "電気機器", "avg_return": 0.012, "total_volume": 1500000 }
    ]
  }
]
```

---

## 2. Prices — 株価時系列

### `GET /api/prices/{code}`

指定銘柄の OHLCV 時系列データを返す。

**Path Parameters**

| パラメータ | 型 | 説明 |
|---|---|---|
| `code` | string | 銘柄コード (例: `7203`) |

**Query Parameters**

| パラメータ | 型 | デフォルト | 説明 |
|---|---|---|---|
| `from_` | string | — | 開始日 (YYYY-MM-DD) |
| `to` | string | — | 終了日 (YYYY-MM-DD) |

**Response** `200 OK` — `DailyPrice[]`

```json
[
  {
    "date": "2026-03-03",
    "open": 2500.0,
    "high": 2550.0,
    "low": 2480.0,
    "close": 2530.0,
    "volume": 1200000,
    "return_rate": 0.012,
    "price_range": 70.0,
    "range_pct": 0.028,
    "relative_strength": 1.05
  }
]
```

**Error** `404` — 銘柄データが見つからない場合

---

## 3. Stock — 銘柄詳細

### `GET /api/stock/{code}`

銘柄の総合情報を返す: 基本情報 + 直近価格 + 因果連鎖 + 相関銘柄 + クラスター + シグナル。

**Path Parameters**

| パラメータ | 型 | 説明 |
|---|---|---|
| `code` | string | 銘柄コード |

**Response** `200 OK` — `StockDetail`

```json
{
  "code": "7203",
  "name": "トヨタ自動車",
  "sector": "輸送用機器",
  "recent_prices": [
    { "date": "2026-03-03", "open": 2500.0, "high": 2550.0, "low": 2480.0, "close": 2530.0, "volume": 1200000, "return_rate": 0.012 }
  ],
  "causes": [
    { "target": "6758", "lag_days": 2, "p_value": 0.003, "f_stat": 8.5, "name": "ソニーグループ", "sector": "電気機器" }
  ],
  "caused_by": [
    { "source": "8306", "lag_days": 1, "p_value": 0.01, "f_stat": 6.2, "name": "三菱UFJフィナンシャル", "sector": "銀行業" }
  ],
  "correlated": [
    { "peer_code": "7267", "coefficient": 0.85, "name": "本田技研工業", "sector": "輸送用機器" }
  ],
  "cluster": {
    "community_id": 3,
    "members": [
      { "code": "7267", "name": "本田技研工業", "sector": "輸送用機器" }
    ]
  },
  "signals": [
    {
      "id": 42,
      "date": "2026-03-03",
      "signal_type": "causality_chain",
      "direction": "bullish",
      "confidence": 0.78,
      "reasoning": { "chain": ["8306", "7203"], "lag_days": 2 }
    }
  ]
}
```

**Error** `404` — 銘柄が見つからない場合

---

## 4. Network — ネットワークグラフ

### `GET /api/network/{type}`

vis-network 互換のネットワークデータを返す。

**Path Parameters**

| パラメータ | 型 | 説明 |
|---|---|---|
| `type` | string | `correlation` / `causality` / `fund_flow` |

**Query Parameters**

| パラメータ | 型 | デフォルト | 説明 |
|---|---|---|---|
| `period` | string | `60d` | 分析期間 (例: `20d`, `60d`)。correlation / causality で使用 |
| `threshold` | float | 0.7 | 相関/因果の閾値。correlation / causality で使用 |
| `date_from` | string | — | 期間開始日 (YYYY-MM-DD)。fund_flow で使用 |
| `date_to` | string | — | 期間終了日 (YYYY-MM-DD)。fund_flow で使用 |
| `include_pressure` | bool | false | 市場圧力ノードを追加する (fund_flow のみ) |

**Response** `200 OK` — `NetworkData`

```json
{
  "nodes": [
    { "id": "7203", "label": "7203", "group": "輸送用機器" }
  ],
  "edges": [
    { "from": "7203", "to": "7267", "value": 0.85, "arrows": "to" }
  ]
}
```

`fund_flow` で `date_from` / `date_to` を指定した場合、edges に追加フィールド:

| フィールド | 型 | 説明 |
|---|---|---|
| `edge_count` | int | 期間内の出現頻度 |
| `coefficient` | float | 平均 return_spread |

`include_pressure=true` の場合、nodes に市場圧力ノードが追加される:
- `__pressure_bullish__` (pl_zone が neutral / bottom 系)
- `__pressure_bearish__` (pl_zone が ceiling / overheat)

**Error** `400` — 不明な type を指定した場合

---

## 5. Fund Flow — 資金フロー分析

### `GET /api/fund-flow/timeseries`

セクター間の資金フローを時系列で集計して返す。上位 8 ペアに絞られる。

**Query Parameters**

| パラメータ | 型 | デフォルト | 説明 |
|---|---|---|---|
| `granularity` | string | `week` | `week` / `month` |
| `limit` | int | 12 | 取得する期間数 |

**Response** `200 OK` — `FundFlowTimeseries`

```json
{
  "periods": ["2026-W06", "2026-W07"],
  "start_dates": ["2026-02-03", "2026-02-10"],
  "series": [
    {
      "label": "電気機器 → 銀行業",
      "sector_from": "電気機器",
      "sector_to": "銀行業",
      "values": [
        { "count": 5, "avg_spread": 0.012 },
        { "count": 3, "avg_spread": -0.005 }
      ]
    }
  ]
}
```

**Error** `400` — granularity が `week` / `month` 以外

---

### `GET /api/fund-flow/cumulative`

基準日からの累積 return_spread とセクター累積リターンを返す。上位 8 ペアに絞られる。

**Query Parameters**

| パラメータ | 型 | デフォルト | 説明 |
|---|---|---|---|
| `base_date` | string | **(必須)** | 基準日 (YYYY-MM-DD)。累積 = 0 の起点 |
| `granularity` | string | `week` | `week` / `month` |

**Response** `200 OK` — `FundFlowCumulative`

```json
{
  "base_date": "2026-01-06",
  "periods": [
    { "key": "2026-W02", "start_date": "2026-01-06", "regime": "risk_on" }
  ],
  "series": [
    {
      "label": "電気機器 → 銀行業",
      "sector_from": "電気機器",
      "sector_to": "銀行業",
      "cumulative_spread": [0.012, 0.025],
      "sector_cumulative_return": [0.008, 0.015]
    }
  ]
}
```

---

## 6. Market Pressure — 市場圧力指標

### `GET /api/market-pressure/timeseries`

信用圧力指標の週次時系列を返す。

**Query Parameters**

| パラメータ | 型 | デフォルト | 説明 |
|---|---|---|---|
| `days` | int | 90 | 取得期間日数 |

**Response** `200 OK` — `MarketPressureTimeseries`

```json
{
  "dates": ["2026-02-07", "2026-02-14"],
  "pl_ratio": [1.25, 1.18],
  "pl_zone": ["neutral", "ceiling"],
  "buy_growth_4w": [0.05, -0.02],
  "margin_ratio": [3.2, 3.5],
  "margin_ratio_trend": [0.1, 0.3],
  "signal_flags": [
    { "credit_overheating": false },
    { "credit_overheating": true }
  ]
}
```

---

## 7. Forex — 為替レート

### `GET /api/forex`

通貨ペアの為替レート時系列を返す。

**Query Parameters**

| パラメータ | 型 | デフォルト | 説明 |
|---|---|---|---|
| `pair` | string | `USDJPY` | 通貨ペア (例: `USDJPY`, `EURUSD`) |
| `days` | int | 60 | 取得日数 (1〜365) |

**Response** `200 OK`

```json
[
  {
    "date": "2026-03-03",
    "pair": "USDJPY",
    "open": 149.5,
    "high": 150.2,
    "low": 149.1,
    "close": 149.8,
    "change_rate": -0.003,
    "ma20": 150.5
  }
]
```

---

### `GET /api/forex/latest`

全通貨ペアの最新レートを返す。ヘッダー表示用。

**Response** `200 OK`

```json
[
  { "date": "2026-03-03", "pair": "USDJPY", "close": 149.8, "change_rate": -0.003 },
  { "date": "2026-03-03", "pair": "EURUSD", "close": 1.085, "change_rate": 0.002 }
]
```

---

## 8. Margin — 信用残高

### `GET /api/margin/{code}`

指定銘柄の信用残高の週次時系列を返す。

**Path Parameters**

| パラメータ | 型 | 説明 |
|---|---|---|
| `code` | string | 銘柄コード |

**Query Parameters**

| パラメータ | 型 | デフォルト | 説明 |
|---|---|---|---|
| `weeks` | int | 26 | 取得週数 (1〜104) |

**Response** `200 OK`

```json
[
  {
    "week_date": "2026-02-28",
    "margin_buy": 5000000,
    "margin_sell": 1000000,
    "margin_ratio": 5.0,
    "buy_change": 200000,
    "sell_change": -50000
  }
]
```

---

### `GET /api/margin/risk/high`

信用倍率が閾値以上の銘柄一覧を返す (追証リスク監視)。

**Query Parameters**

| パラメータ | 型 | デフォルト | 説明 |
|---|---|---|---|
| `ratio_threshold` | float | 8.0 | 信用倍率の下限 (1.0〜) |

**Response** `200 OK`

```json
[
  {
    "code": "9984",
    "name": "ソフトバンクグループ",
    "sector": "情報・通信業",
    "week_date": "2026-02-28",
    "margin_buy": 8000000,
    "margin_sell": 500000,
    "margin_ratio": 16.0,
    "buy_change": 300000,
    "sell_change": -20000
  }
]
```

---

## 9. Backtest — バックテスト結果

### `GET /api/backtest`

バックテスト実行一覧を返す (新しい順)。

**Query Parameters**

| パラメータ | 型 | デフォルト | 説明 |
|---|---|---|---|
| `limit` | int | 20 | 取得件数 (1〜100) |

**Response** `200 OK`

```json
[
  {
    "id": 1,
    "name": "因果チェーン 60日",
    "signal_type": "causality_chain",
    "from_date": "2025-01-01",
    "to_date": "2025-12-31",
    "holding_days": 5,
    "direction_filter": null,
    "min_confidence": 0.6,
    "created_at": "2026-03-01T10:00:00",
    "total_trades": 120,
    "win_rate": 0.58,
    "avg_return": 0.015,
    "total_return": 0.42,
    "max_drawdown": -0.12,
    "sharpe_ratio": 1.35
  }
]
```

---

### `GET /api/backtest/{run_id}`

指定バックテストの設定と集計結果を返す。

**Path Parameters**

| パラメータ | 型 | 説明 |
|---|---|---|
| `run_id` | int | バックテスト実行 ID |

**Response** `200 OK`

```json
{
  "run": {
    "id": 1,
    "name": "因果チェーン 60日",
    "signal_type": "causality_chain",
    "from_date": "2025-01-01",
    "to_date": "2025-12-31",
    "holding_days": 5,
    "direction_filter": null,
    "min_confidence": 0.6,
    "created_at": "2026-03-01T10:00:00"
  },
  "result": {
    "run_id": 1,
    "total_trades": 120,
    "win_rate": 0.58,
    "avg_return": 0.015,
    "total_return": 0.42,
    "max_drawdown": -0.12,
    "sharpe_ratio": 1.35
  }
}
```

**Error** `404` — run_id が存在しない場合

---

### `GET /api/backtest/{run_id}/trades`

指定バックテストのトレード明細を返す (ページング対応)。

**Path Parameters**

| パラメータ | 型 | 説明 |
|---|---|---|
| `run_id` | int | バックテスト実行 ID |

**Query Parameters**

| パラメータ | 型 | デフォルト | 説明 |
|---|---|---|---|
| `code` | string | — | 銘柄コードでフィルタ |
| `limit` | int | 200 | 取得件数 (1〜1000) |
| `offset` | int | 0 | オフセット |

**Response** `200 OK`

```json
[
  {
    "id": 1,
    "signal_id": 42,
    "code": "7203",
    "stock_name": "トヨタ自動車",
    "signal_date": "2025-06-01",
    "entry_date": "2025-06-02",
    "exit_date": "2025-06-07",
    "entry_price": 2500.0,
    "exit_price": 2575.0,
    "return_rate": 0.03,
    "direction": "bullish"
  }
]
```

**Error** `404` — run_id が存在しない場合

---

## 10. Portfolio — ポートフォリオ管理

> ポートフォリオデータは専用の `portfolio.db` に格納される。
> 現在価格は `stocks.db` から参照。

### `GET /api/portfolio/holdings`

保有銘柄一覧を返す。現在価格・評価額・含み損益を付与。

**Response** `200 OK`

```json
[
  {
    "code": "7203",
    "name": "トヨタ自動車",
    "sector": "輸送用機器",
    "quantity": 100,
    "avg_cost": 2400.0,
    "entry_date": "2025-10-15",
    "note": "長期保有",
    "updated_at": "2026-03-03T09:00:00",
    "current_price": 2530.0,
    "valuation": 253000.0,
    "cost_basis": 240000.0,
    "unrealized_pnl": 13000.0,
    "unrealized_pnl_pct": 5.42
  }
]
```

---

### `POST /api/portfolio/holdings`

保有銘柄を追加または更新する (UPSERT)。

**Request Body**

```json
{
  "code": "7203",
  "quantity": 100,
  "avg_cost": 2400.0,
  "entry_date": "2025-10-15",
  "note": "長期保有"
}
```

| フィールド | 型 | 必須 | 説明 |
|---|---|---|---|
| `code` | string | Yes | 銘柄コード |
| `quantity` | float | Yes | 保有株数 (> 0) |
| `avg_cost` | float | Yes | 平均取得単価 (> 0) |
| `entry_date` | string | Yes | 初回取得日 (YYYY-MM-DD) |
| `note` | string | No | メモ |

**Response** `201 Created`

```json
{ "code": "7203", "status": "upserted" }
```

---

### `DELETE /api/portfolio/holdings/{code}`

保有銘柄を削除する。

**Path Parameters**

| パラメータ | 型 | 説明 |
|---|---|---|
| `code` | string | 銘柄コード |

**Response** `200 OK`

```json
{ "code": "7203", "status": "deleted" }
```

**Error** `404` — 保有銘柄が見つからない場合

---

### `GET /api/portfolio/transactions`

取引履歴を返す (ページング対応)。

**Query Parameters**

| パラメータ | 型 | デフォルト | 説明 |
|---|---|---|---|
| `code` | string | — | 銘柄コードでフィルタ |
| `action` | string | — | `buy` / `sell` でフィルタ |
| `limit` | int | 100 | 取得件数 (1〜1000) |
| `offset` | int | 0 | オフセット |

**Response** `200 OK`

```json
[
  {
    "id": 1,
    "code": "7203",
    "date": "2025-10-15",
    "action": "buy",
    "quantity": 100,
    "price": 2400.0,
    "fee": 500.0,
    "note": "初回購入"
  }
]
```

---

### `POST /api/portfolio/transactions`

取引を登録し、保有銘柄の平均取得単価と数量を自動更新する。

- **buy**: holdings 存在時は加重平均で avg_cost を更新 + quantity 加算。未保有時は新規追加。
- **sell**: quantity を減算。保有数を超える場合は `400` エラー。残数 0 で holdings 自動削除。

**Request Body**

```json
{
  "code": "7203",
  "date": "2026-03-03",
  "action": "buy",
  "quantity": 50,
  "price": 2530.0,
  "fee": 500.0,
  "note": "追加購入"
}
```

| フィールド | 型 | 必須 | 説明 |
|---|---|---|---|
| `code` | string | Yes | 銘柄コード |
| `date` | string | Yes | 取引日 (YYYY-MM-DD) |
| `action` | string | Yes | `buy` / `sell` |
| `quantity` | float | Yes | 株数 (> 0) |
| `price` | float | Yes | 取引単価 (> 0) |
| `fee` | float | No | 手数料 (デフォルト 0) |
| `note` | string | No | メモ |

**Response** `201 Created`

```json
{ "status": "created", "code": "7203", "action": "buy" }
```

**Error** `400` — 売却数量が保有数を超える場合 / holdings 未保有で sell の場合

---

### `GET /api/portfolio/performance`

ポートフォリオの日次評価額推移を返す (portfolio_snapshots テーブル)。

**Query Parameters**

| パラメータ | 型 | デフォルト | 説明 |
|---|---|---|---|
| `days` | int | 90 | 取得日数 (1〜730) |

**Response** `200 OK`

```json
[
  {
    "date": "2026-03-03",
    "total_valuation": 500000.0,
    "total_cost_basis": 450000.0,
    "total_unrealized_pnl": 50000.0
  }
]
```

---

### `GET /api/portfolio/signals`

保有銘柄に関連するシグナルを返す。

**Query Parameters**

| パラメータ | 型 | デフォルト | 説明 |
|---|---|---|---|
| `days` | int | 7 | 取得日数 (1〜90) |

**Response** `200 OK`

```json
[
  {
    "id": 42,
    "date": "2026-03-03",
    "signal_type": "causality_chain",
    "code": "7203",
    "sector": "輸送用機器",
    "direction": "bullish",
    "confidence": 0.78,
    "reasoning": { "chain": ["8306", "7203"], "lag_days": 2 }
  }
]
```

---

## 11. Sector Rotation — セクターローテーション分析

### `GET /api/sector-rotation/heatmap`

セクター別リターンのヒートマップデータを返す。

**Query Parameters**

| パラメータ | 型 | デフォルト | 説明 |
|---|---|---|---|
| `periods` | int | 12 | 取得する期間数 |
| `period_type` | string | `weekly` | `weekly` / `monthly` |

**Response** `200 OK` — `SectorRotationHeatmap`

```json
{
  "periods": ["2026-W06", "2026-W07"],
  "sectors": ["電気機器", "銀行業", "輸送用機器"],
  "data": [
    { "period": "2026-W06", "sector": "電気機器", "return_rate": 0.025, "rank": 1 },
    { "period": "2026-W06", "sector": "銀行業", "return_rate": 0.012, "rank": 2 }
  ]
}
```

**Error** `400` — 不明な period_type

---

### `GET /api/sector-rotation/states`

ローテーション状態の時系列を返す (古い順)。

**Query Parameters**

| パラメータ | 型 | デフォルト | 説明 |
|---|---|---|---|
| `cluster_method` | string | `kmeans` | クラスタリング手法 |
| `limit` | int | 52 | 取得期間数 |

**Response** `200 OK` — `SectorRotationStates`

```json
{
  "states": [
    {
      "period": "2026-W06",
      "state_id": 2,
      "state_name": "テック主導",
      "top_sectors": [
        { "sector": "電気機器", "avg_return": 0.03 }
      ]
    }
  ]
}
```

---

### `GET /api/sector-rotation/transitions`

状態遷移確率行列と各状態の平均持続期間を返す。

**Query Parameters**

| パラメータ | 型 | デフォルト | 説明 |
|---|---|---|---|
| `cluster_method` | string | `kmeans` | クラスタリング手法 |

**Response** `200 OK` — `SectorRotationTransitions`

```json
{
  "transitions": [
    { "from_state": 0, "to_state": 1, "probability": 0.35, "count": 7 }
  ],
  "state_names": { "0": "景気敏感", "1": "ディフェンシブ", "2": "テック主導" },
  "avg_durations": { "0": 3.2, "1": 4.5, "2": 2.8 }
}
```

---

### `GET /api/sector-rotation/prediction`

最新のローテーション状態予測を返す。

**Response** `200 OK` — `SectorRotationPrediction`

予測データがある場合:

```json
{
  "available": true,
  "calc_date": "2026-03-03",
  "current": { "state_id": 2, "state_name": "テック主導" },
  "prediction": { "state_id": 1, "state_name": "ディフェンシブ", "confidence": 0.72 },
  "top_sectors": [
    { "sector": "食料品", "avg_return": 0.018 }
  ],
  "all_probabilities": [
    { "state_id": 0, "state_name": "景気敏感", "probability": 0.15 },
    { "state_id": 1, "state_name": "ディフェンシブ", "probability": 0.72 },
    { "state_id": 2, "state_name": "テック主導", "probability": 0.13 }
  ],
  "model_accuracy": 0.68
}
```

予測データがない場合:

```json
{ "available": false }
```

---

## 12. News — ニュース記事

### `GET /api/news`

ニュース記事一覧を返す。

**Query Parameters**

| パラメータ | 型 | デフォルト | 説明 |
|---|---|---|---|
| `date` | string | — | 対象日 (YYYY-MM-DD)。省略時は全期間 |
| `ticker` | string | — | 銘柄コードで絞り込み (news_ticker_map 経由) |
| `limit` | int | 50 | 最大返却件数 |

**Response** `200 OK` — `NewsArticle[]`

```json
[
  {
    "id": "abc123",
    "published_at": "2026-03-03T06:30:00Z",
    "source": "reuters",
    "source_name": "Reuters",
    "title": "Toyota raises profit forecast",
    "title_ja": "トヨタが利益予想を上方修正",
    "url": "https://example.com/article",
    "language": "en",
    "image_url": "https://example.com/image.jpg",
    "sentiment": 0.8
  }
]
```

---

### `GET /api/news/summary`

日次ニュースの件数とソース分布を返す。

**Query Parameters**

| パラメータ | 型 | デフォルト | 説明 |
|---|---|---|---|
| `date` | string | — | 集計対象日 (YYYY-MM-DD)。省略時は全期間 |

**Response** `200 OK` — `NewsSummary`

```json
{
  "date": "2026-03-03",
  "total": 42,
  "sources": [
    { "source": "reuters", "count": 15 },
    { "source": "nikkei", "count": 12 }
  ]
}
```

---

## 13. US Indices — 米国株価指数

### `GET /api/us-indices`

米国主要株価指数の時系列データを返す。

**Query Parameters**

| パラメータ | 型 | デフォルト | 説明 |
|---|---|---|---|
| `ticker` | string | — | 指数ティッカー (例: `^GSPC`)。省略時は全指数 |
| `days` | int | 90 | 取得日数 (1〜1825) |

**Response** `200 OK`

```json
[
  {
    "date": "2026-03-03",
    "ticker": "^GSPC",
    "name": "S&P 500",
    "open": 5200.0,
    "high": 5250.0,
    "low": 5180.0,
    "close": 5230.0,
    "volume": 3500000000,
    "change_pct": 0.45
  }
]
```

---

### `GET /api/us-indices/summary`

各指数の最新値・前日比・年初来リターンを返す。

**Response** `200 OK`

```json
[
  {
    "ticker": "^GSPC",
    "name": "S&P 500",
    "date": "2026-03-03",
    "close": 5230.0,
    "change_pct": 0.45,
    "ytd_return_pct": 3.2
  }
]
```

---

## 14. Fear Indices — 恐怖指数 (Phase 21)

### `GET /api/fear-indices/latest`

最新の恐怖指数を返す。VIX は `us_indices` テーブルから取得、BTC Fear & Greed は `crypto_fear_greed` テーブルから取得。

**Response** `200 OK`

```json
{
  "vix": {
    "value": 21.58,
    "change_pct": -1.2,
    "date": "2026-03-04"
  },
  "btc_fear_greed": {
    "value": 10,
    "classification": "Extreme Fear",
    "date": "2026-03-04"
  }
}
```

| フィールド | 型 | 説明 |
|---|---|---|
| `vix` | object \| null | VIX 最新値。データなしの場合 null |
| `vix.value` | float | 現在の VIX 値 |
| `vix.change_pct` | float \| null | 前日比変化率 (%) |
| `vix.date` | string | データ日付 (YYYY-MM-DD) |
| `btc_fear_greed` | object \| null | Bitcoin Fear & Greed Index。データなしの場合 null |
| `btc_fear_greed.value` | int | 0〜100 のスコア |
| `btc_fear_greed.classification` | string | ラベル (Extreme Fear / Fear / Neutral / Greed / Extreme Greed) |
| `btc_fear_greed.date` | string | データ日付 (YYYY-MM-DD) |

**VIX ソース**: Yahoo Finance `^VIX` (バッチで日次取得、`us_indices` テーブルに保存)

**BTC Fear & Greed ソース**: Alternative.me API (`https://api.alternative.me/fng/`)、バッチで日次取得

---

## 共通仕様

### エラーレスポンス

```json
{ "detail": "エラーメッセージ" }
```

| ステータスコード | 説明 |
|---|---|
| `400` | リクエストパラメータ不正 |
| `404` | リソースが見つからない |
| `500` | サーバー内部エラー |

### データソース

| DB | 用途 | アクセスモード |
|---|---|---|
| `stocks.db` | 株価・分析結果・シグナル | 読み取り専用 |
| `portfolio.db` | ポートフォリオ管理 | 読み書き |

### 認証

現在は認証なし (パブリック API)。

---

最終更新: 2026-03-05
