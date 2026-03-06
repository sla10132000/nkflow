# 日本株「海外売り・個人買い」転換検知システム 設計書

## 1. 目的

日本株市場における需給転換（海外売り・個人買い / 海外買い・個人売り）を早期検知する分析機能を nkflow に追加する。

主な目的:

- 投資主体別フローから相場フェーズを推定する
- 天井圏・底入れ候補を早期に検知する
- 資金フローの構造を可視化する
- 既存の資金フローダッシュボード（NetworkView）に統合する

---

## 2. 背景

日本株市場では JPX が投資主体別売買動向を週次で公開しており、「誰が買っているか / 売っているか」を分析できる。

### 典型パターン

| フェーズ | 海外投資家 | 個人 |
|----------|-----------|------|
| 上昇相場 | 買い | 売り |
| 天井圏 | 売り | 買い |
| 下落終盤 | 買い | 売り |

この構造を定量化することで、相場転換の兆候を検出する。

---

## 3. システムスコープ

### 対象市場

- TSE Prime（東証プライム市場）

### 将来拡張

- TOPIX / 日経平均との相関分析
- セクター別投資主体フロー
- 個別銘柄レベルの分析

---

## 4. 入力データ

### 4.1 投資部門別売買動向（必須・新規取得）

**データソース**: J-Quants API `/markets/trades_spec`

| 項目 | 値 |
|------|-----|
| エンドポイント | `GET https://api.jquants.com/v1/markets/trades_spec` |
| 認証 | Bearer token（既存の `JQUANTS_API_KEY` を使用） |
| 頻度 | 週次（毎週木曜 15:30 公開） |
| セクション | `TSEPrime` |
| パラメータ | `section`, `from`, `to`, `pagination_key` |

**レスポンスの主要フィールド**（単位: 千円）:

| カテゴリ | フィールド名（売り / 買い / 差引） |
|----------|----------------------------------|
| 海外投資家 (Foreigners) | `ForeignersSales` / `ForeignersPurchases` / `ForeignersBalance` |
| 個人 (Individuals) | `IndividualsSales` / `IndividualsPurchases` / `IndividualsBalance` |
| 投資信託 (Investment Trusts) | `InvestmentTrustsSales` / `InvestmentTrustsPurchases` / `InvestmentTrustsBalance` |
| 信託銀行 (Trust Banks) | `TrustBanksSales` / `TrustBanksPurchases` / `TrustBanksBalance` |
| 事業法人 (Business Companies) | `BusinessCompaniesSales` / `BusinessCompaniesPurchases` / `BusinessCompaniesBalance` |

**メタデータ**: `PublishedDate`, `StartDate`, `EndDate`, `Section`

**制約**:
- `section` と `from/to` は排他（どちらか一方のみ指定可能）
- レスポンスが大きすぎると 413 エラー

### 4.2 株価データ（既存）

既存の `daily_prices` テーブルをそのまま使用。日経平均は `daily_summary.nikkei_close` から取得。

### 4.3 補助データ（既存）

| データ | テーブル | 用途 |
|--------|---------|------|
| USDJPY | `exchange_rates` | 為替との相関確認 |
| VIX | `us_indices` (^VIX) | リスクオフ局面の判定補助 |
| 市場レジーム | `daily_summary.regime` | 既存レジームとの整合性チェック |

---

## 5. 既存アーキテクチャへの統合

```
EventBridge Scheduler (毎営業日 JST 18:00)
    │
    ▼
Lambda: nkflow-batch (既存)
    │ ... 既存処理 ...
    │ ★ 新規: fetch_investor_flows()   ← datalake/src/ingestion/jquants.py に追加
    │ ★ 新規: compute_flow_indicators() ← datalake/src/transform/statistics.py に追加
    │ ★ 新規: generate_flow_signals()   ← datalake/src/signals/generator.py に追加
    │
    └──► S3: data/stocks.db (既存テーブルに追加)

API Gateway (既存)
    │ ★ 新規: /api/investor-flows/*     ← nkflow/backend/src/api/routers/investor_flows.py
    ▼
Lambda: nkflow-api (既存)
    └──► stocks.db 読み取り

Frontend (既存)
    │ ★ 新規: NetworkView に投資主体フローセクションを追加
    ▼
```

**変更範囲**:
- 新規ファイル 3 つ（ingestion 関数、API ルーター、フロントコンポーネント）
- 既存ファイル 4 つに追記（handler.py、statistics.py、generator.py、init_sqlite.py）

---

## 6. データモデル

### 6.1 investor_flow_weekly（新規テーブル）

J-Quants API のレスポンスを正規化して保存する。

| column | type | PK | description |
|--------|------|-----|-------------|
| week_start | TEXT | PK | 週開始日 (YYYY-MM-DD) |
| week_end | TEXT | PK | 週終了日 (YYYY-MM-DD) |
| section | TEXT | PK | 市場区分 (TSEPrime) |
| investor_type | TEXT | PK | `foreigners` / `individuals` / `trust_banks` / `investment_trusts` / `business_cos` |
| sales | REAL | | 売り (千円) |
| purchases | REAL | | 買い (千円) |
| balance | REAL | | 差引 (千円) = purchases - sales |
| published_date | TEXT | | 公開日 |
| created_at | TEXT | | レコード作成日時 |

### 6.2 investor_flow_indicators（新規テーブル）

計算済み指標を保存する。

| column | type | PK | description |
|--------|------|-----|-------------|
| week_end | TEXT | PK | 週終了日 |
| foreigners_net | REAL | | 海外差引 (百万円) |
| individuals_net | REAL | | 個人差引 (百万円) |
| foreigners_4w_ma | REAL | | 海外 4 週移動平均 |
| individuals_4w_ma | REAL | | 個人 4 週移動平均 |
| foreigners_momentum | REAL | | 海外モメンタム (今週 − 4 週前) |
| individuals_momentum | REAL | | 個人モメンタム |
| divergence_score | REAL | | ダイバージェンス・スコア |
| nikkei_return_4w | REAL | | 日経平均 4 週リターン |
| flow_regime | TEXT | | `bull` / `topping` / `bear` / `bottoming` |

### 6.3 シグナル出力

既存の `signals` テーブルに新しい `signal_type` を追加する（テーブル新設不要）。

| signal_type | direction | 意味 |
|-------------|-----------|------|
| `investor_flow_topping` | bearish | 天井警戒 |
| `investor_flow_bottoming` | bullish | 底入れ候補 |
| `investor_flow_divergence` | bearish / bullish | フロー乖離 |

`reasoning` フィールドに詳細を JSON で格納:

```json
{
  "foreigners_net": -150000,
  "individuals_net": 80000,
  "divergence_score": 0.85,
  "nikkei_return_4w": 0.03,
  "flow_regime": "topping"
}
```

---

## 7. 指標設計

### 7.1 移動平均 (4 週)

```
foreigners_4w_ma[t] = mean(foreigners_net[t-3 : t])
individuals_4w_ma[t] = mean(individuals_net[t-3 : t])
```

フローの短期トレンドを平滑化する。

### 7.2 モメンタム (4 週変化)

```
foreigners_momentum[t] = foreigners_net[t] - foreigners_net[t-4]
individuals_momentum[t] = individuals_net[t] - individuals_net[t-4]
```

フローの加速・減速を検出する。

### 7.3 ダイバージェンス・スコア

海外と個人の逆行度合いを -1.0 〜 +1.0 で定量化する。

```
# 各主体の 4 週 MA を z-score に変換
z_foreign = (foreigners_4w_ma - mean) / std    # 直近 26 週の平均・標準偏差
z_individual = (individuals_4w_ma - mean) / std

# スコア = 個人 z-score − 海外 z-score（個人買い・海外売り で正の値）
divergence_score = z_individual - z_foreign

# -1.0 〜 +1.0 にクリップ
divergence_score = clip(divergence_score / 2, -1.0, +1.0)
```

| divergence_score | 解釈 |
|-----------------|------|
| +0.5 以上 | 強い天井警戒（個人買い・海外売り） |
| +0.2 〜 +0.5 | 弱い天井警戒 |
| -0.2 〜 +0.2 | 中立 |
| -0.5 〜 -0.2 | 弱い底入れ兆候 |
| -0.5 以下 | 強い底入れ兆候（海外買い・個人売り） |

### 7.4 フローレジーム判定

4 つの条件を組み合わせてレジームを判定する。

| regime | 条件 |
|--------|------|
| `bull` | foreigners_4w_ma > 0 AND individuals_4w_ma < 0 |
| `topping` | foreigners_momentum < 0 AND individuals_momentum > 0 AND nikkei_return_4w > 0 |
| `bear` | foreigners_4w_ma < 0 AND individuals_4w_ma > 0 AND nikkei_return_4w < 0 |
| `bottoming` | foreigners_momentum > 0 AND individuals_momentum < 0 AND nikkei_return_4w < 0 |

いずれにも該当しない場合は直前のレジームを維持する。

---

## 8. シグナル定義

### 8.1 天井警戒 (`investor_flow_topping`)

**条件** (すべて満たす):

1. `divergence_score >= 0.5`
2. `foreigners_momentum < 0`（海外が売りに転換）
3. `nikkei_return_4w > 0`（株価はまだ上昇中）

**confidence**: `min(abs(divergence_score), 1.0)`

### 8.2 底入れ候補 (`investor_flow_bottoming`)

**条件** (すべて満たす):

1. `divergence_score <= -0.5`
2. `foreigners_momentum > 0`（海外が買いに転換）
3. `nikkei_return_4w < 0`（株価はまだ下落中）

**confidence**: `min(abs(divergence_score), 1.0)`

### 8.3 フロー乖離 (`investor_flow_divergence`)

天井・底入れの条件を満たさないが、ダイバージェンスが閾値を超えた場合の早期警戒シグナル。

**条件**: `abs(divergence_score) >= 0.3` かつ上記 8.1 / 8.2 に該当しない

**direction**: `divergence_score > 0` → bearish / `divergence_score < 0` → bullish

---

## 9. API エンドポイント

既存 API Gateway に新規ルーターを追加する。

### `GET /api/investor-flows/timeseries`

投資主体別フローの時系列データを返す。

| パラメータ | 型 | デフォルト | 説明 |
|-----------|-----|----------|------|
| `weeks` | int | 52 | 取得週数 (1〜260) |
| `investor_type` | string | — | フィルタ (foreigners / individuals) |

**レスポンス例**:

```json
[
  {
    "week_start": "2026-02-24",
    "week_end": "2026-02-28",
    "investor_type": "foreigners",
    "sales": 5200000,
    "purchases": 4800000,
    "balance": -400000
  }
]
```

### `GET /api/investor-flows/indicators`

計算済み指標とフローレジームを返す。

| パラメータ | 型 | デフォルト | 説明 |
|-----------|-----|----------|------|
| `weeks` | int | 26 | 取得週数 |

**レスポンス例**:

```json
[
  {
    "week_end": "2026-02-28",
    "foreigners_net": -400000,
    "individuals_net": 250000,
    "foreigners_4w_ma": -200000,
    "individuals_4w_ma": 150000,
    "divergence_score": 0.65,
    "nikkei_return_4w": 0.02,
    "flow_regime": "topping"
  }
]
```

### `GET /api/investor-flows/latest`

最新週のフロー + 指標 + シグナルをまとめて返す（ダッシュボード用）。

**レスポンス例**:

```json
{
  "week_end": "2026-02-28",
  "flows": {
    "foreigners": { "sales": 5200000, "purchases": 4800000, "balance": -400000 },
    "individuals": { "sales": 3000000, "purchases": 3250000, "balance": 250000 }
  },
  "indicators": {
    "divergence_score": 0.65,
    "flow_regime": "topping",
    "foreigners_4w_ma": -200000,
    "individuals_4w_ma": 150000
  },
  "signal": {
    "type": "investor_flow_topping",
    "direction": "bearish",
    "confidence": 0.65
  }
}
```

---

## 10. フロント画面

既存の NetworkView（資金フローダッシュボード）に統合する。

### 10.1 投資主体フローセクション

NetworkView の信用圧力ゲージの下に追加する。

```
┌─── 投資主体別フロー ──────────────────────────────┐
│                                                    │
│  最新週: 2026-02-28    レジーム: [TOPPING]          │
│  ダイバージェンス: ████████████░░░ 0.65             │
│                                                    │
│ ┌──────────────────────────────────────────────┐   │
│ │  [海外投資家 (青棒)] [個人 (赤棒)] [日経 (灰線)] │   │
│ │  ████               ████                      │   │
│ │  ████  ██           ████  ████                │   │
│ │  ────────────────────────────────             │   │
│ │  W1    W2    W3    W4    W5    W6             │   │
│ └──────────────────────────────────────────────┘   │
│                                                    │
└────────────────────────────────────────────────────┘
```

### 10.2 コンポーネント

| コンポーネント | 種類 | 用途 |
|---------------|------|------|
| `InvestorFlowChart` | Chart.js 棒 + 折れ線 | 海外/個人の差引推移 + 日経平均オーバーレイ |
| `DivergenceGauge` | SVG バー | ダイバージェンス・スコア (-1 〜 +1) |

---

## 11. 実装フェーズ

### Phase 1: データ取得 + 保存

- `datalake/src/ingestion/jquants.py` に `fetch_investor_flows()` を追加
- `nkflow/backend/scripts/init_sqlite.py` に `investor_flow_weekly` テーブルを追加
- `datalake/src/pipeline/handler.py` のバッチに組み込み

### Phase 2: 指標計算

- `datalake/src/transform/statistics.py` に `compute_investor_flow_indicators()` を追加
- `investor_flow_indicators` テーブルへの書き込み

### Phase 3: シグナル生成

- `datalake/src/signals/generator.py` に投資主体フローシグナルを追加
- 既存 `signals` テーブルに `investor_flow_*` タイプで INSERT

### Phase 4: API

- `nkflow/backend/src/api/routers/investor_flows.py` を新規作成
- `nkflow/backend/src/api/main.py` にルーター登録

### Phase 5: フロントエンド

- `InvestorFlowChart.vue` + `DivergenceGauge.vue` を作成
- `NetworkView.vue` に統合

### Phase 6: バックテスト

- 既存バックテストエンジンで `investor_flow_*` シグナルを評価
- 4 週 / 8 週 / 12 週リターンで精度検証

---

## 12. バックテスト評価基準

| 指標 | 基準 |
|------|------|
| 天井警戒シグナル → 4 週後リターン | 負が 60% 以上なら有効 |
| 底入れ候補シグナル → 4 週後リターン | 正が 60% 以上なら有効 |
| 8 週後 / 12 週後 | 同様に方向一致率を確認 |

---

## 13. テスト

### Unit Test

- `test_investor_flows.py`: フロー取得・正規化のテスト（moto で J-Quants モック）
- `test_flow_indicators.py`: 指標計算のテスト（固定データで期待値検証）
- `test_flow_signals.py`: シグナル条件のテスト

### Integration Test

- `test_router_investor_flows.py`: API エンドポイントのテスト（TestClient + SQLite tmp_path）

### Frontend Test

- `InvestorFlowChart.test.ts`: Chart.js コンポーネントのテスト
- `DivergenceGauge.test.ts`: ゲージ表示のテスト

---

## 14. 非機能要件

| 項目 | 基準 |
|------|------|
| API レスポンス | 1 秒以内 |
| バッチ追加時間 | 既存バッチ +30 秒以内 |
| テストカバレッジ | 新規コード 80% 以上 |

---

## 15. 将来拡張

- セクター別投資主体フロー分析
- 信託銀行・投資信託フローの追加指標
- 先物・オプションの投資主体フローとの統合
- AI による転換点予測モデル
- Slack / LINE アラート連携（既存 SNS 通知に追加）

---

## 参考

- [JPX 投資部門別売買状況](https://www.jpx.co.jp/markets/statistics-equities/investor-type/index.html)
- [J-Quants API — Trading by Type of Investors](https://jpx.gitbook.io/j-quants-en/api-reference/trades_spec)
