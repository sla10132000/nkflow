# Bugfix: nkflow-api Lambda `/tmp` 容量不足で 500 エラー

## 発覚経緯

2026-03-03、Playwright の実 API テスト (`npm run test:e2e:real`) を実行したところ
本番 API が 500 を返していることが判明。Lambda ログを確認したところ根本原因を特定。

## 根本原因

`nkflow-api` Lambda が S3 から `stocks.db` を `/tmp` にダウンロードする際に
ディスク容量が枯渇し書き込みに失敗している。

```
OSError: [Errno 28] No space left on device
```

### 現在の設定 (`cdk/lib/nkflow-stack.ts` L142 付近)

| 項目 | 現在値 | batch Lambda の値 |
|---|---|---|
| `memorySize` | **512 MB** | 2048 MB |
| `ephemeralStorageSize` | **未設定 (デフォルト 512 MB)** | 2048 MB |

`nkflow-batch` には `ephemeralStorageSize: cdk.Size.mebibytes(2048)` が設定されているが、
`nkflow-api` には設定が漏れている。`stocks.db` は成長し続けるため 512 MB では不足している。

## 修正内容

`cdk/lib/nkflow-stack.ts` の `apiLambda` 定義に `ephemeralStorageSize` を追加する。

```diff
  const apiLambda = new lambda.DockerImageFunction(this, 'NkflowApiLambda', {
    functionName: 'nkflow-api',
    ...
    memorySize: 512,
    timeout: Duration.seconds(30),
+   ephemeralStorageSize: cdk.Size.mebibytes(2048),
    role: apiRole,
```

## 実行手順

```bash
# 1. CDK の差分確認
cd cdk && npm run build && npx cdk diff NkflowStack

# 2. デプロイ
npx cdk deploy NkflowStack --require-approval never

# 3. 動作確認
E2E_API_BASE=https://018cw5o5hh.execute-api.ap-northeast-1.amazonaws.com/prod \
  cd frontend && npm run test:e2e:real
```

## 期待する結果

- `nkflow-api` Lambda の `/tmp` が 2048 MB に拡張される
- `stocks.db` のダウンロードが成功し、API が正常なレスポンスを返す
- `test:e2e:real` が pass する

## 備考

- `ephemeralStorageSize` は Lambda の課金対象。512 MB 超の分は追加料金が発生するが微小。
- `stocks.db` のサイズが今後も増え続ける場合は定期的な vacuum やアーカイブも検討する。
