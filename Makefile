ACCOUNT := $(shell aws sts get-caller-identity --query Account --output text 2>/dev/null || echo "000000000000")
S3_BUCKET := nkflow-data-$(ACCOUNT)
S3_BUCKET_DEV := nkflow-data-dev-$(ACCOUNT)
HB_S3_BUCKET := hazardbrief-data-$(ACCOUNT)

.PHONY: help \
        install install-backend install-datalake install-frontend install-cdk \
        dev \
        test test-datalake test-frontend lint lint-datalake lint-frontend \
        build build-frontend build-cdk \
        diff diff-dev deploy deploy-cdk deploy-frontend \
        deploy-dev deploy-prod \
        deploy-cdk-dev deploy-cdk-prod \
        deploy-frontend-dev deploy-frontend-prod \
        sync-db-to-dev \
        pull push push-db \
        migrate \
        deploy-hazardbrief deploy-hazardbrief-cdk deploy-hazardbrief-frontend \
        test-hazardbrief-backend test-hazardbrief-frontend \
        install-hazardbrief

# デフォルトターゲット
help:
	@echo "Usage: make <target>"
	@echo ""
	@echo "--- Install ---"
	@echo "  install            全レイヤーの依存関係をインストール"
	@echo "  install-backend    backend (API): uv pip install -e .[dev]"
	@echo "  install-datalake   datalake (バッチ): uv pip install -e .[dev]"
	@echo "  install-frontend   frontend: npm install"
	@echo "  install-cdk        cdk: npm ci"
	@echo ""
	@echo "--- Dev ---"
	@echo "  dev                フロントエンド開発サーバー起動 (vite, :5173)"
	@echo "  dev-api            バックエンド開発サーバー起動 (uvicorn, :8001)"
	@echo "                     ※ 事前に make pull で stocks.db を取得すること"
	@echo ""
	@echo "--- Test / Lint ---"
	@echo "  test               backend + datalake pytest"
	@echo "  test-datalake      datalake pytest のみ"
	@echo "  test-frontend      frontend vitest"
	@echo "  lint               backend + datalake ruff"
	@echo "  lint-datalake      datalake ruff のみ"
	@echo "  lint-frontend      frontend biome check"
	@echo ""
	@echo "--- Build ---"
	@echo "  build              frontend + cdk をビルド"
	@echo "  build-frontend     vue-tsc && vite build"
	@echo "  build-cdk          tsc (CDK TypeScript コンパイル)"
	@echo ""
	@echo "--- Deploy ---"
	@echo "  deploy-dev         dev 環境に CDK + frontend をデプロイ"
	@echo "  deploy-prod        prod 環境に CDK + frontend をデプロイ"
	@echo "  deploy             deploy-prod のエイリアス (後方互換)"
	@echo "  deploy-cdk         CDK のみ prod デプロイ (後方互換)"
	@echo "  deploy-frontend    frontend のみ prod デプロイ (後方互換)"
	@echo "  diff               cdk diff NkflowStack-prod"
	@echo "  diff-dev           cdk diff NkflowStack-dev"
	@echo ""
	@echo "--- DB ---"
	@echo "  sync-db-to-dev     prod DB を dev バケットにコピー (初回 / リフレッシュ時)"
	@echo ""
	@echo "--- Git ---"
	@echo "  push               git push origin main (GitHub Actions deploy をトリガー)"
	@echo ""
	@echo "--- DB ---"
	@echo "  pull               S3 から stocks.db をダウンロード (worktree 対応)"
	@echo "  push-db            stocks.db を S3 へアップロード (worktree 対応)"

# -----------------------------------------------------------------------
# Install
# -----------------------------------------------------------------------

install: install-backend install-datalake install-frontend install-cdk

install-backend:
	cd nkflow/backend && uv pip install -e ".[dev]"

install-datalake:
	cd datalake && uv venv .venv --python 3.12 && uv pip install -e ".[dev]"

install-frontend:
	cd nkflow/frontend && npm install

install-cdk:
	cd nkflow/cdk && npm ci

# -----------------------------------------------------------------------
# Dev server
# -----------------------------------------------------------------------

dev:
	cd nkflow/frontend && npm run dev

# バックエンド開発サーバー (S3_BUCKET 未設定 = ローカルファイルモード)
# 事前に: make pull  (stocks.db をS3からダウンロード)
dev-api:
	cd nkflow/backend && SQLITE_PATH=$(SQLITE_LOCAL) .venv/bin/uvicorn src.api.main:app --host 127.0.0.1 --port 8001 --reload

# -----------------------------------------------------------------------
# Test / Lint
# -----------------------------------------------------------------------

test:
	cd nkflow/backend && .venv/bin/python -m pytest tests/ -v
	cd datalake && .venv/bin/python -m pytest tests/ -v

test-datalake:
	cd datalake && .venv/bin/python -m pytest tests/ -v

test-frontend:
	cd nkflow/frontend && npm test

lint:
	cd nkflow/backend && .venv/bin/ruff check src/ tests/
	cd datalake && .venv/bin/ruff check src/ tests/ scripts/

lint-datalake:
	cd datalake && .venv/bin/ruff check src/ tests/ scripts/

lint-frontend:
	cd nkflow/frontend && npm run lint

# -----------------------------------------------------------------------
# Build
# -----------------------------------------------------------------------

build: build-frontend build-cdk

build-frontend:
	cd nkflow/frontend && npm run build

build-cdk:
	cd nkflow/cdk && npm run build

# -----------------------------------------------------------------------
# CDK / Deploy
# -----------------------------------------------------------------------

diff: build-cdk
	cd nkflow/cdk && npx cdk diff NkflowStack-prod -c env=prod

diff-dev: build-cdk
	cd nkflow/cdk && npx cdk diff NkflowStack-dev -c env=dev

# ── dev 環境デプロイ ──────────────────────────────────────────────
deploy-dev: deploy-cdk-dev deploy-frontend-dev

deploy-cdk-dev: build-cdk
	cd nkflow/cdk && npx cdk deploy NkflowStack-dev -c env=dev --require-approval never

deploy-frontend-dev:
	cd nkflow/frontend && npm run build -- --mode development
	aws s3 sync nkflow/frontend/dist/ s3://$(S3_BUCKET_DEV)/frontend/ --delete

# ── prod 環境デプロイ ─────────────────────────────────────────────
deploy-prod: deploy-cdk-prod deploy-frontend-prod

deploy-cdk-prod: build-cdk
	cd nkflow/cdk && npx cdk deploy NkflowStack-prod -c env=prod --require-approval never

deploy-frontend-prod:
	cd nkflow/frontend && npm run build
	aws s3 sync nkflow/frontend/dist/ s3://$(S3_BUCKET)/frontend/ --delete

# ── 後方互換エイリアス ────────────────────────────────────────────
# CDK + frontend を両方デプロイ (通常はこれを使う → deploy-prod のエイリアス)
deploy: deploy-prod

# CDK のみ (backend/Lambda/インフラ変更時) → prod
deploy-cdk: deploy-cdk-prod

# frontend のみ: ビルドして S3 へ同期 → prod
# ⚠️ GitHub Actions は frontend/ を自動デプロイしない — Vue 変更後は必ずこれを実行
deploy-frontend: deploy-frontend-prod

# -----------------------------------------------------------------------
# Git
# -----------------------------------------------------------------------

# git push → GitHub Actions が CDK deploy を自動実行 (frontend は含まない)
# ⚠️ frontend 変更時は push 後に make deploy-frontend も実行すること
push:
	git push origin main

# -----------------------------------------------------------------------
# DB (SQLite)
# Worktree 内では /tmp/nkflow-<name>/stocks.db に分離される
# -----------------------------------------------------------------------

# Worktree 検出: .claude/worktrees/<name>/ 配下なら分離パスを使う
_WT_MARKER := /.claude/worktrees/
_WT_NAME := $(if $(findstring $(_WT_MARKER),$(CURDIR)),$(word 1,$(subst /, ,$(lastword $(subst $(_WT_MARKER), ,$(CURDIR))))))
SQLITE_LOCAL := $(if $(_WT_NAME),/tmp/nkflow-$(_WT_NAME)/stocks.db,/tmp/stocks.db)

# S3 から SQLite をダウンロード (ローカル分析用)
pull:
	@mkdir -p $(dir $(SQLITE_LOCAL))
	aws s3 cp s3://$(S3_BUCKET)/data/stocks.db $(SQLITE_LOCAL)
	@echo "Downloaded to: $(SQLITE_LOCAL)"

# SQLite を S3 へアップロード (バックフィル後など)
# WAL チェックポイントを先に実行し、WAL の変更をメイン DB ファイルに書き込んでからアップロードする
push-db:
	sqlite3 $(SQLITE_LOCAL) "PRAGMA wal_checkpoint(TRUNCATE);"
	aws s3 cp $(SQLITE_LOCAL) s3://$(S3_BUCKET)/data/stocks.db
	@echo "Uploaded from: $(SQLITE_LOCAL)"

# prod の stocks.db を dev バケットにコピー (初回セットアップ / リフレッシュ時)
sync-db-to-dev:
	aws s3 cp s3://$(S3_BUCKET)/data/stocks.db s3://$(S3_BUCKET_DEV)/data/stocks.db
	@echo "Synced prod DB to dev bucket: s3://$(S3_BUCKET_DEV)/data/stocks.db"

# -----------------------------------------------------------------------
# HazardBrief
# -----------------------------------------------------------------------

install-hazardbrief:
	cd hazardbrief/backend && uv pip install -e ".[dev]"
	cd hazardbrief/frontend && npm install
	cd hazardbrief/cdk && npm ci

# HazardBrief: CDK + frontend を両方デプロイ
deploy-hazardbrief: deploy-hazardbrief-cdk deploy-hazardbrief-frontend

# HazardBrief: CDK のみデプロイ (backend/Lambda/インフラ変更時)
deploy-hazardbrief-cdk:
	cd hazardbrief/cdk && npm run build && npx cdk deploy HazardBriefStack --require-approval never

# HazardBrief: frontend のみビルド&S3同期 (Vue変更時)
deploy-hazardbrief-frontend:
	cd hazardbrief/frontend && npm run build && aws s3 sync dist/ s3://$$(aws cloudformation describe-stacks --stack-name HazardBriefStack --query 'Stacks[0].Outputs[?OutputKey==`FrontendBucketName`].OutputValue' --output text)/frontend/ --delete

# HazardBrief: backend テスト
test-hazardbrief-backend:
	cd hazardbrief/backend && .venv/bin/python -m pytest tests/ -v

# HazardBrief: frontend テスト
test-hazardbrief-frontend:
	cd hazardbrief/frontend && npx vitest run
