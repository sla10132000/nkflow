# GCP → AWS 移行計画

> Source of truth: `docs/spec.md`
> 作成日: 2026-03-01

---

## 1. 現行 GCP 依存箇所 一覧

### 1.1 インフラ・ランタイム

| ファイル | 箇所 | GCP 依存内容 |
|---|---|---|
| `nikkei-analysis/src/config.py` | `GCS_BUCKET` 変数 | Google Cloud Storage バケット名 |
| `nikkei-analysis/src/batch/storage.py` | `_restore_sqlite()` | `litestream restore` コマンド (GCS バックエンド) |
| `nikkei-analysis/src/batch/storage.py` | `_restore_kuzu()` | `from google.cloud import storage as gcs` / `gcs.Client()` |
| `nikkei-analysis/src/batch/storage.py` | `start_replicate()` | `litestream replicate` コマンド (GCS WAL レプリケーション) |
| `nikkei-analysis/src/batch/storage.py` | `stop_replicate()` | litestream プロセス管理 |
| `nikkei-analysis/src/batch/storage.py` | `_upload_kuzu()` | `gcs.Client()` / `blob.upload_from_filename()` |
| `nikkei-analysis/src/batch/storage.py` | `persist()` | litestream stop + GCS アップロード |
| `nikkei-analysis/src/batch/main.py` | コメント・ログ | "GCS から復元", "Cloud Run Job", "Cloud Logging" |
| `nikkei-analysis/src/batch/main.py` | 関数シグネチャ | Cloud Run Job 向け CLI (`argparse` + `sys.exit`) |
| `nikkei-analysis/litestream.yml` | 全体 | GCS バックエンドの litestream 設定ファイル |
| `nikkei-analysis/Dockerfile.batch` | litestream インストール | `ADD .../litestream-*.tar.gz` |
| `nikkei-analysis/Dockerfile.batch` | gsutil インストール | Google Cloud SDK インストール |
| `nikkei-analysis/Dockerfile.batch` | ベースイメージ | `python:3.12-slim` (Lambda 非互換) |
| `nikkei-analysis/Dockerfile.dashboard` | litestream インストール | `ADD .../litestream-*.tar.gz` |
| `nikkei-analysis/Dockerfile.dashboard` | ベースイメージ | `python:3.12-slim` |
| `nikkei-analysis/cloudbuild-batch.yaml` | 全体 | Cloud Build (GCR イメージ push) |
| `nikkei-analysis/cloudbuild-dashboard.yaml` | 全体 | Cloud Build (GCR イメージ push) |
| `nikkei-analysis/scripts/deploy.sh` | 全体 | `gcloud`, `gsutil`, Cloud Run Jobs, Cloud Scheduler, Secret Manager |
| `nikkei-analysis/scripts/start_dashboard.sh` | `litestream restore` | GCS から SQLite 復元 |
| `nikkei-analysis/scripts/start_dashboard.sh` | `streamlit run` | Streamlit ダッシュボード (UI層) |
| `nikkei-analysis/SETUP.md` | 全体 | GCP 手順書 |

### 1.2 Python パッケージ依存

| パッケージ | 用途 | GCP 固有 |
|---|---|---|
| `google-cloud-storage` | GCS 読み書き | ✅ 削除対象 |
| `streamlit` | GCP Cloud Run で Streamlit UI 提供 | ✅ 削除対象 (Vue3 SPA に置換) |
| `plotly` | Streamlit チャート | ✅ 削除対象 |
| `pyvis` | Streamlit ネットワーク可視化 | ✅ 削除対象 |

### 1.3 テスト

| ファイル | GCP 依存内容 |
|---|---|
| `tests/test_storage.py` | `gsutil cp` / `litestream` コマンドのモック検証 |
| `tests/test_storage.py` | `GCS_BUCKET` 環境変数テスト |
| `conftest.py` | `GCS_BUCKET=test-bucket` 環境変数 |

---

## 2. GCP → AWS 対応表

| GCP サービス | AWS サービス | 用途 |
|---|---|---|
| Cloud Run Job | Lambda コンテナ (バッチ) | 日次バッチ実行 |
| Cloud Run Service (Streamlit) | Lambda コンテナ + Function URL (FastAPI) | REST API |
| Cloud Scheduler | EventBridge Scheduler | 日次トリガー (18:00 JST) |
| Cloud Storage (GCS) | S3 | SQLite + KùzuDB 永続化 |
| Secret Manager | SSM Parameter Store (SecureString) | J-Quants クレデンシャル |
| Container Registry (GCR) | ECR | コンテナイメージ保管 |
| Cloud Build | (CDK から ECR push) | CI/CD |
| Cloud Logging | CloudWatch Logs | ログ収集 (自動) |
| Litestream (WAL レプリケーション) | boto3 S3 upload (バッチ終了時スナップショット) | SQLite 永続化戦略変更 |
| IAM Service Account | IAM Role + Lambda 実行ロール | 権限管理 |
| Streamlit SPA | Vue3 SPA (S3 + CloudFront) | フロントエンド UI |

### 永続化戦略の変更点

| | GCP (旧) | AWS (新) |
|---|---|---|
| SQLite 同期 | litestream が WAL を GCS にリアルタイムレプリケーション | Lambda 終了前に boto3 で S3 にアップロード |
| KùzuDB 同期 | gsutil cp で tar.gz アップロード | boto3 で tar.gz アップロード |
| 起動時復元 | `litestream restore` | boto3 S3 download (初回時スキーマ初期化) |
| クレデンシャル | Secret Manager | SSM Parameter Store (SecureString) |

---

## 3. 新ディレクトリ構成 (spec.md 準拠)

```
nkflow/
├── docs/
│   ├── spec.md
│   └── migration_plan.md
│
├── backend/                      # 旧 nikkei-analysis/ を移行
│   ├── pyproject.toml            # boto3/fastapi/mangum 追加、GCS/streamlit 削除
│   ├── Dockerfile.batch          # Lambda コンテナ (ECR Lambda ベース)
│   ├── Dockerfile.api            # Lambda コンテナ (ECR Lambda ベース)
│   ├── src/
│   │   ├── config.py             # GCS_BUCKET → S3_BUCKET + SSM
│   │   ├── batch/
│   │   │   ├── handler.py        # Lambda ハンドラ (旧 main.py)
│   │   │   ├── storage.py        # boto3 S3 (旧 litestream + GCS)
│   │   │   ├── fetch.py          # 変更なし
│   │   │   ├── compute.py        # 変更なし
│   │   │   ├── statistics.py     # 変更なし
│   │   │   ├── graph.py          # 変更なし
│   │   │   └── signals.py        # 変更なし
│   │   └── api/                  # 新規: FastAPI REST API
│   │       ├── handler.py        # Mangum アダプタ
│   │       ├── main.py           # FastAPI アプリ
│   │       ├── routers/
│   │       │   ├── summary.py
│   │       │   ├── prices.py
│   │       │   ├── signals.py
│   │       │   ├── network.py
│   │       │   └── stock.py
│   │       └── storage.py        # S3 → /tmp SQLite キャッシュ
│   ├── scripts/
│   │   ├── init_sqlite.py        # 変更なし
│   │   ├── init_kuzu.py          # 変更なし
│   │   └── backfill.py           # S3_BUCKET 参照に更新
│   └── tests/
│       ├── conftest.py           # GCS_BUCKET → S3_BUCKET
│       ├── test_storage.py       # moto[s3,ssm] に全面書き換え
│       ├── test_fetch.py         # 変更なし
│       ├── test_compute.py       # 変更なし
│       ├── test_statistics.py    # 変更なし
│       ├── test_graph.py         # 変更なし
│       └── fixtures/
│           └── sample_prices.csv
│
├── cdk/                          # 新規: AWS CDK (TypeScript)
│   ├── package.json
│   ├── tsconfig.json
│   ├── cdk.json
│   ├── bin/nkflow.ts
│   └── lib/nkflow-stack.ts
│
└── frontend/                     # 新規: Vue3 SPA
    ├── package.json
    ├── vite.config.ts
    └── src/
        └── ...
```

### 削除するファイル (GCP 固有)

| ファイル | 理由 |
|---|---|
| `nikkei-analysis/litestream.yml` | litestream 廃止 |
| `nikkei-analysis/cloudbuild-batch.yaml` | Cloud Build 廃止 |
| `nikkei-analysis/cloudbuild-dashboard.yaml` | Cloud Build 廃止 |
| `nikkei-analysis/scripts/deploy.sh` | gcloud/gsutil コマンド全廃 → CDK deploy に置換 |
| `nikkei-analysis/scripts/start_dashboard.sh` | Streamlit 廃止 |
| `nikkei-analysis/Dockerfile.dashboard` | Streamlit ダッシュボード廃止 |
| `nikkei-analysis/src/dashboard/` | Streamlit UI 全廃 (Vue3 SPA に置換) |
| `nikkei-analysis/SETUP.md` | GCP 手順書 (README.md に AWS 手順を別途記載) |

---

## 4. 移行ステップ

### Step 1: ディレクトリ再構成

```
nikkei-analysis/ → backend/ にリネーム (src/, scripts/, tests/ はそのまま)
GCP 固有ファイルを削除
```

### Step 2: config.py の書き換え

- `GCS_BUCKET` → `S3_BUCKET` (必須環境変数)
- `S3_SQLITE_KEY = "data/stocks.db"` を追加
- `S3_KUZU_KEY = "data/kuzu_db.tar.gz"` を追加
- J-Quants クレデンシャルは SSM から取得する注記を追加

### Step 3: storage.py の全面書き換え

**削除する依存**:
- `litestream restore / replicate` サブプロセス呼び出し
- `google.cloud.storage` (GCS SDK)
- `subprocess` (gsutil)

**追加する実装**:
- `boto3.client("s3")` で S3 download/upload
- `boto3.client("ssm")` で J-Quants クレデンシャル取得
- `download()`: S3 → /tmp/stocks.db + /tmp/kuzu_db.tar.gz → 展開
- `upload()`: /tmp/stocks.db VACUUM → S3、/tmp/kuzu_db → tar.gz → S3
- `get_credentials()`: SSM `/nkflow/jquants-email` と `/nkflow/jquants-password`

### Step 4: batch/main.py → batch/handler.py に変換

- 関数名: `run_batch()` → `handler(event, context)`
- CLI エントリポイント (`argparse`, `sys.exit`) を削除
- レスポンス形式: Lambda JSON レスポンス
- `storage.restore()` → `storage.download()`
- `storage.start_replicate()` → 削除 (litestream 廃止)
- `storage.persist()` → `storage.upload()`
- ログ: `logging` のまま (CloudWatch Logs 自動収集)

### Step 5: pyproject.toml 依存更新

- 削除: `google-cloud-storage`, `streamlit`, `plotly`, `pyvis`
- 追加: `boto3>=1.34`, `fastapi>=0.115`, `mangum>=0.19`
- dev 依存: `pytest-mock` → `moto[s3,ssm]`, `httpx` 追加

### Step 6: API Lambda 新規作成 (src/api/)

- `handler.py`: `Mangum(app)` でアダプタ
- `main.py`: FastAPI アプリ + 起動時 S3 → SQLite ダウンロード
- `routers/`: 5 エンドポイント (summary, prices, signals, network, stock)
- `storage.py`: /tmp SQLite キャッシュ (1時間有効)

### Step 7: Dockerfile 書き換え

- ベースイメージ: `public.ecr.aws/lambda/python:3.12`
- litestream / gsutil / Google Cloud SDK インストール削除
- `CMD` を Lambda ハンドラ形式に変更

### Step 8: テスト書き換え

- `conftest.py`: `GCS_BUCKET` → `S3_BUCKET`
- `test_storage.py`: `moto` を使った S3/SSM モックに全面書き換え
  - litestream コマンド検証テスト → 削除
  - GCS API 呼び出しテスト → boto3/moto ベースに置換

### Step 9: CDK スタック作成

- S3 バケット、Lambda x2 (batch/api)、EventBridge Scheduler
- CloudFront (S3 SPA + API Lambda Function URL)
- ECR リポジトリ x2、SSM パラメータ (枠のみ)
- IAM ロール (S3 R/W + SSM R)

### Step 10: フロントエンド雛形作成 (Phase 8 相当)

- Vue3 + Vite + vue-router + TypeScript
- `useApi.ts` で Lambda Function URL を呼び出す

---

## 5. 変更不要なファイル

以下のファイルはビジネスロジックのみで GCP 依存なし。**変更不要**。

| ファイル | 内容 |
|---|---|
| `src/batch/fetch.py` | J-Quants API クライアント、SQLite 書き込み |
| `src/batch/compute.py` | DuckDB 計算ロジック |
| `src/batch/statistics.py` | statsmodels / scipy 統計分析 |
| `src/batch/graph.py` | KùzuDB グラフ構築・探索 |
| `src/batch/signals.py` | 予測シグナル生成 |
| `scripts/init_sqlite.py` | SQLite スキーマ初期化 |
| `scripts/init_kuzu.py` | KùzuDB スキーマ初期化 |
| `scripts/backfill.py` | 過去データバックフィル (パス引数のみ) |
| `tests/test_fetch.py` | J-Quants モックテスト |
| `tests/test_compute.py` | DuckDB 計算テスト |
| `tests/test_statistics.py` | 統計分析テスト |
| `tests/test_graph.py` | グラフ構築テスト |
| `tests/fixtures/sample_prices.csv` | テスト用サンプルデータ |

---

## 6. 進捗チェックリスト

- [x] migration_plan.md 作成
- [x] ディレクトリ再構成 (nikkei-analysis/ → backend/)
- [x] GCP 固有ファイル削除 (litestream.yml, cloudbuild-*.yaml, deploy.sh, Dockerfile.dashboard, src/dashboard/, SETUP.md)
- [x] config.py 書き換え (GCS_BUCKET → S3_BUCKET + S3_SQLITE_KEY + S3_KUZU_KEY)
- [x] storage.py 書き換え (litestream/GCS → boto3 S3/SSM)
- [x] batch/handler.py 作成 (Cloud Run main.py → Lambda handler)
- [x] pyproject.toml 依存更新 (google-cloud-storage/streamlit/plotly/pyvis 削除 → boto3/fastapi/mangum 追加)
- [x] API Lambda 新規作成 (src/api/ — handler.py, main.py, routers x5, storage.py)
- [x] Dockerfile.batch / Dockerfile.api 書き換え (Lambda コンテナ形式)
- [x] tests/test_storage.py 書き換え (moto[s3,ssm] ベース — 102テスト全通過)
- [x] conftest.py 更新 (GCS_BUCKET → S3_BUCKET)
- [x] CDK スタック作成 (cdk/lib/nkflow-stack.ts — S3/Lambda/CloudFront/EventBridge/ECR/SSM)
- [ ] フロントエンド雛形 (frontend/) — Phase 8 で実装予定
