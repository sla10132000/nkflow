# AWS 独自ドメイン + HTTPS 構成へのリファクタリングプラン

## 現状の構成

- **フロントエンド**: Vue 3
- **バックエンド**: AWS Lambda (Function URL で直接公開)
- **問題**: 独自ドメインなし、HTTPS未対応（or Function URLの直接公開）

## 目標構成

```
ユーザー → 独自ドメイン(HTTPS) → CloudFront → S3 (Vue3 SPA)
                                       ↓ (/api/*)
                                  API Gateway → Lambda
```

---

## Phase 1: インフラ準備

1. Route 53 で独自ドメインのホストゾーン作成（または既存確認）
2. ACM (us-east-1) で SSL 証明書をリクエスト → DNS検証
3. S3 バケット作成（静的ホスティング用、パブリックアクセス不要）

## Phase 2: フロントエンド（Vue3 → S3 + CloudFront）

4. Vue3 プロジェクトを `npm run build` で静的ファイル生成
5. S3 にビルド成果物をアップロード
6. CloudFront ディストリビューション作成
   - オリジン: S3（OAC経由）
   - カスタムドメイン + ACM証明書を紐付け
   - SPA用: カスタムエラーレスポンス 403/404 → /index.html (200)
7. Route 53 に A レコード（エイリアス → CloudFront）を追加

## Phase 3: バックエンド（Lambda Function URL → API Gateway）

8. API Gateway (HTTP API) を作成
9. 既存の Lambda 関数を API Gateway に統合
   - Lambda Function URL を削除
   - API Gateway のルート設定（例: POST /api/xxx）
   - 必要に応じて CORS 設定
10. API Gateway にカスタムドメイン設定
    - **方法A（推奨）**: CloudFront の `/api/*` パスパターンで API Gateway をオリジンに設定
    - 方法B: `api.example.com` として別ドメインで公開

## Phase 4: Vue3 側の修正

11. API呼び出しのベースURLを変更
    - 旧: Lambda Function URL (`https://xxxxx.lambda-url.ap-northeast-1.on.aws`)
    - 新: `/api/xxx`（同一ドメイン、CloudFront経由）
12. 環境変数の整理（`.env.production`）

## Phase 5: デプロイ・検証

13. フロントエンド再ビルド & S3アップロード
14. CloudFront キャッシュ無効化
15. HTTPS + 独自ドメインでのアクセス確認
16. API Gateway 経由の API 動作確認
17. Lambda Function URL の無効化・削除

---

## 推奨構成: CloudFront 1つで統合（方法A）

```
CloudFront ディストリビューション
├── デフォルト (*)       → S3 オリジン (Vue3 SPA)
└── /api/*              → API Gateway オリジン
```

この構成なら **ドメインが1つで済み、CORSも不要** になる。

---

## 補足: 必要な情報

- 独自ドメイン名
- AWSリージョン
- 既存の Lambda 関数名・ARN
- Vue3 プロジェクトのAPI呼び出し箇所
