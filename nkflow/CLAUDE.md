# nkflow — 日経225 投資分析基盤

Product-specific instructions for the nkflow application.

---

## Commands

### Backend (Python — API サーバー)

```bash
cd nkflow/backend

# 依存関係インストール (初回 / pyproject.toml 変更後)
uv pip install -e ".[dev]"

# テスト全件
.venv/bin/python -m pytest tests/ -v

# 単一テストファイル
.venv/bin/python -m pytest tests/test_signals.py -v

# Lint
.venv/bin/ruff check src/ tests/
```

### CDK (TypeScript)

```bash
cd nkflow/cdk

npm ci                          # 依存インストール
npm run build                   # TypeScript コンパイル
npx cdk diff NkflowStack        # 変更差分確認
npx cdk deploy NkflowStack --require-approval never
```

### Frontend (Vue SPA)

> **重要: フロントエンドは CDK deploy と独立しており、自動デプロイされない。**
> `nkflow/frontend/` を変更したら必ず `make deploy-frontend` を実行すること。

```bash
make deploy-frontend   # ビルド + S3 sync (これだけでOK)
```

### GitHub Actions

- `main` への push (`nkflow/cdk/`, `nkflow/backend/`, `datalake/` 変更) で自動デプロイ
- **frontend/ の変更は GitHub Actions 対象外** — `make deploy-frontend` が必要
- 手動実行: GitHub Actions → Deploy CDK → Run workflow

---

## Architecture

### 全体構成

```
EventBridge Scheduler
    │ 毎営業日 JST 18:00
    ▼
Lambda: nkflow-batch          ← datalake/Dockerfile.batch
    │ 1. SSM → J-Quants APIキー
    │ 2. S3 → /tmp/stocks.db + /tmp/kuzu_db/
    │ 3. J-Quants OHLCV fetch
    │ 3.5 Yahoo Finance FX + J-Quants 信用残
    │ 4. DuckDB 騰落率・相関計算
    │ 5. statsmodels グレンジャー因果・リードラグ
    │ 6. KùzuDB グラフ更新・探索
    │ 7. シグナル生成
    │ 8. /tmp → S3 (finally で必ず実行)
    └──► SNS → 通知 Lambda (Slack/LINE)

API Gateway (prod)
    │ /api/* → Lambda Function URL
    ▼
Lambda: nkflow-api             ← nkflow/backend/Dockerfile.api
    │ FastAPI + Mangum
    │ cold start: S3 → /tmp/stocks.db (1時間 TTL キャッシュ)
    │ 書き込み: S3 download → write → commit → S3 upload
    └──► S3: frontend/index.html (SPA フォールバック)
```

### データフロー (S3 キー)

| S3 キー | 用途 | アクセス |
|---|---|---|
| `data/stocks.db` | メイン SQLite (OHLCV・分析結果) | バッチ: 読み書き / API: 読み取り専用 |
| `data/kuzu_db.tar.gz` | KùzuDB グラフDB | バッチのみ |
| `data/portfolio.db` | ポートフォリオ (Phase 15) | API: 読み書き |
| `frontend/` | Vue SPA 静的ファイル | API Lambda 経由で配信 |

### モジュール構成

```
datalake/src/                          # データパイプライン (バッチ処理) ※リポジトリルートの共有モジュール
├── config.py                          # 環境変数・定数 (バッチ用)
├── db.py                              # DuckDB ユーティリティ
├── pipeline/
│   ├── handler.py                     # Lambda エントリポイント (バッチオーケストレーション)
│   └── storage.py                     # S3↔/tmp 同期 + SSM 認証
├── ingestion/
│   ├── jquants.py                     # J-Quants OHLCV + 銘柄マスタ取得
│   ├── yahoo_finance.py               # Yahoo Finance FX・VIX・米国指数・信用残高
│   └── news.py                        # ニュース正規化
├── transform/
│   ├── compute.py                     # DuckDB 騰落率・相関計算
│   ├── statistics.py                  # グレンジャー因果・リードラグ・資金フロー
│   ├── sector_rotation.py             # セクターローテーション HMM
│   ├── td_sequential.py               # TD Sequential
│   └── news_enrichment.py             # ニュース翻訳・分類
├── graph/
│   └── kuzu.py                        # KùzuDB グラフ更新・探索
├── signals/
│   └── generator.py                   # シグナル生成 (mega_trend_follow)
├── notification/
│   ├── notifier.py                    # SNS 日次レポート
│   └── handler.py                     # 通知 Lambda ハンドラ
├── news/
│   ├── rss.py                         # RSS フィード解析
│   └── handler.py                     # ニュース Lambda ハンドラ
└── backtest/
    └── engine.py                      # バックテストエンジン

nkflow/backend/src/                    # API サーバー (FastAPI)
├── config.py                          # API 用設定 (最小限)
└── api/
    ├── handler.py                     # Mangum(app)
    ├── main.py                        # FastAPI + ルーター登録 + フロントエンド配信
    ├── storage.py                     # stocks.db 読み取り専用接続 (10分 TTL)
    ├── portfolio_storage.py           # portfolio.db 読み書き
    └── routers/                       # summary / prices / signals / network / stock /
                                       # accuracy / forex / margin / backtest / portfolio
```

### CDK スタック (NkflowStack)

リージョン: `ap-northeast-1`。主要リソース:
- S3 Bucket: `nkflow-data-{account}` (RETAIN)
- Lambda Batch: メモリ 2048MB・タイムアウト 900秒・エフェメラル 2048MB
- Lambda API: メモリ 512MB・タイムアウト 30秒・Function URL (CORS `*`)
- API Gateway REST API: `nkflow` (prod ステージ)
- EventBridge Scheduler: `cron(0 9 ? * MON-FRI *)` UTC
- SSM: `/nkflow/jquants-api-key` (PLACEHOLDER → 手動で SecureString に変更)

### テスト

- テストフレームワーク: pytest + moto (S3/SSM/SNS モック)
- `conftest.py` が `S3_BUCKET=test-nkflow-bucket` 等のダミー環境変数を自動設定
- 実 AWS アクセスなし。全テストはローカルで完結

### SQLite 並列実行の安全ルール

Worktree ごとに `SQLITE_PATH` が自動で分離される（`/tmp/nkflow-<worktree名>/stocks.db`）。
ただし以下のルールを守ること:

* `make push-db` は排他的に実行する — 同時に複数セッションで実行しない
* DB スキーマ変更（マイグレーション）を含むタスクは並列実行しない
* バックフィルスクリプト実行中は他セッションで同じ DB を操作しない
* `make push-db` 実行前に、他セッションが S3 上の DB を更新していないか確認する
* テスト (`make test`) は pytest `tmp_path` で隔離されるため並列実行しても安全

#### WAL (Write-Ahead Log) の注意

SQLite はデフォルトで WAL モードで動作する。バックフィル等でデータを書き込んだ後、
WAL ファイル (`stocks.db-wal`) に変更が残った状態で `aws s3 cp` するとメインDBファイルのみが
アップロードされ、変更が S3 に反映されない。

**`make push-db` は内部で `PRAGMA wal_checkpoint(TRUNCATE)` を実行してから S3 にアップロードするため、
直接 `aws s3 cp` を使わず必ず `make push-db` を使うこと。**

### スキーマ変更時

`nkflow/backend/scripts/migrate_phaseXX.py` を作成して冪等なマイグレーションを実装する。
`_download_sqlite` / `_init_sqlite_schema` が初回実行時に `scripts/init_sqlite.py` を呼ぶ。

---

## ER
@docs/er_diagram.md

## 画面設計書
@docs/screen_design.md

## テスト設計書
@docs/test_design.md

## API リファレンス
@docs/api_reference.md

### 設計書の更新ルール

**以下のファイルを変更したとき、必ず対応する設計書も更新すること。**

| 変更ファイル | 更新すべき設計書 |
|---|---|
| `nkflow/backend/src/batch/statistics.py` (資金フロー部分) | `nkflow/docs/fund_flow_dashboard.md` § 3.1 |
| `nkflow/backend/src/api/routers/network.py` | `nkflow/docs/fund_flow_dashboard.md` § 3.2 |
| `nkflow/frontend/src/views/NetworkView.vue` | `nkflow/docs/fund_flow_dashboard.md` § 4.1 |
| `nkflow/frontend/src/components/charts/FundFlowTimeline.vue` | `nkflow/docs/fund_flow_dashboard.md` § 4.2 |
| `nkflow/frontend/src/components/charts/FundFlowSankey.vue` | `nkflow/docs/fund_flow_dashboard.md` § 4.3 |
| `nkflow/frontend/src/types/index.ts` (FundFlow系型) | `nkflow/docs/fund_flow_dashboard.md` § 5 |
| `nkflow/frontend/src/composables/useApi.ts` (FundFlow系) | `nkflow/docs/fund_flow_dashboard.md` § 8 |

**更新手順**:
1. 変更内容を実装する
2. 対応する設計書の該当セクションを修正する
3. 設計書末尾の「最終更新」日付を更新する
4. 両方をまとめて1コミットにする (レイヤー分離の原則は守りつつ、ドキュメントは実装と同一コミットで可)
