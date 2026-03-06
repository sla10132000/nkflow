# HazardBrief テスト設計書

> 最終更新: 2026-03-06

---

## 1. テスト戦略

### 1.1 テストピラミッド

```
        ╱  E2E  ╲          ← Playwright (未整備)
       ╱─────────╲
      ╱ Integration╲       ← API Router テスト (pytest + TestClient)
     ╱───────────────╲
    ╱   Unit Tests     ╲   ← pytest (backend) / vitest (frontend)
   ╱─────────────────────╲
```

### 1.2 テスト方針

- **外部 API は必ずモック** — 国交省API・国土地理院API への実際のリクエストは行わない
- **SQLite は tmp_path で隔離** — テスト間の干渉なし
- **ハザードデータの並列取得は asyncio.gather** で検証
- **graceful degradation を必ず検証** — 個別の外部API失敗でもシステムが動作することを確認

---

## 2. バックエンドテスト

### 2.1 テスト対象

| テストファイル | 対象 | 主なテスト内容 |
|---|---|---|
| `test_properties.py` | `routers/properties.py` | 物件CRUD、ジオコーディング失敗時のフォールバック |
| `test_hazard.py` | `routers/hazard.py`, `routers/report.py` | ハザードデータ取得、キャッシュ、レポート生成 |

### 2.2 テストケース: 物件API

| テスト | 内容 |
|---|---|
| `test_returns_empty_list_when_no_properties` | 物件なしで空リスト |
| `test_returns_properties` | 登録済み物件を返す |
| `test_filter_by_company_id` | company_id フィルタ |
| `test_create_property_with_geocoding` | ジオコーディング成功時の登録 |
| `test_create_property_without_geocoding_failure` | ジオコーディング失敗でも登録可能 |
| `test_create_property_with_manual_coordinates` | 手動座標指定 |
| `test_delete_existing_property` | 物件削除 |
| `test_delete_nonexistent_returns_404` | 存在しない物件の削除 |

### 2.3 テストケース: ハザードAPI

| テスト | 内容 |
|---|---|
| `test_returns_404_for_nonexistent_property` | 存在しない物件 |
| `test_returns_422_when_no_coordinates` | 緯度経度なし |
| `test_fetches_hazard_data_from_external_api` | 外部API呼び出しと結果返却 |
| `test_returns_cached_data_on_second_request` | キャッシュヒット (外部API 1回のみ) |
| `test_force_refresh_bypasses_cache` | force_refresh でキャッシュバイパス |
| `test_returns_404_when_no_hazard_report` | レポートなし |
| `test_returns_report_when_hazard_data_exists` | レポート生成 |

---

## 3. フロントエンドテスト

### 3.1 テスト対象

| テストファイル | 対象 | テスト数 |
|---|---|---|
| `DashboardView.test.ts` | DashboardView.vue | 4 |
| `RiskSummaryCard.test.ts` | RiskSummaryCard.vue | 6 |

### 3.2 モック戦略

- `@auth0/auth0-vue`: `vi.mock` で `isAuthenticated = true` を返す
- `../composables/useApi`: `mockUseApi` でAPIレスポンスをモック
- `HazardMap.vue`: Leaflet は happy-dom 非対応のため `div` スタブ

### 3.3 テストケース: RiskSummaryCard

| テスト | 内容 |
|---|---|
| タイトル表示 | リスクタイプのタイトルが表示される |
| レベルラベル表示 | 低/中/高/要確認のバッジが表示される |
| 説明文表示 | description テキストが表示される |
| 対策ヒント表示 | mitigation テキストが表示される |
| データ取得不可の警告 | available=false で警告文を表示 |
| low → 緑スタイル | risk-low クラスが適用される |
| high → オレンジスタイル | risk-high クラスが適用される |

---

## 4. テスト未整備の領域

| 対象 | 優先度 | 備考 |
|---|---|---|
| `lib/hazard/__init__.py` | 高 | asyncio.gather の並列取得、例外ハンドリング |
| `lib/hazard/flood.py` | 高 | 外部API モック、レスポンス解析 |
| `lib/hazard/geocoding.py` | 高 | 住所→座標変換 |
| `PropertyNewView.vue` | 中 | フォーム入力、デバウンス、ジオコーディング |
| `PropertyDetailView.vue` | 中 | レポート表示、タブ切り替え |
| E2E テスト | 低 | 主要フロー 3本 |

---

## 5. 実行方法

### バックエンド

```bash
cd hazardbrief/backend
# 依存インストール
uv pip install -e ".[dev]"
# テスト実行
.venv/bin/python -m pytest tests/ -v
```

### フロントエンド

```bash
cd hazardbrief/frontend
npm install
npx vitest run
```

---

## 6. カバレッジ目標

| レイヤー | 現状 | 目標 |
|---|---|---|
| Backend API routers | ~60% | 80% |
| Backend hazard lib | 0% | 70% |
| Frontend views | ~20% | 60% |
| Frontend components | ~40% | 70% |
| E2E | 0% | 主要3フロー |
