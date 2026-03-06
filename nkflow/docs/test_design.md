# テスト設計書

## 1. 概要

本ドキュメントは nkflow プロジェクトのテスト戦略・現状・カバレッジ・改善計画を定義する。

**最終更新**: 2026-03-04

---

## 2. テスト戦略

### 2.1 テストピラミッド

```
        ╱  E2E  ╲          ← Playwright (未整備)
       ╱─────────╲
      ╱ Integration╲       ← API Router テスト (pytest + TestClient)
     ╱───────────────╲
    ╱   Unit Tests     ╲   ← pytest (backend) / vitest (frontend)
   ╱─────────────────────╲
```

| レイヤー | ツール | 現状 |
|---|---|---|
| Unit (Backend) | pytest + moto | 14 ファイル、~160 テスト |
| Unit (Frontend) | vitest + Vue Test Utils | 8 ファイル、~63 テスト |
| Integration (API) | pytest + TestClient | 2 ルーター (backtest, portfolio) のみ |
| E2E | Playwright | 未整備 |

### 2.2 テスト方針

- **外部 AWS サービスは moto でモック** — 実 AWS アクセスなし
- **SQLite は tmp_path で隔離** — テスト間の干渉なし
- **フロントエンドは happy-dom 環境** — ブラウザ不要
- **Chart.js / D3 等の canvas 系はモック** — `src/test/setup.ts` で定義
- **API composable (`useApi`) はモック** — `src/test/mocks/useApi.ts`

---

## 3. テスト環境・設定

### 3.1 バックエンド

| 項目 | 設定 |
|---|---|
| フレームワーク | pytest |
| モック | moto (S3, SSM, SNS), unittest.mock |
| conftest.py | `S3_BUCKET=test-nkflow-bucket`, `JQUANTS_API_KEY=test-api-key` 等ダミー環境変数 |
| 実行コマンド | `make test` or `.venv/bin/python -m pytest tests/ -v` |
| Worktree 内実行 | `/Volumes/Data/work/prj/code/nkflow/backend/.venv/bin/python -m pytest tests/ -v` |

### 3.2 フロントエンド

| 項目 | 設定 |
|---|---|
| フレームワーク | vitest |
| DOM 環境 | happy-dom |
| Vue テスト | @vue/test-utils (mount / flushPromises) |
| setup.ts | Canvas mock, ResizeObserver mock |
| 実行コマンド | `make test-frontend` or `cd frontend && npx vitest run` |

### 3.3 Lint

| 項目 | 設定 |
|---|---|
| バックエンド | ruff (`make lint`) |
| フロントエンド | Biome (`make lint-frontend`) |

---

## 4. 現状のテストカバレッジ

### 4.1 バックエンド テスト一覧

#### Batch レイヤー (データパイプライン)

| テストファイル | 対象モジュール | テスト数 | 主なテスト内容 |
|---|---|---|---|
| test_fetch.py | batch/fetch.py | 10 | J-Quants API、銘柄マスタ同期、OHLCV 取得 |
| test_fetch_external.py | batch/fetch_external.py | 10 | 為替レート、信用残高、エラーハンドリング |
| test_fetch_news.py | batch/fetch_news.py | 7 | ニュース正規化、記事処理 |
| test_fetch_us_indices.py | batch/fetch_us_indices.py | 4 | 米国指数取得、差分更新 |
| test_compute.py | batch/compute.py | 19 | 騰落率、相関係数、セクターサマリー、相対強度 |
| test_statistics.py | batch/statistics.py | 14 | グレンジャー因果、リードラグ、資金フロー、市場レジーム |
| test_graph.py | batch/graph.py | 15 | KùzuDB 操作、因果チェーン、コミュニティ検出 |
| test_backtest.py | batch/backtest.py | 16 | 売買シミュレーション、メトリクス計算 |
| test_market_pressure.py | batch/market_pressure.py | 18 | 含み損益ゾーン、信用圧力タイムライン |
| test_notifier.py | batch/notifier.py | 13 | SNS 通知、Slack/LINE、日次レポート |
| test_storage.py | batch/storage.py + api/storage.py | 15 | S3↔SQLite 同期、SSM 連携 |

#### API レイヤー (HTTP エンドポイント)

| テストファイル | 対象モジュール | テスト数 | 主なテスト内容 |
|---|---|---|---|
| test_backtest.py (一部) | api/routers/backtest.py | — | バックテスト API エンドポイント |
| test_portfolio.py | api/routers/portfolio.py | 17 | ポートフォリオ CRUD、取引管理 |

#### ニュース / 通知レイヤー

| テストファイル | 対象モジュール | テスト数 | 主なテスト内容 |
|---|---|---|---|
| test_rss.py | news/rss.py | 15 | RSS フィード解析、日付処理、画像抽出 |
| test_news_handler.py | news/handler.py | 4 | Lambda ハンドラ、S3 操作 |

### 4.2 フロントエンド テスト一覧

#### View コンポーネント (6/6 = 100%)

| テストファイル | 対象 | テスト数 | 主なテスト内容 |
|---|---|---|---|
| OverviewView.test.ts | OverviewView.vue | 6 | マーケットサマリー表示、API 呼び出し、エラー |
| NetworkView.test.ts | NetworkView.vue | 8 | 資金フロー表示、信用圧力、API 連携 |
| StockView.test.ts | StockView.vue | 6 | 銘柄詳細、ルーティング、期間選択 |
| TimeseriesView.test.ts | TimeseriesView.vue | 7 | 時系列データ、コード入力、テーブル表示 |
| SectorRotationView.test.ts | SectorRotationView.vue | 7 | セクターローテーション、HMM 予測 |
| NewsView.test.ts | NewsView.vue | 8 | ニュース記事表示、フィルタリング、日付選択 |

#### Chart コンポーネント (2/8 = 25%)

| テストファイル | 対象 | テスト数 | 主なテスト内容 |
|---|---|---|---|
| MarketPressureGauge.test.ts | MarketPressureGauge.vue | 13 | ゲージセグメント、ラベル、P/L ゾーン |
| HeatMap.test.ts | HeatMap.vue | 8 | セクターヒートマップ、色マッピング |

---

## 5. テスト未整備の領域

### 5.1 バックエンド — 未テストモジュール

| モジュール | LOC | 優先度 | 理由 |
|---|---|---|---|
| api/routers/network.py | 468 | **高** | 資金フロー API — 複雑なクエリロジック |
| api/routers/sector_rotation.py | 202 | **高** | セクターローテーション API — HMM 連携 |
| batch/sector_rotation.py | — | **高** | Phase 17 セクター分析 — 新機能 |
| api/routers/stock.py | 119 | 中 | 銘柄詳細 API |
| api/routers/us_indices.py | 117 | 中 | 米国指数 API |
| api/routers/news.py | 90 | 中 | ニュース API |
| api/routers/margin.py | 70 | 中 | 信用残 API |
| api/routers/forex.py | 58 | 中 | 為替 API |
| api/routers/prices.py | 41 | 低 | 価格 API (シンプル) |
| api/routers/summary.py | 38 | 低 | サマリー API (シンプル) |
| api/portfolio_storage.py | 145 | 中 | ポートフォリオ DB 直接操作 |
| notification/handler.py | — | 低 | 通知 Lambda (副次的) |
| batch/handler.py | — | 低 | Lambda オーケストレーション (統合テスト向き) |
| config.py | — | 低 | 定数定義のみ |

### 5.2 フロントエンド — 未テストコンポーネント

| コンポーネント | LOC | 優先度 | 理由 |
|---|---|---|---|
| FundFlowTimeline.vue | 533 | **高** | 最大の Chart コンポーネント |
| MarketPressureTimeline.vue | 334 | **高** | 信用圧力タイムライン |
| FundFlowSankey.vue | 202 | 中 | Sankey ダイアグラム |
| SectorReturnHeatmap.vue | 140 | 中 | セクターリターン |
| SectorRotationTimeline.vue | 128 | 中 | ローテーション時系列 |
| PriceChart.vue | 77 | 低 | 価格チャート (Chart.js ラッパー) |
| GraphView.vue | — | 低 | ネットワークグラフ (D3/Cytoscape) |
| useApi.ts | — | **高** | API composable — 全 View から依存 |

---

## 6. テスト改善計画

### Phase 1: API Router テスト追加 (優先度: 高)

FastAPI の `TestClient` を使い、各ルーターのエンドポイントをテストする。

**対象**:
1. `api/routers/network.py` — 資金フロー・ネットワーク関連
2. `api/routers/sector_rotation.py` — セクターローテーション
3. `api/routers/stock.py` — 銘柄詳細

**テスト方針**:
- SQLite を tmp_path に作成し、テストデータを INSERT
- FastAPI app を TestClient でラップ
- 正常系・異常系 (パラメータ不正、データなし) を網羅

```python
# 例: test_router_network.py
from fastapi.testclient import TestClient
from api.main import app

client = TestClient(app)

def test_fund_flow_returns_data(db_with_test_data):
    response = client.get("/api/fund-flow?period=5d")
    assert response.status_code == 200
    data = response.json()
    assert "nodes" in data
    assert "edges" in data
```

### Phase 2: フロントエンド Chart テスト拡充 (優先度: 高)

**対象**:
1. `useApi.ts` — composable の単体テスト
2. `FundFlowTimeline.vue` — props / イベント / 描画ロジック
3. `MarketPressureTimeline.vue` — ゾーン描画・閾値ライン

**テスト方針**:
- Chart.js / D3 の canvas 描画は setup.ts のモックで対応
- props のバリデーション、computed の計算ロジック、emit イベントをテスト
- DOM 構造 (wrapper class, SVG 要素の存在) を検証

```typescript
// 例: FundFlowTimeline.test.ts
import { mount } from '@vue/test-utils'
import FundFlowTimeline from '../FundFlowTimeline.vue'

describe('FundFlowTimeline', () => {
  it('renders timeline with fund flow data', () => {
    const wrapper = mount(FundFlowTimeline, {
      props: { data: mockFundFlowData, period: '5d' }
    })
    expect(wrapper.find('.timeline-container').exists()).toBe(true)
  })

  it('emits period-change on selector click', async () => {
    // ...
  })
})
```

### Phase 3: batch/sector_rotation.py テスト追加 (優先度: 高)

Phase 17 の新機能。HMM モデルによるセクターローテーション分析のテスト。

**テスト方針**:
- テストデータ (セクター別騰落率) を fixture で用意
- HMM の学習・推定・遷移確率の出力を検証
- エッジケース (データ不足、単一セクター) のハンドリング

### Phase 4: E2E テスト導入 (優先度: 中)

Playwright を使ったブラウザ E2E テスト。

**対象ワークフロー**:
1. トップページ表示 → サマリー確認
2. 銘柄検索 → 詳細ページ → チャート表示
3. 資金フローネットワーク → ノードクリック → 詳細遷移
4. セクターローテーション → HMM 予測表示

**テスト方針**:
- API はモックサーバー (MSW) または fixtures で対応
- スクリーンショット比較でビジュアルリグレッション検出
- CI (GitHub Actions) で自動実行

```typescript
// 例: e2e/overview.spec.ts
import { test, expect } from '@playwright/test'

test('overview page shows market summary', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByText('マーケットサマリー')).toBeVisible()
  await expect(page.getByTestId('sector-heatmap')).toBeVisible()
})
```

### Phase 5: 残りの API Router テスト (優先度: 中〜低)

Phase 1 の対象外ルーターを順次テスト追加。

**対象**: forex, margin, news, prices, summary, us_indices

---

## 7. テスト品質基準

### 7.1 新規コードのルール

- **新しいモジュール・コンポーネントには必ずテストを書く**
- **既存コンポーネントを変更した場合、対応するテストも更新する**
- **API エンドポイント追加時は正常系 + エラー系の最低 2 ケース**

### 7.2 テスト命名規則

**バックエンド (pytest)**:
```
test_<対象モジュール>.py
  class Test<機能名>:
    def test_<振る舞い>_<条件>(self):
```

**フロントエンド (vitest)**:
```
<ComponentName>.test.ts
  describe('<ComponentName>', () => {
    it('<振る舞いの説明>', () => { })
  })
```

### 7.3 カバレッジ目標

| レイヤー | 現状 | 目標 |
|---|---|---|
| Backend batch | ~80% | 90% |
| Backend API routers | ~20% | 70% |
| Frontend views | 100% | 100% 維持 |
| Frontend components | 25% | 60% |
| E2E | 0% | 主要フロー 4 本 |

---

## 8. テスト統計サマリー

| 指標 | 数値 |
|---|---|
| バックエンド テストファイル数 | 14 |
| バックエンド テスト関数数 | ~160 |
| バックエンド テスト LOC | ~4,065 |
| フロントエンド テストファイル数 | 8 |
| フロントエンド テストケース数 | ~63 |
| フロントエンド テスト LOC | ~904 |
| **合計テスト LOC** | **~4,969** |
| バックエンド モジュール カバー率 | 13/35 (37%) |
| API ルーター カバー率 | 2/10 (20%) |
| フロントエンド View カバー率 | 6/6 (100%) |
| フロントエンド Component カバー率 | 2/8 (25%) |
| E2E テスト | 0 |
