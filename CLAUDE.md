# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Agent behavior policy is defined in `.claude/CLAUDE.md` — read it first.

---

## Commands

### Makefile (推奨: 全コマンドはここから実行)

```bash
make help            # 利用可能なコマンド一覧
make deploy          # CDK + frontend を両方デプロイ (通常はこれ)
make deploy-cdk      # CDK のみ (backend/Lambda/インフラ変更時)
make deploy-frontend # Vue frontend のみビルド&S3同期
make pull            # S3 → stocks.db ダウンロード (worktree 対応)
make push-db         # stocks.db → S3 アップロード (worktree 対応)
make test            # pytest
make test-frontend   # vitest
make lint            # ruff
```

### Backend (Python)

```bash
cd backend

# 依存関係インストール (初回 / pyproject.toml 変更後)
uv pip install -e ".[dev]"

# テスト全件
.venv/bin/python -m pytest tests/ -v

# 単一テストファイル
.venv/bin/python -m pytest tests/test_signals.py -v

# 単一テスト関数
.venv/bin/python -m pytest tests/test_signals.py::test_generate_causality_chain -v

# Lint
.venv/bin/ruff check src/ tests/
```

### CDK (TypeScript)

```bash
cd cdk

npm ci                          # 依存インストール
npm run build                   # TypeScript コンパイル
npx cdk diff NkflowStack        # 変更差分確認
npx cdk deploy NkflowStack --require-approval never
```

### Frontend (Vue SPA)

> **重要: フロントエンドは CDK deploy と独立しており、自動デプロイされない。**
> `frontend/` を変更したら必ず `make deploy-frontend` を実行すること。

```bash
make deploy-frontend   # ビルド + S3 sync (これだけでOK)
```

### GitHub Actions

- `main` への push (cdk/ または backend/ 変更) で自動デプロイ
- **frontend/ の変更は GitHub Actions 対象外** — `make deploy-frontend` が必要
- 手動実行: GitHub Actions → Deploy CDK → Run workflow

---

## Architecture

### 全体構成

```
EventBridge Scheduler
    │ 毎営業日 JST 18:00
    ▼
Lambda: nkflow-batch          ← Dockerfile.batch
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
Lambda: nkflow-api             ← Dockerfile.api
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

### バックエンド モジュール構成

```
backend/src/
├── config.py               # 環境変数・定数 (S3_BUCKET は必須)
├── batch/
│   ├── handler.py          # Lambda エントリポイント (8ステップ逐次実行)
│   ├── storage.py          # S3↔/tmp 同期 + SSM 認証
│   ├── fetch.py            # J-Quants OHLCV 取得
│   ├── fetch_external.py   # Yahoo Finance FX + J-Quants 信用残
│   ├── compute.py          # DuckDB 騰落率・相関
│   ├── statistics.py       # グレンジャー因果・リードラグ・資金フロー
│   ├── graph.py            # KùzuDB グラフ更新・探索
│   ├── signals.py          # シグナル生成 (causality_chain / cluster_breakout / margin_squeeze / yen_sensitivity)
│   ├── tracker.py          # シグナル的中率追跡 (Phase 11)
│   └── notifier.py         # SNS 日次レポート (Phase 12)
└── api/
    ├── handler.py          # Mangum(app)
    ├── main.py             # FastAPI + ルーター登録 + フロントエンド配信
    ├── storage.py          # stocks.db 読み取り専用接続 (1時間 TTL)
    ├── portfolio_storage.py # portfolio.db 読み書き (writable_portfolio_connection)
    └── routers/            # summary / prices / signals / network / stock /
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

### スキーマ変更時

`backend/scripts/migrate_phaseXX.py` を作成して冪等なマイグレーションを実装する。
`_download_sqlite` / `_init_sqlite_schema` が初回実行時に `scripts/init_sqlite.py` を呼ぶ。

---

## Design Documents

`docs/` 配下に機能ごとの設計書がある。

| ファイル | 対象機能 |
|---|---|
| `docs/spec.md` | プロジェクト全体設計 (Source of truth) |
| `docs/migration_plan.md` | GCP→AWS 移行計画 |
| `docs/fund_flow_dashboard.md` | 資金フローダッシュボード (NetworkView / FundFlowTimeline / FundFlowSankey) |

### 設計書の更新ルール

**以下のファイルを変更したとき、必ず対応する設計書も更新すること。**

| 変更ファイル | 更新すべき設計書 |
|---|---|
| `backend/src/batch/statistics.py` (資金フロー部分) | `docs/fund_flow_dashboard.md` § 3.1 |
| `backend/src/api/routers/network.py` | `docs/fund_flow_dashboard.md` § 3.2 |
| `frontend/src/views/NetworkView.vue` | `docs/fund_flow_dashboard.md` § 4.1 |
| `frontend/src/components/charts/FundFlowTimeline.vue` | `docs/fund_flow_dashboard.md` § 4.2 |
| `frontend/src/components/charts/FundFlowSankey.vue` | `docs/fund_flow_dashboard.md` § 4.3 |
| `frontend/src/types/index.ts` (FundFlow系型) | `docs/fund_flow_dashboard.md` § 5 |
| `frontend/src/composables/useApi.ts` (FundFlow系) | `docs/fund_flow_dashboard.md` § 8 |

**更新手順**:
1. 変更内容を実装する
2. 対応する設計書の該当セクションを修正する
3. 設計書末尾の「最終更新」日付を更新する
4. 両方をまとめて1コミットにする (レイヤー分離の原則は守りつつ、ドキュメントは実装と同一コミットで可)
