# CloudFront 導入計画

## ステータス

**作業中断** — AWS アカウントが CloudFront 未承認のため一時停止

- ブランチ: `worktree-feature/cloudfront`
- コミット: `2750ed0 feat(cdk): CloudFront Distribution を API Gateway 前段に追加`

---

## 目的

現在の API Gateway 直接公開から CloudFront を前段に挟み、以下を実現する。

- HTTPS 強制 (HTTP → HTTPS リダイレクト)
- エッジロケーションによるレイテンシ低減
- 将来的なカスタムドメイン・WAF 追加の足がかり

---

## 現在のアーキテクチャ

```
ブラウザ
  │
  ▼
API Gateway (prod ステージ)
  │
  ▼
Lambda: nkflow-api (FastAPI + Mangum)
  │  - フロントエンド SPA 配信 (S3 から読み取り)
  │  - /api/* エンドポイント
  ▼
S3: nkflow-data-{account}
```

## 変更後のアーキテクチャ

```
ブラウザ
  │
  ▼
CloudFront Distribution (*.cloudfront.net)
  │  - デフォルト動作: CACHING_DISABLED → API Gateway
  │  - /api/* 動作:   CACHING_DISABLED → API Gateway
  │  - HTTPS 強制
  │  - PriceClass: PRICE_CLASS_200 (北米・欧州・アジア)
  ▼
API Gateway (prod ステージ)  ← 直接アクセスも引き続き可能
  │
  ▼
Lambda: nkflow-api
  ▼
S3: nkflow-data-{account}
```

---

## 実装済みの変更

### `cdk/lib/nkflow-stack.ts`

**追加インポート**

```typescript
aws_cloudfront as cloudfront,
aws_cloudfront_origins as origins,
```

**追加リソース (セクション 11)**

```typescript
const apiGatewayDomain = `${restApi.restApiId}.execute-api.${this.region}.amazonaws.com`;

const distribution = new cloudfront.Distribution(this, 'NkflowDistribution', {
  comment: 'nkflow CDN — API Gateway オリジン',
  defaultBehavior: {
    origin: new origins.HttpOrigin(apiGatewayDomain, {
      originPath: '/prod',
      protocolPolicy: cloudfront.OriginProtocolPolicy.HTTPS_ONLY,
    }),
    cachePolicy: cloudfront.CachePolicy.CACHING_DISABLED,
    originRequestPolicy: cloudfront.OriginRequestPolicy.ALL_VIEWER_EXCEPT_HOST_HEADER,
    allowedMethods: cloudfront.AllowedMethods.ALLOW_ALL,
    viewerProtocolPolicy: cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
  },
  additionalBehaviors: {
    '/api/*': {
      origin: new origins.HttpOrigin(apiGatewayDomain, {
        originPath: '/prod',
        protocolPolicy: cloudfront.OriginProtocolPolicy.HTTPS_ONLY,
      }),
      cachePolicy: cloudfront.CachePolicy.CACHING_DISABLED,
      originRequestPolicy: cloudfront.OriginRequestPolicy.ALL_VIEWER_EXCEPT_HOST_HEADER,
      allowedMethods: cloudfront.AllowedMethods.ALLOW_ALL,
      viewerProtocolPolicy: cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
    },
  },
  enableLogging: false,
  priceClass: cloudfront.PriceClass.PRICE_CLASS_200,
});
```

**Outputs の変更**

| Output | 変更内容 |
|---|---|
| `FrontendUrl` | `ApiGatewayUrl` にリネーム (内部参照用) |
| `CloudFrontUrl` | 新規追加 — 公開エンドポイント |
| `CloudFrontDistributionId` | 新規追加 — キャッシュ無効化用 |

---

## デプロイ失敗の原因

```
Access denied for operation 'AWS::CloudFront::Distribution':
Your account must be verified before you can add new CloudFront resources.
(Request ID: 61fc6df4-861d-4192-8479-4b2401eb061a)
```

AWS アカウントの CloudFront 利用承認が未完了。新規アカウントでよく発生する制限。
スタックはロールバック済みで既存動作に影響なし。

---

## 再開手順

1. [AWS Support](https://console.aws.amazon.com/support/home#/) でケースを作成
   - カテゴリ: CloudFront > General Question
   - 本文例: "Please verify my account to enable CloudFront resource creation."
2. 承認メール受領後 (通常数時間〜1営業日)
3. ブランチ `worktree-feature/cloudfront` に切り替え
4. `make deploy-cdk` を実行
5. Output の `CloudFrontUrl` を確認してブラウザで動作確認
6. 問題なければ `dev` ブランチへマージ

---

## 将来の拡張候補

- カスタムドメイン + ACM 証明書 (`domainNames` / `certificate` プロパティ)
- WAF WebACL アタッチ (`webAclId` プロパティ)
- フロントエンド静的ファイルを S3 直接オリジンに分離してキャッシュ有効化
- CloudFront Functions による SPA フォールバック (index.html リダイレクト)

---

最終更新: 2026-03-03
