S3_BUCKET := nkflow-data-268914462689

.PHONY: help \
        install install-backend install-frontend install-cdk \
        dev \
        test lint \
        build build-frontend build-cdk \
        diff deploy deploy-cdk deploy-frontend \
        pull push push-db \
        migrate

# デフォルトターゲット
help:
	@echo "Usage: make <target>"
	@echo ""
	@echo "--- Install ---"
	@echo "  install           全レイヤーの依存関係をインストール"
	@echo "  install-backend   backend: uv pip install -e .[dev]"
	@echo "  install-frontend  frontend: npm install"
	@echo "  install-cdk       cdk: npm ci"
	@echo ""
	@echo "--- Dev ---"
	@echo "  dev               フロントエンド開発サーバー起動 (vite, :5173)"
	@echo "  dev-api           バックエンド開発サーバー起動 (uvicorn, :8001)"
	@echo "                    ※ 事前に make pull で /tmp/stocks.db を取得すること"
	@echo ""
	@echo "--- Test / Lint ---"
	@echo "  test              backend pytest"
	@echo "  lint              backend ruff"
	@echo "  lint-frontend     frontend biome check"
	@echo ""
	@echo "--- Build ---"
	@echo "  build             frontend + cdk をビルド"
	@echo "  build-frontend    vue-tsc && vite build"
	@echo "  build-cdk         tsc (CDK TypeScript コンパイル)"
	@echo ""
	@echo "--- Deploy ---"
	@echo "  deploy            CDK + frontend を両方デプロイ (通常はこれ)"
	@echo "  deploy-cdk        CDK のみデプロイ (backend/Lambda/インフラ変更時)"
	@echo "  deploy-frontend   frontend のみビルド&S3同期 (Vue変更時)"
	@echo "  diff              cdk diff NkflowStack"
	@echo ""
	@echo "--- Git ---"
	@echo "  push              git push origin main (GitHub Actions deploy をトリガー)"
	@echo ""
	@echo "--- DB ---"
	@echo "  pull              S3 から /tmp/stocks.db をダウンロード"
	@echo "  push-db           /tmp/stocks.db を S3 へアップロード"

# -----------------------------------------------------------------------
# Install
# -----------------------------------------------------------------------

install: install-backend install-frontend install-cdk

install-backend:
	cd backend && uv pip install -e ".[dev]"

install-frontend:
	cd frontend && npm install

install-cdk:
	cd cdk && npm ci

# -----------------------------------------------------------------------
# Dev server
# -----------------------------------------------------------------------

dev:
	cd frontend && npm run dev

# バックエンド開発サーバー (S3_BUCKET 未設定 = ローカルファイルモード)
# 事前に: make pull  (/tmp/stocks.db をS3からダウンロード)
dev-api:
	cd backend && SQLITE_PATH=/tmp/stocks.db .venv/bin/uvicorn src.api.main:app --host 127.0.0.1 --port 8001 --reload

# -----------------------------------------------------------------------
# Test / Lint
# -----------------------------------------------------------------------

test:
	cd backend && .venv/bin/python -m pytest tests/ -v

lint:
	cd backend && .venv/bin/ruff check src/ tests/

lint-frontend:
	cd frontend && npm run lint

# -----------------------------------------------------------------------
# Build
# -----------------------------------------------------------------------

build: build-frontend build-cdk

build-frontend:
	cd frontend && npm run build

build-cdk:
	cd cdk && npm run build

# -----------------------------------------------------------------------
# CDK / Deploy
# -----------------------------------------------------------------------

diff: build-cdk
	cd cdk && npx cdk diff NkflowStack

# CDK + frontend を両方デプロイ (通常はこれを使う)
deploy: deploy-cdk deploy-frontend

# CDK のみ (backend/Lambda/インフラ変更時)
deploy-cdk: build-cdk
	cd cdk && npx cdk deploy NkflowStack --require-approval never

# frontend のみ: ビルドして S3 へ同期
# ⚠️ GitHub Actions は frontend/ を自動デプロイしない — Vue 変更後は必ずこれを実行
deploy-frontend: build-frontend
	aws s3 sync frontend/dist/ s3://$(S3_BUCKET)/frontend/ --delete

# -----------------------------------------------------------------------
# Git
# -----------------------------------------------------------------------

# git push → GitHub Actions が CDK deploy を自動実行 (frontend は含まない)
# ⚠️ frontend 変更時は push 後に make deploy-frontend も実行すること
push:
	git push origin main

# -----------------------------------------------------------------------
# DB (SQLite)
# -----------------------------------------------------------------------

# S3 から /tmp/stocks.db をダウンロード (ローカル分析用)
pull:
	aws s3 cp s3://$(S3_BUCKET)/data/stocks.db /tmp/stocks.db

# /tmp/stocks.db を S3 へアップロード (バックフィル後など)
push-db:
	aws s3 cp /tmp/stocks.db s3://$(S3_BUCKET)/data/stocks.db
