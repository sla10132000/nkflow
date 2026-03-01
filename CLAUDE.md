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
make pull            # S3 → /tmp/stocks.db ダウンロード
make push-db         # /tmp/stocks.db → S3 アップロード
make test            # pytest
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

### スキーマ変更時

`backend/scripts/migrate_phaseXX.py` を作成して冪等なマイグレーションを実装する。
`_download_sqlite` / `_init_sqlite_schema` が初回実行時に `scripts/init_sqlite.py` を呼ぶ。
