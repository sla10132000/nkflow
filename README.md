# nkflow — 日経225 投資分析基盤 (AWS版)

日経平均225構成銘柄の日次データを収集・分析し、グラフDB（KùzuDB）で銘柄間の因果関係・資金フロー・予測シグナルを可視化する個人向け投資分析基盤。

## アーキテクチャ概要

```
EventBridge Scheduler (毎営業日 JST 18:00)
  → Lambda (バッチ) : J-Quants 取得 → DuckDB 計算 → 統計分析 → グラフ構築 → S3 永続化

CloudFront
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

## J-Quants API について

[J-Quants](https://jpx-jquants.com/) の API キーが必要です。

| プラン | データ範囲 | 直近制限 | レート上限 |
|--------|-----------|---------|-----------|
| **Free** | 過去2年分 | 直近12週は取得不可 | **5 req/min** |
| Light / **Standard** / Premium | 最大10年分 | 制限なし | 無制限 |

本プロジェクトは **Standard プラン** で運用しています (`JQUANTS_PLAN=standard`)。

SSM には J-Quants ダッシュボードの「**API キー**」を設定し、v2 API (`ClientV2`) を使用します。

## Phase 0: 事前準備 (手動)

```bash
# 1. AWS CLI 設定
aws configure

# 2. CDK ブートストラップ (初回のみ)
cdk bootstrap aws://<ACCOUNT_ID>/ap-northeast-1

# 3. J-Quants API キーを SSM に登録
#    API キーは https://jpx-jquants.com/ のダッシュボードで取得
aws ssm put-parameter \
  --name /nkflow/jquants-api-key \
  --type SecureString \
  --value "your_api_key" \
  --overwrite
```

## デプロイ手順

### 1. CDK スタックをデプロイ

```bash
cd cdk
npm install
cdk deploy

# デプロイ後に出力される値を控える
# DataBucketName: nkflow-data-<ACCOUNT_ID>
# ApiLambdaUrl: https://xxxxxx.lambda-url.ap-northeast-1.on.aws
```

### 2. バッチ Lambda イメージをビルド & プッシュ

```bash
# ECR にログイン
aws ecr get-login-password --region ap-northeast-1 | \
  docker login --username AWS --password-stdin \
  <ACCOUNT_ID>.dkr.ecr.ap-northeast-1.amazonaws.com

# バッチイメージをビルド
cd backend
docker build -f Dockerfile.batch \
  --platform linux/amd64 \
  -t nkflow-batch .

# ECR にプッシュ
docker tag nkflow-batch \
  <ACCOUNT_ID>.dkr.ecr.ap-northeast-1.amazonaws.com/nkflow-batch:latest
docker push \
  <ACCOUNT_ID>.dkr.ecr.ap-northeast-1.amazonaws.com/nkflow-batch:latest
```

### 3. API Lambda イメージをビルド & プッシュ

```bash
docker build -f Dockerfile.api \
  --platform linux/amd64 \
  -t nkflow-api .

docker tag nkflow-api \
  <ACCOUNT_ID>.dkr.ecr.ap-northeast-1.amazonaws.com/nkflow-api:latest
docker push \
  <ACCOUNT_ID>.dkr.ecr.ap-northeast-1.amazonaws.com/nkflow-api:latest
```

### 4. Lambda を最新イメージに更新

```bash
aws lambda update-function-code \
  --function-name nkflow-batch \
  --image-uri <ACCOUNT_ID>.dkr.ecr.ap-northeast-1.amazonaws.com/nkflow-batch:latest

aws lambda update-function-code \
  --function-name nkflow-api \
  --image-uri <ACCOUNT_ID>.dkr.ecr.ap-northeast-1.amazonaws.com/nkflow-api:latest
```

### 5. 過去データのバックフィル (初回のみ)

```bash
cd backend
uv pip install -e ".[dev]"

# Free プラン: 自動的に過去2年・直近12週除外・12秒/req スロットリング
S3_BUCKET=nkflow-data-<ACCOUNT_ID> \
JQUANTS_API_KEY=your_api_key \
JQUANTS_PLAN=free \
  .venv/bin/python scripts/backfill.py

# 有料プランの場合 (例: standard)
S3_BUCKET=nkflow-data-<ACCOUNT_ID> \
JQUANTS_API_KEY=your_api_key \
JQUANTS_PLAN=standard \
  .venv/bin/python scripts/backfill.py --years 5
```

### 6. フロントエンドをビルド & S3 にアップロード

```bash
cd frontend
npm install

# 本番 API エンドポイントを設定
echo "VITE_API_BASE=https://xxxxxx.lambda-url.ap-northeast-1.on.aws" > .env.local

npm run build

# S3 にアップロード
aws s3 sync dist/ s3://nkflow-data-<ACCOUNT_ID>/frontend/ --delete

# CloudFront キャッシュを無効化
aws cloudfront create-invalidation \
  --distribution-id <DISTRIBUTION_ID> \
  --paths "/*"
```

## ローカル開発

### バックエンド (API)

```bash
cd backend
uv pip install -e ".[dev]"

# ローカル SQLite を用意
python scripts/init_sqlite.py /tmp/stocks.db
python scripts/init_kuzu.py /tmp/kuzu_db

# FastAPI 起動 (uvicorn)
S3_BUCKET=dummy SQLITE_PATH=/tmp/stocks.db \
  .venv/bin/uvicorn src.api.main:app --reload --port 8000
```

### フロントエンド

```bash
cd frontend
npm install
npm run dev
# → http://localhost:5173
```

## テスト

```bash
cd backend
uv pip install -e ".[dev]"
.venv/bin/python -m pytest tests/ -v
.venv/bin/python -m pytest tests/ --cov=src --cov-report=term-missing
```

## ディレクトリ構成

```
nkflow/
├── backend/
│   ├── src/
│   │   ├── config.py
│   │   ├── batch/          # Lambda バッチ処理
│   │   └── api/            # FastAPI REST API
│   ├── scripts/            # 初期化・バックフィル
│   ├── tests/
│   ├── Dockerfile.batch
│   └── Dockerfile.api
├── cdk/                    # AWS CDK スタック (TypeScript)
├── frontend/               # Vue3 SPA (Vite)
└── docs/
    └── spec.md             # 設計書
```

## コスト目安

AWS 無料枠内で運用可能 (月額 $0〜2)。詳細は `docs/spec.md` セクション 13 を参照。
