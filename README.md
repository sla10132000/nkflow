# nkflow — 日経225 投資分析基盤 (AWS版)

日経平均225構成銘柄の日次データを収集・分析し、グラフDB（KùzuDB）で銘柄間の因果関係・資金フロー・予測シグナルを可視化する個人向け投資分析基盤。

## リポジトリ構成

```
/
├── nkflow/                 # プロダクト: 日経225 分析基盤
│   ├── backend/            # FastAPI REST API (Lambda)
│   ├── frontend/           # Vue3 SPA (Vite)
│   ├── cdk/                # AWS CDK スタック (TypeScript)
│   └── docs/               # 設計書
├── datalake/               # 共有データパイプライン (Lambda バッチ)
└── Makefile                # ビルド・テスト・デプロイ
```

## アーキテクチャ概要

```
EventBridge Scheduler (毎営業日 JST 18:00)
  → Lambda (バッチ) : J-Quants 取得 → DuckDB 計算 → 統計分析 → グラフ構築 → S3 永続化

API Gateway
  ├── / (S3 静的ホスティング)  : Vue3 SPA
  └── /api/* (Lambda Function URL) : FastAPI REST API
```

## 前提条件

| ツール | バージョン |
|---|---|
| AWS CLI | v2 |
| AWS CDK CLI | v2 (`npm install -g aws-cdk`) |
| Node.js | v18+ |
| Python | 3.12 |
| uv | 最新 |
| Docker Desktop | 最新 |

## クイックスタート

```bash
# 依存関係インストール
make install

# テスト
make test            # backend + datalake pytest
make test-frontend   # vitest

# デプロイ
make deploy          # CDK + frontend を両方デプロイ
```

## デプロイ手順

### 1. CDK スタックをデプロイ

```bash
cd nkflow/cdk
npm install
npx cdk deploy NkflowStack
```

### 2. フロントエンドをビルド & S3 にアップロード

```bash
make deploy-frontend
```

## ローカル開発

### バックエンド (API)

```bash
cd nkflow/backend
uv pip install -e ".[dev]"

# ローカル SQLite を用意
make pull

# FastAPI 起動
make dev-api
```

### フロントエンド

```bash
cd nkflow/frontend
npm install
npm run dev
# → http://localhost:5173
```

## テスト

```bash
make test            # backend + datalake
make test-frontend   # vitest
make lint            # ruff
make lint-frontend   # biome
```

## コスト目安

AWS 無料枠内で運用可能 (月額 $0〜2)。
