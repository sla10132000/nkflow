# Auth0 Google ソーシャルログイン実装計画

最終更新: 2026-03-03
ステータス: **実装済み (Auth0ドメイン設定待ちで中断)**
ブランチ: `worktree-feature/auth0-google-auth`

---

## 概要

nkflow SPA に Auth0 を使った Google アカウント認証を追加する。
認証されたユーザーのみが画面にアクセスでき、ポートフォリオ系 API エンドポイントは JWT で保護される。

### Auth0 アプリ情報

| 項目 | 値 |
|---|---|
| テナント | `dev-0ay7xweu5xq7tmq2` |
| Domain | `dev-0ay7xweu5xq7tmq2.us.auth0.com` |
| Client ID | `wBpgIGTDeBKZ8siQh9zqpRstjwKzhT2G` |
| アプリ種別 | SPA (シングルページアプリケーション) |
| 有効な接続 | Username-Password-Authentication, **google-oauth2** |

---

## 実装済みの内容

コミット: `47966c3` on `worktree-feature/auth0-google-auth`

### Frontend

| ファイル | 変更内容 |
|---|---|
| `frontend/package.json` | `@auth0/auth0-vue ^2.3.3` を追加 |
| `frontend/src/main.ts` | Auth0プラグインを初期化。env変数 `VITE_AUTH0_DOMAIN` / `VITE_AUTH0_CLIENT_ID` / `VITE_AUTH0_AUDIENCE` を使用 |
| `frontend/src/App.vue` | ナビバーにGoogleログイン/ログアウトボタン + ユーザーアバター + 名前を追加。未認証時はナビリンクを非表示 |
| `frontend/src/router/index.ts` | 全ルートに `authGuard` を適用。`/callback` ルートを追加 |
| `frontend/src/views/AuthCallbackView.vue` | Auth0リダイレクトコールバック用画面 (新規) |
| `frontend/src/composables/useApi.ts` | Axios interceptor で Bearer トークンを全 API リクエストに自動付与 |
| `frontend/.env.example` | Auth0環境変数3つを追記 |
| `frontend/.env.production` | Auth0環境変数3つを追記 (audienceは空のまま) |

### Backend

| ファイル | 変更内容 |
|---|---|
| `backend/pyproject.toml` | `PyJWT>=2.8`, `cryptography>=42.0`, `httpx>=0.27` を追加 |
| `backend/src/api/auth.py` | Auth0 JWKS 経由で RS256 JWT を検証する `require_auth` FastAPI 依存性 (新規) |
| `backend/src/api/routers/portfolio.py` | `router = APIRouter(dependencies=[Depends(require_auth)])` で全 `/api/portfolio/*` を保護 |

### CDK

| ファイル | 変更内容 |
|---|---|
| `cdk/lib/nkflow-stack.ts` | API Lambda の `environment` に `AUTH0_DOMAIN`, `AUTH0_AUDIENCE` を追加 |

---

## 中断理由

Auth0 カスタムドメインの設定に時間がかかるため一時中断。
コードは完成しており、以下の Auth0/環境変数設定が完了すればデプロイ可能。

---

## 再開時に必要な作業

### 1. Auth0: API (Audience) を作成する

Auth0 ダッシュボード → **Applications → APIs → Create API**

| 項目 | 設定値 (例) |
|---|---|
| Name | nkflow API |
| Identifier (Audience) | `https://nkflow.example.com/api` (任意のURL形式) |
| Signing Algorithm | RS256 |

→ 作成後の **Identifier** の値をメモする。

### 2. Auth0: Allowed Callback URLs を設定する

Auth0 ダッシュボード → **Applications → App → Settings**

| 項目 | 設定値 |
|---|---|
| Allowed Callback URLs | `https://<本番ドメイン>/#/callback`, `http://localhost:5173/#/callback` |
| Allowed Logout URLs | `https://<本番ドメイン>`, `http://localhost:5173` |
| Allowed Web Origins | `https://<本番ドメイン>`, `http://localhost:5173` |

### 3. 環境変数を設定する

**フロントエンド** (`frontend/.env.production`):
```
VITE_AUTH0_AUDIENCE=https://nkflow.example.com/api  # 手順1で作成したIdentifier
```

**CDK デプロイ時**:
```bash
export AUTH0_DOMAIN=dev-0ay7xweu5xq7tmq2.us.auth0.com
export AUTH0_AUDIENCE=https://nkflow.example.com/api
make deploy-cdk
```

または `cdk/lib/nkflow-stack.ts` の `AUTH0_AUDIENCE` 値を直接書き換えてもよい。

### 4. パッケージをインストールしてビルド確認

```bash
cd frontend
npm install          # @auth0/auth0-vue を取得
npm run build        # ビルドエラーがないか確認
```

```bash
cd backend
uv pip install -e ".[dev]"   # PyJWT, cryptography, httpx を取得
python -m pytest tests/ -v   # 既存テストが通るか確認
```

### 5. デプロイ

```bash
# CDK (backend + infra)
make deploy-cdk

# Frontend
make deploy-frontend
```

### 6. 動作確認

1. 本番URLにアクセス → 「Googleでログイン」ボタンが表示される
2. ボタンクリック → Auth0のGoogleログイン画面にリダイレクト
3. Googleアカウントでログイン → `/#/callback` を経由して `/` に戻る
4. ナビバーにユーザー名とアバターが表示される
5. ログアウトボタンクリック → ログイン前の状態に戻る
6. `curl -X GET /api/portfolio/holdings` (トークンなし) → `401 Unauthorized`
7. `curl -X GET /api/portfolio/holdings -H "Authorization: Bearer <token>"` → 正常レスポンス

---

## アーキテクチャ概要

```
ブラウザ (Vue SPA)
  │  ①未認証でルートアクセス
  ▼
authGuard → Auth0 ログイン画面 (Google OAuth)
  │  ②Googleアカウントで認証
  ▼
Auth0 → /#/callback にリダイレクト (code + state)
  │  ③auth0-vue が code → access_token に交換
  ▼
Vue Router → / (ホーム画面)
  │  ④API呼び出し時に Axios interceptor がトークンを付与
  ▼
FastAPI (Lambda)
  │  ⑤require_auth が Auth0 JWKS でトークン検証
  ▼
保護されたエンドポイント (/api/portfolio/*)
```

---

## ファイル構成 (変更ファイル一覧)

```
nkflow/
├── frontend/
│   ├── .env.example              # ← Auth0変数追加
│   ├── .env.production           # ← Auth0変数追加
│   ├── package.json              # ← @auth0/auth0-vue追加
│   └── src/
│       ├── main.ts               # ← Auth0プラグイン初期化
│       ├── App.vue               # ← ログイン/ログアウトUI
│       ├── router/index.ts       # ← authGuard + /callback
│       ├── views/
│       │   └── AuthCallbackView.vue  # ← 新規
│       └── composables/
│           └── useApi.ts         # ← Bearerトークン注入
├── backend/
│   ├── pyproject.toml            # ← PyJWT等追加
│   └── src/api/
│       ├── auth.py               # ← 新規: JWT検証
│       └── routers/
│           └── portfolio.py      # ← require_auth適用
└── cdk/lib/
    └── nkflow-stack.ts           # ← AUTH0_DOMAIN/AUDIENCE追加
```
