# Chart.js 共通設定の整理 (Task #7)

## 背景

現在、各チャートコンポーネントで Chart.js のプラグイン登録・オプション構築が重複している。
共通設定を `composables/useChartDefaults.ts` に集約する。

## 対象ファイル

チャートコンポーネント (要調査: 各ファイルの Chart.js 設定を確認):

- `frontend/src/components/charts/PriceChart.vue`
- `frontend/src/components/charts/HeatMap.vue`
- `frontend/src/components/charts/NikkeiAreaChart.vue`
- `frontend/src/components/charts/SectorTrendBar.vue`
- `frontend/src/components/charts/FundFlowTimeline.vue`
- `frontend/src/components/charts/FundFlowSankey.vue`
- `frontend/src/components/charts/MarketPressureGauge.vue`
- `frontend/src/components/charts/MarketPressureTimeline.vue`
- `frontend/src/components/charts/SectorReturnHeatmap.vue`
- `frontend/src/components/charts/SectorRotationTimeline.vue`

## 作成するファイル

```
frontend/src/composables/useChartDefaults.ts
```

## 実装方針

### 1. 共通プラグイン登録の一元化

各コンポーネントで個別に行っている `Chart.register(...)` を1箇所にまとめる。

```typescript
// useChartDefaults.ts
import {
  Chart,
  CategoryScale, LinearScale, TimeScale,
  BarElement, LineElement, PointElement,
  BarController, LineController,
  Tooltip, Legend, Filler,
} from "chart.js";

let registered = false;

export function registerChartPlugins() {
  if (registered) return;
  Chart.register(
    CategoryScale, LinearScale, TimeScale,
    BarElement, LineElement, PointElement,
    BarController, LineController,
    Tooltip, Legend, Filler,
  );
  registered = true;
}
```

### 2. 共通オプションビルダー

```typescript
export function baseChartOptions(overrides?: Partial<ChartOptions>): ChartOptions {
  return {
    responsive: true,
    maintainAspectRatio: false,
    animation: { duration: 0 },
    plugins: {
      legend: { display: false },
      tooltip: { ... },
    },
    scales: { ... },
    ...overrides,
  };
}
```

### 3. 共通カラーパレット

チャート用の色定数 (セクター色、ゾーン色など) を `utils/colors.ts` に既にある定数と統合。

### 4. 各コンポーネントの修正

各チャートコンポーネントから:
- `Chart.register(...)` 呼び出しを削除
- `registerChartPlugins()` を1回呼ぶように変更
- 共通オプションを `baseChartOptions()` から生成してオーバーライド

## 実施手順

1. 各チャートコンポーネントの Chart.js 設定を調査・比較
2. `useChartDefaults.ts` を作成 (プラグイン登録 + 共通オプション)
3. 各コンポーネントを順次修正 (1コンポーネントずつ)
4. テスト実行・lint 確認
5. Playwright で各画面のチャート表示を確認

## 注意事項

- チャートごとに必要なプラグインが異なる場合がある (Sankey, Gauge 等)
- lightweight-charts (TradingView) を使っているコンポーネントは対象外
- 既存テストへの影響を最小限にする
