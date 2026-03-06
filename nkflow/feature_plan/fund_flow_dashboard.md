# 資金フローダッシュボード 設計書

> 最終更新: 2026-03-03 (fix: 市場圧力が常に同じ値になる問題を修正)
> 対象ブランチ: feature/fund-flow-dashboard (dev にマージ済み)

---

## 1. 概要

セクター間の資金移動を可視化するダッシュボード。
日次バッチで推定された「資金フロー」（出来高急減セクター → 出来高急増セクターへの資金移動）を多角的に表示する。

### 主要コンポーネント

| コンポーネント | 役割 |
|---|---|
| `NetworkView.vue` | ページ全体コントローラー (フィルター管理・レイアウト) |
| `FundFlowTimeline.vue` | 時系列棒グラフ + アンカーモード (折れ線 / 積み上げ棒) |
| `FundFlowSankey.vue` | 期間集計サンキー図 (SVG自前実装) |
| `GraphView.vue` | ネットワークグラフ (vis-network / 折りたたみ表示) |
| `MarketPressureGauge.vue` | 信用評価損益率 半円ゲージ + 買残増加率バー (Phase 16) |
| `MarketPressureTimeline.vue` | 信用圧力 90日推移グラフ (ゾーン色帯 + 過熱警報縦線) (Phase 16) |

---

## 2. データフロー

```
[バッチ Lambda]
  ├─ statistics.run_fund_flow()
  │    ↓ セクター別 avg_return / volume_delta を計算
  │    ↓ outflow × inflow のクロス集計でエッジ生成
  │    ↓ INSERT INTO graph_fund_flows
  └─ statistics.run_market_pressure()          ← Phase 16
       ↓ margin_balances を週次集計
       ↓ pl_ratio_proxy (加重累積リターン近似) を計算
       ↓ INSERT INTO margin_trading_weekly
       ↓ INSERT INTO market_pressure_daily

[シグナル生成]
  └─ signals.generate_credit_overheating_signal()  ← Phase 16
       条件: pl_ratio > 0.12 AND buy_growth_4w > 0.08
       → bearish シグナル + signal_flags 更新

[API Lambda]
  ├─ GET /api/network/fund_flow          → サンキー + ネットワーク用
  ├─ GET /api/fund-flow/timeseries       → 時系列棒グラフ用
  ├─ GET /api/fund-flow/cumulative       → アンカーモード用
  └─ GET /api/market-pressure/timeseries → 信用圧力時系列 (Phase 16)

[フロントエンド]
  └─ NetworkView.vue
       ├─ MarketPressureGauge     ← /api/market-pressure/timeseries?days=7
       ├─ FundFlowTimeline        ← /api/fund-flow/timeseries, /api/fund-flow/cumulative
       ├─ MarketPressureTimeline  ← /api/market-pressure/timeseries?days=90 (折りたたみ)
       ├─ FundFlowSankey          ← /api/network/fund_flow
       └─ GraphView               ← /api/network/fund_flow
```

---

## 3. バックエンド

### 3.1 資金フロー推定ロジック (`backend/src/batch/statistics.py`)

**実行タイミング**: 毎営業日バッチの `run_all()` 内で呼ばれる (`run_fund_flow(db_path, target_date)`)

**アルゴリズム**:
1. 当日セクター別集計: `AVG(return_rate)`, `SUM(volume)` を取得
2. ベースライン計算: 直近 `FUND_FLOW_WINDOW=20` 営業日の1日あたり平均出来高
3. `volume_delta_pct = (当日 - ベースライン) / ベースライン` を計算
4. フロー判定:
   - `volume_delta_pct < -10%` かつ `avg_return < -0.5%` → **outflow セクター**
   - `volume_delta_pct > +10%` かつ `avg_return > +0.5%` → **inflow セクター**
5. outflow × inflow の全組み合わせで `graph_fund_flows` にエッジ挿入
   - `return_spread = dst.avg_return - src.avg_return`

**DBスキーマ** (`graph_fund_flows`):

| カラム | 型 | 説明 |
|---|---|---|
| sector_from | TEXT | 流出元セクター |
| sector_to | TEXT | 流入先セクター |
| volume_delta | REAL | 流出元の出来高変化率 (%) |
| return_spread | REAL | 流入先 - 流出元の騰落率差 |
| date | TEXT | 対象日 (YYYY-MM-DD) |

### 3.2 API エンドポイント (`backend/src/api/routers/network.py`)

#### `GET /api/network/fund_flow`

| パラメータ | 型 | デフォルト | 説明 |
|---|---|---|---|
| date_from | string | - | 開始日 (省略時は最新日のみ) |
| date_to | string | - | 終了日 |

**レスポンス (vis-network 互換)**:
```json
{
  "nodes": [{ "id": "電気機器", "label": "電気機器", "group": "電気機器" }],
  "edges": [{ "from": "銀行業", "to": "電気機器", "value": 5, "arrows": "to", "edge_count": 5, "coefficient": 0.012 }]
}
```
- `date_from/date_to` 指定時: `value = edge_count` (フロー発生回数), `coefficient = avg(return_spread)`
- 省略時: `value = return_spread` (最新日のみ)

#### `GET /api/fund-flow/timeseries`

| パラメータ | 型 | デフォルト | 説明 |
|---|---|---|---|
| granularity | "week" \| "month" | "week" | 集計粒度 |
| limit | int | 12 | 取得する期間数 |

**レスポンス**:
```json
{
  "periods": ["2025-W01", "2025-W02"],
  "start_dates": ["2025-01-06", "2025-01-13"],
  "series": [{
    "label": "銀行業 → 電気機器",
    "sector_from": "銀行業",
    "sector_to": "電気機器",
    "values": [{ "count": 3, "avg_spread": 0.015 }]
  }]
}
```
- 上位8ペア (総発生回数順) のみ返す

#### `GET /api/fund-flow/cumulative`

| パラメータ | 型 | 説明 |
|---|---|---|
| base_date | string | 基準日 (累積 = 0 の起点) |
| granularity | "week" \| "month" | 集計粒度 |

**レスポンス**:
```json
{
  "base_date": "2025-01-06",
  "periods": [{ "key": "2025-W02", "start_date": "2025-01-13", "regime": "risk_on" }],
  "series": [{
    "label": "銀行業 → 電気機器",
    "sector_from": "銀行業",
    "sector_to": "電気機器",
    "cumulative_spread": [0.012, 0.025],
    "sector_cumulative_return": [0.008, 0.021]
  }]
}
```
- `regime`: `daily_summary` の多数決で各期間のレジームを決定
- 上位8ペア (累積絶対スプレッド順) のみ返す

---

## 4. フロントエンド

### 4.1 NetworkView.vue (`frontend/src/views/NetworkView.vue`)

**状態管理**:

| 状態 | 型 | 説明 |
|---|---|---|
| fundFlowFilter | 'period' \| 'range' \| 'date' | フィルターモード |
| dateFrom / dateTo | string | 範囲指定 |
| dateSingle | string | 単日指定 |
| anchorDate | string \| null | アンカー基準日 (FundFlowTimeline から受信) |
| currentRegime | string \| null | 現在のレジーム |
| networkData | NetworkData \| null | サンキー + ネットワーク用データ |
| showNetwork | boolean | ネットワークセクション表示/非表示 |

**レイアウト構成**:
1. **コントロールバー**: フィルターモード切替 + 期間/範囲/日付入力
2. **時系列フロー** (常時表示): `FundFlowTimeline`
3. **サンキー図** (常時表示): `FundFlowSankey`
4. **ネットワーク** (折りたたみ): `GraphView` + 選択ノード詳細

**ヘッダーバッジ**:
- レジームバッジ: Risk-on (緑) / Risk-off (赤) / Neutral (グレー)
- アンカーバッジ: アンカー日が設定されたときに表示

### 4.2 FundFlowTimeline.vue (`frontend/src/components/charts/FundFlowTimeline.vue`)

**2つのモード**:

#### 通常モード
- **Chart.js 棒グラフ** (週次 or 月次、デフォルト)
- X軸: 期間ラベル、Y軸: 発生回数 or スプレッド平均
- **棒をクリック** → アンカーモードに切替 (クリックした週/月が基準日)
- `emit('anchor-changed', date)` で親コンポーネントへ伝播

#### アンカーモード
- 基準日以降の累積値を表示
- **ペア別折れ線**: 各ペアの累積スプレッド or 累積リターン
  - レジーム背景色プラグイン (`nkflowRegimeBg`): Risk-on=緑, Risk-off=赤の半透明帯
- **流入先で集計 (積み上げ棒)**: 流入先セクターごとの累積値を積み上げ
- 指標切替: 「累積スプレッド」「セクター累積リターン」

**コントロール**:
- 粒度: 週次 / 月次
- 指標: 発生回数 / スプレッド平均 (通常モード), 累積スプレッド / セクター累積リターン (アンカーモード)
- 集計: ペア別 / 流入先で集計 (アンカーモードのみ)
- 解除ボタン (アンカーモードのみ)

### 4.3 FundFlowSankey.vue (`frontend/src/components/charts/FundFlowSankey.vue`)

**SVGカスタム実装** (外部ライブラリ不使用):
- 固定サイズ: 600×270px (viewBox でレスポンシブ)
- 左列: 流出元セクター、右列: 流入先セクター
- Bezier 曲線で接続 (帯の幅 = フロー発生回数)
- カラー: 東証33業種対応のカラーマップ (`SECTOR_COLORS`)
- `edge_count` がある場合は回数表示、なければ絶対値

**レイアウト計算**:
1. 各ノードの総フロー量を集計
2. 高さを比例配分 (`(tot / total) * flowH`)
3. Bezier パスを大きい順に描画 (前面に小さいパスが来る)

---

## 4.4 MarketPressureGauge.vue (`frontend/src/components/charts/MarketPressureGauge.vue`)

**SVGカスタム実装** (外部ライブラリ不使用):
- 半円ゲージ: -20% (大底) ～ +15% (天井) の範囲
- 6ゾーン: bottom / sellin / weak / neutral / overheat / ceiling (各色帯)
- 針: `plRatio` の位置を指示
- 下部: `buy_growth_4w` の水平バー (緑→黄→赤)

**Props**:
- `plRatio: number | null`
- `plZone: string`
- `buyGrowth4w: number | null`

### 4.5 MarketPressureTimeline.vue (`frontend/src/components/charts/MarketPressureTimeline.vue`)

**Chart.js Line グラフ**:
- 主軸: `pl_ratio` (折れ線, 青)
- 副軸: `buy_growth_4w` (折れ線, 点線, 琥珀)
- 背景: `pl_zone` に応じた色帯 (`nkflowPressureZoneBg` plugin)
- 信用過熱警報マーカー: `signal_flags.credit_overheating=true` の日に赤縦線 (`nkflowCreditOverheating` plugin)

**Props**:
- `days?: number` (デフォルト 90)

---

## 4a. Market Pressure バックエンド (Phase 16)

### 4a.1 指標計算 (`backend/src/batch/statistics.py`)

**`run_market_pressure(db_path, target_date)`**:
1. `margin_balances` から最新 `week_date` を取得
2. SUM(margin_buy), SUM(margin_sell) → `margin_trading_weekly` に保存
3. `pl_ratio_proxy`: **最新の信用残高報告日 (latest_week) 以降**の累積リターンを margin_buy 加重平均
   - 報告日当日 (window=0) はフォールバックとして直近20営業日窓を使用 (>=5日分)
   - これにより毎営業日 pl_ratio が変動するようになる
4. `buy_growth_4w`: 現在の margin_buy_balance と4週前の比較
5. `margin_ratio_trend`: 直近**2**エントリ以上の margin_ratio を linregress で傾き算出 (旧: 4件必須)
6. `signal_flags.credit_overheating`: `pl_zone in (ceiling, overheat) AND margin_ratio >= 6.0` で True
7. `market_pressure_daily` に INSERT OR REPLACE

**`_backfill_market_pressure(db_path)`**:
- `margin_balances` に存在するが `market_pressure_daily` にない週をバックフィル
- `run_all` 末尾から呼ばれる

**`fetch_margin_balance`** (fetch_external.py):
- 既存週数 < 8 の場合は 180 日遡及取得 (初回バックフィル)

**`_calc_pl_zone(pl_ratio)`**:

| 範囲 | ゾーン |
|---|---|
| ≥ +15% | ceiling |
| ≥ +5% | overheat |
| ≥ 0% | neutral |
| ≥ -10% | weak |
| ≥ -15% | sellin |
| < -15% | bottom |

### 4a.2 信用過熱シグナル (`backend/src/batch/signals.py`)

**`generate_credit_overheating_signal(conn, target_date)`**:
- 発動条件: `pl_ratio > 0.12 AND buy_growth_4w > 0.08`
- direction: `bearish`
- confidence: `0.5 + min(0.4, (pl_ratio - 0.12) * 4 + (buy_growth_4w - 0.08) * 2)`
- 発動時: `market_pressure_daily.signal_flags = {"credit_overheating": true}`

### 4a.3 API エンドポイント (`backend/src/api/routers/network.py`)

#### `GET /api/market-pressure/timeseries`

| パラメータ | 型 | デフォルト | 説明 |
|---|---|---|---|
| days | int | 90 | 取得日数 |

**レスポンス**:
```json
{
  "dates": ["2025-03-01"],
  "pl_ratio": [0.08],
  "pl_zone": ["neutral"],
  "buy_growth_4w": [0.03],
  "margin_ratio": [4.5],
  "margin_ratio_trend": [0.1],
  "signal_flags": [{"credit_overheating": false}]
}
```

#### `GET /api/network/fund_flow` (拡張)

`include_pressure=true` パラメータ追加:
- 最新の `pl_zone` から `__pressure_bullish__` または `__pressure_bearish__` ノードを追加
- `group: "market_pressure"` → GraphView.vue で菱形 (diamond) 描画

---

## 5. 型定義 (`frontend/src/types/index.ts`)

```typescript
interface FundFlowTimeseriesValue { count: number; avg_spread: number }
interface FundFlowTimeseriesSeries {
  label: string; sector_from: string; sector_to: string
  values: FundFlowTimeseriesValue[]
}
interface FundFlowTimeseries { periods: string[]; start_dates: string[]; series: FundFlowTimeseriesSeries[] }

interface FundFlowCumulativePeriod { key: string; start_date: string; regime: string }
interface FundFlowCumulativeSeries {
  label: string; sector_from: string; sector_to: string
  cumulative_spread: number[]; sector_cumulative_return: number[]
}
interface FundFlowCumulative { base_date: string; periods: FundFlowCumulativePeriod[]; series: FundFlowCumulativeSeries[] }

// Phase 16: Market Pressure
interface MarketPressureTimeseries {
  dates: string[]
  pl_ratio: (number | null)[]
  pl_zone: string[]
  buy_growth_4w: (number | null)[]
  margin_ratio: (number | null)[]
  margin_ratio_trend: (number | null)[]
  signal_flags: Array<{ credit_overheating?: boolean }>
}
```

---

## 6. 設計上の判断・注意事項

| 項目 | 判断内容 |
|---|---|
| サンキー外部ライブラリ不使用 | `d3-sankey` 等の依存追加を避けSVGを自前実装 |
| アンカーモードの起点 | 棒グラフのバーをクリックした期間の `start_date` を基準日とする |
| レジーム背景 | Chart.js カスタムプラグインで実装 (Plugin APIによる `beforeDraw`) |
| 上位8ペア制限 | APIとフロントエンドともに上位8ペアのみ処理 (描画パフォーマンス確保) |
| NetworkView のネットワーク | デフォルト折りたたみ (解析用途のため非優先) |
| `edge_count` と `coefficient` の使い分け | 期間指定時は `edge_count` をエッジ太さに使用 (`coefficient = avg_spread`) |

---

## 7. 変更時の注意

- `graph_fund_flows` スキーマ変更 → `backend/scripts/migrate_phaseXX.py` でマイグレーション必須
- 新しいAPIエンドポイント → `backend/src/api/main.py` のルーター登録を確認
- セクターカラー変更 → `FundFlowTimeline.vue` と `FundFlowSankey.vue` の `SECTOR_COLORS` を両方更新
- 東証業種追加/変更 → `SECTOR_COLORS` に追記

---

## 8. API composable (`frontend/src/composables/useApi.ts`)

```typescript
getMarketPressureTimeseries: (days = 90) =>
  api.get('/api/market-pressure/timeseries', { params: { days } }).then(r => r.data)
```

---

## 9. 関連ファイル一覧

| ファイル | 役割 |
|---|---|
| `backend/scripts/migrate_phase16.py` | Phase 16 DB マイグレーション |
| `backend/scripts/init_sqlite.py` | 全テーブル定義 (Phase 16 テーブル含む) |
| `backend/src/batch/statistics.py` | `run_fund_flow()`, `run_market_pressure()` |
| `backend/src/batch/signals.py` | `generate_credit_overheating_signal()` |
| `backend/src/api/routers/network.py` | 全エンドポイント (market-pressure/timeseries 含む) |
| `frontend/src/views/NetworkView.vue` | ページコントローラー |
| `frontend/src/components/charts/FundFlowTimeline.vue` | 時系列チャート |
| `frontend/src/components/charts/FundFlowSankey.vue` | サンキー図 |
| `frontend/src/components/charts/MarketPressureGauge.vue` | 信用圧力ゲージ (Phase 16) |
| `frontend/src/components/charts/MarketPressureTimeline.vue` | 信用圧力タイムライン (Phase 16) |
| `frontend/src/components/network/GraphView.vue` | ネットワークグラフ (市場圧力ノード対応) |
| `frontend/src/composables/useApi.ts` | `getFundFlowTimeseries`, `getMarketPressureTimeseries` |
| `frontend/src/types/index.ts` | `FundFlowTimeseries`, `MarketPressureTimeseries` 型定義 |
| `backend/tests/test_market_pressure.py` | Phase 16 テスト (29件) |
