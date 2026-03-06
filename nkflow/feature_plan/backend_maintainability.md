# Backend 共通化・メンテナンス性改善計画

> 最終更新: 2026-03-05

## Context

バックエンド (API routers 14ファイル, batch modules 15ファイル) を調査した結果、以下の技術的負債を確認:
- bare `except Exception` による silent failure (デバッグ困難)
- 同一パターンの重複 (stock validation, JSON parsing, Yahoo Finance fetch, DuckDB ATTACH)
- 分析パラメータの散在 (config.py に集約されていない)

既に良い設計: API storage の DI + TTL キャッシュ、batch/API のレイヤー分離、moto テスト基盤

---

## Phase 1: Error Handling 修正 (高優先・低リスク)

### Task 1.1: bare `except Exception` を具体的な例外に絞る
- **対象**: `api/routers/td_sequential.py`, `api/routers/fear_indices.py`, `api/routers/sector_rotation.py`
- **変更**: `except Exception` → `except sqlite3.OperationalError` (テーブル未作成ケース) + `logger.warning`
- **LOC**: ~40行

### Task 1.2: td_sequential.py の stock validation 重複を解消
- **対象**: `api/routers/td_sequential.py` (lines 28-32, 64-68)
- **変更**: ローカルヘルパー `_validate_stock(conn, code)` に抽出
- **LOC**: ~15行 (純減)

---

## Phase 2: 共通 API ヘルパーモジュール作成 (高優先・低リスク)

### Task 2.1: `api/helpers.py` 新規作成
- `require_stock(conn, code)` — 銘柄存在チェック + 404 (td_sequential x2, stock x1 で重複)
- `safe_json_loads(raw, default=None)` — JSON parse + error handling (summary, stock, sector_rotation で 3-4 パターン重複)
- `period_sql_expr(granularity)` — `strftime('%Y-W%W', date)` / `strftime('%Y-%m', date)` + validation (network, us_indices で重複)
- **LOC**: ~50行 (新規)

### Task 2.2: 各 router で helpers を利用
- **対象**: `td_sequential.py`, `stock.py`, `summary.py`, `sector_rotation.py`, `network.py`, `us_indices.py`
- **LOC**: ~50行純減

---

## Phase 3: Yahoo Finance fetch 統合 (高優先・低リスク)

### Task 3.1: `_fetch_fx_ohlcv` と `_fetch_index_ohlcv` を統合
- **対象**: `batch/fetch_external.py` (lines 32-68, 214-258)
- **変更**: `_fetch_yahoo_ohlcv(symbol, days=None, start_date=None, include_volume=False)` に統一
- **差分**: 同一の Yahoo Finance JSON パース処理が2関数に分散 → 1関数に集約
- **LOC**: ~60行削除, ~50行追加 (純減 ~10行)
- **テスト**: `test_fetch_external.py`, `test_fetch_us_indices.py` で検証

---

## Phase 4: 分析パラメータを config.py に集約 (中優先・低リスク)

### Task 4.1: statistics.py のモジュール定数を config.py に移動
- `GRANGER_WINDOW`, `LEAD_LAG_MAX`, `FUND_FLOW_WINDOW`, `REGIME_SHORT_WINDOW`, `REGIME_LONG_WINDOW`, `MAX_GRANGER_STOCKS`
- config.py に既存の `GRANGER_MAX_LAG`, `GRANGER_P_THRESHOLD` と統合
- **LOC**: ~25行

---

## Phase 5: DuckDB 接続ヘルパー (中優先・低リスク)

### Task 5.1: `batch/db.py` に context manager を作成
```python
@contextmanager
def duckdb_sqlite(db_path: str, alias: str = "sq"):
    duck = duckdb.connect()
    duck.execute(f"ATTACH '{db_path}' AS {alias} (TYPE SQLITE)")
    try:
        yield duck
    finally:
        duck.close()
```
- **対象消費者**: `compute.py`, `signals.py` (4箇所の ATTACH パターンを置換)
- **効果**: リソース解放の確実化 (現状は例外時に `duck.close()` が呼ばれないパスがある)
- **LOC**: ~25行新規, ~16行削除

---

## Phase 6: テスト追加

### Task 6.1: `tests/test_api_helpers.py` 新規作成
- `require_stock`, `safe_json_loads`, `period_sql_expr` のユニットテスト
- **LOC**: ~60行

### Task 6.2: `tests/test_batch_db.py` 新規作成
- `duckdb_sqlite` context manager のテスト
- **LOC**: ~30行

---

## 見送り事項 (過剰設計のため)

| 候補 | 見送り理由 |
|------|-----------|
| 全 router に Pydantic response model | 14 router への大量作業、内部 API では `dict(row)` で十分 |
| Enum validation for string params | `Query(pattern=...)` で既に対応可能、スタイルの問題 |
| 抽象 storage base class | API/batch の storage は役割が根本的に異なる |
| 汎用 INSERT OR REPLACE ヘルパー | テーブル・カラム数が全て異なり、汎用化すると ORM 的な複雑さが増す |
| 共通 date/timezone ユーティリティ | 重複箇所が 2-3 箇所のみで抽出効果が薄い |

---

## 実装順序

```
Phase 1 (Task 1.1, 1.2) → Phase 2 (Task 2.1, 2.2) → Phase 3 (Task 3.1)
                                                     → Phase 4 (Task 4.1)
                                                     → Phase 5 (Task 5.1)
                                                     → Phase 6 (Task 6.1, 6.2)
```

合計: **8 コミット**, 純変更量 **~350行**, 全て backend レイヤーのみ

---

## 検証方法

各コミット後:
```bash
make test           # バックエンド pytest 全件パス
make lint           # ruff チェック
```

全 Phase 完了後に Playwright で主要画面の動作確認

---

## 調査で確認した主な重複・問題箇所

### API Routers

| 問題 | ファイル | 行 | 重複回数 |
|------|---------|-----|---------|
| bare `except Exception` | td_sequential.py, fear_indices.py, sector_rotation.py | 各所 | 5箇所 |
| stock validation 重複 | td_sequential.py | 28-32, 64-68 | 2箇所 |
| JSON parse パターン乱立 | summary.py, stock.py, sector_rotation.py, portfolio.py | 各所 | 4パターン |
| period 式重複 | network.py (134-136, 216-218), us_indices.py (231-233) | — | 3箇所 |
| "latest date" subquery 重複 | network.py, sector_rotation.py, us_indices.py, ytd_highs.py | — | 8箇所+ |

### Batch Modules

| 問題 | ファイル | 重複回数 |
|------|---------|---------|
| Yahoo Finance parse 重複 | fetch_external.py (_fetch_fx_ohlcv, _fetch_index_ohlcv) | 2関数 |
| DuckDB ATTACH パターン | compute.py, signals.py | 4箇所 |
| INSERT OR REPLACE ボイラープレート | 7モジュール | 15箇所+ |
| DataFrame → SQL conversion | 5モジュール | 12箇所+ |
| 分析パラメータ散在 | statistics.py, signals.py, sector_rotation.py | ~30定数 |
