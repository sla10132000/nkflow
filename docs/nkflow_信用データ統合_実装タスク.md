# 信用系データ統合 実装タスク

> nkflow 資金フローダッシュボードへの市場圧力 (Market Pressure) ノード追加
>
> 作成日: 2026-03-02 | データソース: J-Quants Standard API

---

## 概要

既存の資金フローダッシュボードに、J-Quants Standard APIから取得する信用取引データを統合し、「市場圧力 (Market Pressure)」という新しいノード層を追加する。これにより、「なぜそのセクターに資金が流れたか」の説明力を大幅に強化する。

> **グラフ構造の変更**
>
> 現在: セクターA → セクターB (資金移動)
> 追加後: MarketPressure(Bullish/Bearish) → セクター → 銘柄
> → 資金フローの「原因」を圧力ノードで説明可能に

> **最終ゴール: 信用過熱警報シグナル**
>
> 発動条件: 評価損益率 > +12% AND 信用買残4週増加率 > +8% AND 外人買い減速
> 日経の大きな下げの直前に高確率で出現。テクニカルの天井判定より早く出る。

---

## 指標優先順位

| 優先度 | 指標 | 意味 | 実装ポイント |
|---|---|---|---|
| ★★★★ | 信用評価損益率 | 日本市場の"恐怖指数"。株価より1〜4週先行。市場ノード(TOPIX/日経225)に持たせる | 銘柄ごとはノイズ。TOPIX平均・日経225平均を市場ノードとして保持 |
| ★★★ | 信用買残増加率 | 水準ではなく4週変化率。株価上昇+急増は「最後の上げ」 | (today - 4w_ago) / 4w_ago。個人がトレンドに参加したサイン |
| ★★ | 信用倍率 | 補助指標。高いだけでは危険でなく、上昇トレンドが危険 | 買残 ÷ 売残。4週移動平均の傾きでトレンド判定 |
| ★ | 貸借倍率 | 機関+裁定の動き。信用倍率(個人)と分離可能 | 信用取引=個人、貸借取引=空売り機関が関与 |

---

## Phase 1: データ取得・保存基盤

目的: J-Quants APIから信用系データを取得し、DBに保存する基盤を作る。

| # | タスク内容 | 対象ファイル | 工数目安 | 依存 |
|---|---|---|---|---|
| 1-1 | **DBスキーマ追加: `margin_trading_weekly` テーブル作成** — カラム: date, market_code (TOPIX/N225), margin_buy_balance, margin_sell_balance, margin_pl_ratio, lending_buy_balance, lending_sell_balance | migrate_phaseXX.py | 0.5h | なし |
| 1-2 | **J-Quants APIクライアント: 信用取引週次データ取得関数実装** — `/markets/weekly-margin-interest` エンドポイント対応。TOPIX平均・日経225平均を分離して保存 | jquants_client.py | 1.5h | 1-1 |
| 1-3 | **バッチ組み込み: `run_all()` 内で週次実行されるように統合** — 曜日判定 (毎週火曜日以降で取得) + 重複チェック | statistics.py | 1h | 1-2 |
| 1-4 | **過去データバックフィル: 直近1年分の信用系データを一括取得・保存するスクリプト** | backfill_margin.py | 1h | 1-2 |

---

## Phase 2: 指標計算エンジン

目的: 生データからシグナルに使える指標を算出する。

| # | タスク内容 | 対象ファイル | 工数目安 | 依存 |
|---|---|---|---|---|
| 2-1 | **信用評価損益率ゾーン判定ロジック実装** — +15%=天井圏, +5%=過熱, 0%=中立, -10%=弱気, -15%=セリクラ近い, -20%=大底。結果を `market_pressure_daily` テーブルに保存 | statistics.py | 1.5h | 1-3 |
| 2-2 | **信用買残4週増加率の算出** — `buy_residual_growth = (today_balance - 4w_ago_balance) / 4w_ago_balance`。危険判定: 株価上昇 + 増加率 > 8% → 「最後の上げ」フラグ | statistics.py | 1h | 1-3 |
| 2-3 | **信用倍率・貸借倍率のトレンド計算** — 信用倍率 = 買残 ÷ 売残。4週移動平均の傾きで上昇トレンド判定。貸借倍率も同様に算出 (機関の動き分離用) | statistics.py | 1h | 1-3 |

> **評価損益率のゾーン目安 (経験則)**
>
> +15%前後 = 天井圏 | +5% = 過熱 | 0% = 中立 | -10% = 弱気 | -15% = セリクラ近い | -20%以下 = 大底ゾーン
>
> 重要: 株価より1〜4週先行するため、A波検出に直結する

---

## Phase 3: 圧力ノード統合 (バックエンド)

目的: 信用データを「圧力ノード」として既存の資金フローグラフに統合する。

| # | タスク内容 | 対象ファイル | 工数目安 | 依存 |
|---|---|---|---|---|
| 3-1 | **DBスキーマ: `market_pressure_daily` テーブル作成** — カラム: date, pressure_type (Bullish/Bearish), pl_ratio, pl_zone, buy_growth_4w, margin_ratio, margin_ratio_trend, lending_ratio, signal_flags (JSON) | migrate_phaseXX.py | 0.5h | 2-1 |
| 3-2 | **APIエンドポイント: `GET /api/network/market_pressure`** — レスポンス: 圧力ノードの属性一式 + vis-network互換ノード形式。既存 `/api/network/fund_flow` に圧力ノードをマージするオプションも | network.py | 1.5h | 3-1 |
| 3-3 | **APIエンドポイント: `GET /api/market-pressure/timeseries`** — 評価損益率・信用買残増加率・信用倍率の時系列データを返却。ゾーン判定結果も含む | network.py | 1h | 3-1 |
| 3-4 | **信用過熱警報シグナルロジック実装** — 発動条件: `pl_ratio > +12% AND buy_growth_4w > +8% AND 外人買い減速`。`market_pressure_daily.signal_flags` に記録。APIでアラートとして返却 | statistics.py | 1.5h | 2-1, 2-2 |

> **設計上の注意**
>
> 圧力ノードは「フロー」ではなく「属性」として持たせる。ネットワークグラフでは MarketPressure(Bullish) / MarketPressure(Bearish) からセクターへのエッジとして描画する。銘柄ノードには持たせない。

---

## Phase 4: フロントエンド統合

目的: ダッシュボードUIに圧力ノードと警報シグナルを表示する。

| # | タスク内容 | 対象ファイル | 工数目安 | 依存 |
|---|---|---|---|---|
| 4-1 | **`MarketPressureGauge.vue` コンポーネント作成** — 評価損益率ゲージ (大底〜天井の半円メーター)、信用買残増加率バー、信用倍率トレンド矢印 | MarketPressureGauge.vue | 2h | 3-2, 3-3 |
| 4-2 | **`MarketPressureTimeline.vue` コンポーネント作成** — Chart.js 折れ線グラフ: 評価損益率の推移 + ゾーン背景色。信用買残増加率を副軸でオーバーレイ | MarketPressureTimeline.vue | 2.5h | 3-3 |
| 4-3 | **`GraphView.vue` 拡張: 圧力ノードの描画対応** — MarketPressure(Bullish) = 緑菱形, MarketPressure(Bearish) = 赤菱形。セクターノードへのエッジを追加 (edge太さ = 圧力強度) | GraphView.vue | 1.5h | 3-2 |
| 4-4 | **`NetworkView.vue` 拡張: レイアウトに統合** — ヘッダーに信用過熱警報バッジを追加 (点滅アニメーション)。MarketPressureGauge をサイドバー or ヘッダー下に配置。MarketPressureTimeline を FundFlowTimeline の上に配置 | NetworkView.vue | 1.5h | 4-1, 4-2 |

---

## Phase 5: テスト・検証

目的: バックテストでシグナルの有効性を検証する。

| # | タスク内容 | 対象ファイル | 工数目安 | 依存 |
|---|---|---|---|---|
| 5-1 | **過去データで信用過熱警報のバックテスト** — 過去1年分のデータでシグナル発動日と日経の大幅下落の相関を検証。先行日数・的中率・偽陽性率を計測 | test_margin_signal.py | 2h | 3-4 |
| 5-2 | **評価損益率ゾーンと市場レジームの整合性検証** — 既存の risk_on / risk_off 判定と評価損益率ゾーンの一致率を確認。矛盾がある場合のハンドリングルールを策定 | test_regime_consistency.py | 1.5h | 2-1 |

---

## 依存関係・実行順序

**クリティカルパス:** `1-1 → 1-2 → 1-3 → 2-1 → 3-4` (信用過熱警報の完成まで)

**並行可能:** 2-2, 2-3 は 2-1 と並行で実行可能。Phase 4 内の 4-1, 4-2, 4-3 も並行可能。

## 影響ファイル一覧

| ファイル | 変更内容 |
|---|---|
| `backend/scripts/migrate_phaseXX.py` | 新規: margin_trading_weekly + market_pressure_daily |
| `backend/src/batch/jquants_client.py` | 新規 or 追加: J-Quants信用データAPI |
| `backend/src/batch/statistics.py` | 追加: 指標計算 + シグナルロジック |
| `backend/scripts/backfill_margin.py` | 新規: 過去データバックフィル |
| `backend/src/api/routers/network.py` | 追加: 2エンドポイント |
| `frontend/src/views/NetworkView.vue` | 拡張: レイアウト + 警報バッジ |
| `frontend/src/components/charts/MarketPressureGauge.vue` | 新規: ゲージコンポーネント |
| `frontend/src/components/charts/MarketPressureTimeline.vue` | 新規: 時系列チャート |
| `frontend/src/components/network/GraphView.vue` | 拡張: 圧力ノード描画 |
| `frontend/src/types/index.ts` | 追加: MarketPressure型定義 |
| `frontend/src/composables/useApi.ts` | 追加: API呼び出し関数 |
