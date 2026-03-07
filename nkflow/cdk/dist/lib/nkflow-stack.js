"use strict";
var __createBinding = (this && this.__createBinding) || (Object.create ? (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    var desc = Object.getOwnPropertyDescriptor(m, k);
    if (!desc || ("get" in desc ? !m.__esModule : desc.writable || desc.configurable)) {
      desc = { enumerable: true, get: function() { return m[k]; } };
    }
    Object.defineProperty(o, k2, desc);
}) : (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    o[k2] = m[k];
}));
var __setModuleDefault = (this && this.__setModuleDefault) || (Object.create ? (function(o, v) {
    Object.defineProperty(o, "default", { enumerable: true, value: v });
}) : function(o, v) {
    o["default"] = v;
});
var __importStar = (this && this.__importStar) || (function () {
    var ownKeys = function(o) {
        ownKeys = Object.getOwnPropertyNames || function (o) {
            var ar = [];
            for (var k in o) if (Object.prototype.hasOwnProperty.call(o, k)) ar[ar.length] = k;
            return ar;
        };
        return ownKeys(o);
    };
    return function (mod) {
        if (mod && mod.__esModule) return mod;
        var result = {};
        if (mod != null) for (var k = ownKeys(mod), i = 0; i < k.length; i++) if (k[i] !== "default") __createBinding(result, mod, k[i]);
        __setModuleDefault(result, mod);
        return result;
    };
})();
Object.defineProperty(exports, "__esModule", { value: true });
exports.NkflowStack = void 0;
const path = __importStar(require("path"));
const cdk = __importStar(require("aws-cdk-lib"));
const aws_cdk_lib_1 = require("aws-cdk-lib");
const aws_ecr_assets_1 = require("aws-cdk-lib/aws-ecr-assets");
const HOSTED_ZONE_DOMAIN = 'senken.app';
const BACKEND = path.join(__dirname, '../../backend');
// datalake is a shared module at repo root, not under nkflow/
const DATALAKE = path.join(__dirname, '../../../datalake');
class NkflowStack extends aws_cdk_lib_1.Stack {
    constructor(scope, id, props) {
        super(scope, id, props);
        const { envName } = props;
        const isProd = envName === 'prod';
        // リソース名サフィックス: nkflow-*-{env} 形式で環境を末尾に明示
        const suffix = envName;
        const bucketName = `senken-datalake-${envName}`;
        const domainName = isProd ? 'nkflow.senken.app' : `${envName}.nkflow.senken.app`;
        const ssmPrefix = `/nkflow/${envName}`;
        // ─────────────────────────────────────────────────────────────
        // 1. S3 Bucket
        // ─────────────────────────────────────────────────────────────
        const dataBucket = new aws_cdk_lib_1.aws_s3.Bucket(this, 'NkflowDataBucket', {
            bucketName,
            removalPolicy: aws_cdk_lib_1.RemovalPolicy.RETAIN,
            blockPublicAccess: aws_cdk_lib_1.aws_s3.BlockPublicAccess.BLOCK_ALL,
            versioned: true,
            lifecycleRules: [
                {
                    // SQLite バックアップ: 非最新バージョンを7世代まで保持し、それ以上は削除
                    prefix: 'data/stocks.db',
                    noncurrentVersionExpiration: aws_cdk_lib_1.Duration.days(1),
                    noncurrentVersionsToRetain: 7,
                },
            ],
        });
        // フロントエンド配信用バケット (nkflow 専用)
        const frontendBucket = new aws_cdk_lib_1.aws_s3.Bucket(this, 'NkflowFrontendBucket', {
            bucketName: `senken-nkflow-frontend-${envName}`,
            removalPolicy: aws_cdk_lib_1.RemovalPolicy.RETAIN,
            blockPublicAccess: aws_cdk_lib_1.aws_s3.BlockPublicAccess.BLOCK_ALL,
        });
        // ─────────────────────────────────────────────────────────────
        // 2. SSM Parameter Store (枠のみ — 値は手動で SecureString に上書き)
        // ─────────────────────────────────────────────────────────────
        new aws_cdk_lib_1.aws_ssm.StringParameter(this, 'JQuantsApiKeyParam', {
            parameterName: `${ssmPrefix}/jquants-api-key`,
            stringValue: 'PLACEHOLDER_SET_MANUALLY',
        });
        // prod のみ通知パラメータを作成 (dev では通知なし)
        if (isProd) {
            new aws_cdk_lib_1.aws_ssm.StringParameter(this, 'SlackWebhookUrlParam', {
                parameterName: `${ssmPrefix}/slack-webhook-url`,
                stringValue: 'PLACEHOLDER_SET_MANUALLY',
                description: 'Slack Incoming Webhook URL (Phase 12)',
            });
            new aws_cdk_lib_1.aws_ssm.StringParameter(this, 'LineNotifyTokenParam', {
                parameterName: `${ssmPrefix}/line-notify-token`,
                stringValue: 'PLACEHOLDER_SET_MANUALLY',
                description: 'LINE Notify アクセストークン (Phase 12)',
            });
        }
        // ─────────────────────────────────────────────────────────────
        // 3. SNS トピック + 通知 Lambda (prod のみ)
        // dev では通知なし (バッチ結果はログで確認)
        // ─────────────────────────────────────────────────────────────
        let notificationTopic;
        if (isProd) {
            notificationTopic = new aws_cdk_lib_1.aws_sns.Topic(this, 'NkflowNotificationTopic', {
                topicName: `nkflow-notifications-${suffix}`,
                displayName: 'nkflow 日次レポート通知',
            });
        }
        // ─────────────────────────────────────────────────────────────
        // 4. IAM ロール (バッチ)
        // ─────────────────────────────────────────────────────────────
        const batchRole = new aws_cdk_lib_1.aws_iam.Role(this, 'NkflowBatchRole', {
            assumedBy: new aws_cdk_lib_1.aws_iam.ServicePrincipal('lambda.amazonaws.com'),
            managedPolicies: [
                aws_cdk_lib_1.aws_iam.ManagedPolicy.fromAwsManagedPolicyName('service-role/AWSLambdaBasicExecutionRole'),
            ],
        });
        dataBucket.grantReadWrite(batchRole);
        batchRole.addToPolicy(new aws_cdk_lib_1.aws_iam.PolicyStatement({
            actions: ['ssm:GetParameter'],
            resources: [`arn:aws:ssm:${this.region}:${this.account}:parameter${ssmPrefix}/*`],
        }));
        // Phase 18: ニュース raw データ読み取り権限 (fetch_news.normalize_news で使用)
        batchRole.addToPolicy(new aws_cdk_lib_1.aws_iam.PolicyStatement({
            actions: ['s3:GetObject'],
            resources: [`${dataBucket.bucketArn}/news/raw/*`],
        }));
        // Phase 18: AWS Translate 翻訳権限
        batchRole.addToPolicy(new aws_cdk_lib_1.aws_iam.PolicyStatement({
            actions: ['translate:TranslateText'],
            resources: ['*'],
        }));
        // Phase 12: SNS publish 権限 (prod のみ)
        if (notificationTopic) {
            batchRole.addToPolicy(new aws_cdk_lib_1.aws_iam.PolicyStatement({
                actions: ['sns:Publish'],
                resources: [notificationTopic.topicArn],
            }));
        }
        // ─────────────────────────────────────────────────────────────
        // 5. IAM ロール (API)
        // ─────────────────────────────────────────────────────────────
        const apiRole = new aws_cdk_lib_1.aws_iam.Role(this, 'NkflowApiRole', {
            assumedBy: new aws_cdk_lib_1.aws_iam.ServicePrincipal('lambda.amazonaws.com'),
            managedPolicies: [
                aws_cdk_lib_1.aws_iam.ManagedPolicy.fromAwsManagedPolicyName('service-role/AWSLambdaBasicExecutionRole'),
            ],
        });
        dataBucket.grantRead(apiRole);
        frontendBucket.grantRead(apiRole);
        // ─────────────────────────────────────────────────────────────
        // 6. IAM ロール / Lambda (通知) — prod のみ (Phase 12)
        // ─────────────────────────────────────────────────────────────
        if (isProd && notificationTopic) {
            const notificationRole = new aws_cdk_lib_1.aws_iam.Role(this, 'NkflowNotificationRole', {
                assumedBy: new aws_cdk_lib_1.aws_iam.ServicePrincipal('lambda.amazonaws.com'),
                managedPolicies: [
                    aws_cdk_lib_1.aws_iam.ManagedPolicy.fromAwsManagedPolicyName('service-role/AWSLambdaBasicExecutionRole'),
                ],
            });
            notificationRole.addToPolicy(new aws_cdk_lib_1.aws_iam.PolicyStatement({
                actions: ['ssm:GetParameter'],
                resources: [
                    `arn:aws:ssm:${this.region}:${this.account}:parameter${ssmPrefix}/slack-webhook-url`,
                    `arn:aws:ssm:${this.region}:${this.account}:parameter${ssmPrefix}/line-notify-token`,
                ],
            }));
            const notificationLambda = new aws_cdk_lib_1.aws_lambda.DockerImageFunction(this, 'NkflowNotificationLambda', {
                functionName: `nkflow-notification-${suffix}`,
                code: aws_cdk_lib_1.aws_lambda.DockerImageCode.fromImageAsset(DATALAKE, {
                    file: 'Dockerfile.notification',
                    platform: aws_ecr_assets_1.Platform.LINUX_AMD64,
                }),
                memorySize: 256,
                timeout: aws_cdk_lib_1.Duration.seconds(30),
                role: notificationRole,
                environment: {
                    SSM_PREFIX: ssmPrefix,
                },
            });
            // SNS → Notification Lambda サブスクリプション
            notificationTopic.addSubscription(new aws_cdk_lib_1.aws_sns_subscriptions.LambdaSubscription(notificationLambda));
        }
        // ─────────────────────────────────────────────────────────────
        // 7. Lambda (バッチ) — Apple Silicon 対応で linux/amd64 を指定
        // ─────────────────────────────────────────────────────────────
        const batchEnv = {
            S3_BUCKET: dataBucket.bucketName,
            JQUANTS_PLAN: 'standard',
            SSM_PREFIX: ssmPrefix,
        };
        if (notificationTopic) {
            batchEnv.SNS_TOPIC_ARN = notificationTopic.topicArn;
        }
        const batchLambda = new aws_cdk_lib_1.aws_lambda.DockerImageFunction(this, 'NkflowBatchLambda', {
            functionName: `nkflow-batch-${suffix}`,
            code: aws_cdk_lib_1.aws_lambda.DockerImageCode.fromImageAsset(DATALAKE, {
                file: 'Dockerfile.batch',
                platform: aws_ecr_assets_1.Platform.LINUX_AMD64,
            }),
            memorySize: 2048,
            timeout: aws_cdk_lib_1.Duration.seconds(900),
            // [IMPORTANT] stocks.db は ~1GB。S3 ダウンロード中に既存ファイル + temp ファイルで
            // 2x の容量が必要なため 2048MB 未満に下げると "No space left on device" になる。
            // Claude Code はこの値を削減しないこと。
            ephemeralStorageSize: cdk.Size.mebibytes(2048),
            role: batchRole,
            environment: batchEnv,
        });
        // ─────────────────────────────────────────────────────────────
        // 8. Lambda (API) + Function URL
        // ─────────────────────────────────────────────────────────────
        const apiLambda = new aws_cdk_lib_1.aws_lambda.DockerImageFunction(this, 'NkflowApiLambda', {
            functionName: `nkflow-api-${suffix}`,
            code: aws_cdk_lib_1.aws_lambda.DockerImageCode.fromImageAsset(BACKEND, {
                file: 'Dockerfile.api',
                platform: aws_ecr_assets_1.Platform.LINUX_AMD64,
            }),
            memorySize: 512,
            timeout: aws_cdk_lib_1.Duration.seconds(30),
            // [IMPORTANT] stocks.db は ~1GB。S3 ダウンロード中に既存ファイル + temp ファイルで
            // 2x の容量が必要なため 2048MB 未満に下げると "No space left on device" になる。
            // Claude Code はこの値を削減しないこと。
            ephemeralStorageSize: cdk.Size.mebibytes(2048),
            role: apiRole,
            environment: {
                S3_BUCKET: dataBucket.bucketName,
                FRONTEND_BUCKET: frontendBucket.bucketName,
                // CACHE_BUST: Lambda 環境変数を手動更新する際に S3_BUCKET が消えるのを防ぐためここで管理する。
                // キャッシュを強制破棄したい場合はこの値を変更して cdk deploy する。
                CACHE_BUST: '1',
            },
        });
        const apiUrl = apiLambda.addFunctionUrl({
            authType: aws_cdk_lib_1.aws_lambda.FunctionUrlAuthType.NONE,
            cors: {
                allowedOrigins: ['*'],
                allowedMethods: [aws_cdk_lib_1.aws_lambda.HttpMethod.GET],
            },
        });
        // ─────────────────────────────────────────────────────────────
        // 9. IAM ロール / Lambda / Scheduler (news-fetch) — Phase 18
        // ─────────────────────────────────────────────────────────────
        const newsFetchRole = new aws_cdk_lib_1.aws_iam.Role(this, 'NkflowNewsFetchRole', {
            assumedBy: new aws_cdk_lib_1.aws_iam.ServicePrincipal('lambda.amazonaws.com'),
            managedPolicies: [
                aws_cdk_lib_1.aws_iam.ManagedPolicy.fromAwsManagedPolicyName('service-role/AWSLambdaBasicExecutionRole'),
            ],
        });
        // news/raw/* への読み書きのみ許可
        newsFetchRole.addToPolicy(new aws_cdk_lib_1.aws_iam.PolicyStatement({
            actions: ['s3:PutObject', 's3:GetObject'],
            resources: [`${dataBucket.bucketArn}/news/raw/*`],
        }));
        // stocks.db の読み書き (ニュース正規化で使用)
        newsFetchRole.addToPolicy(new aws_cdk_lib_1.aws_iam.PolicyStatement({
            actions: ['s3:GetObject', 's3:PutObject'],
            resources: [`${dataBucket.bucketArn}/data/stocks.db`],
        }));
        // 英語記事の日本語翻訳 (Amazon Translate)
        newsFetchRole.addToPolicy(new aws_cdk_lib_1.aws_iam.PolicyStatement({
            actions: ['translate:TranslateText'],
            resources: ['*'],
        }));
        // 全クエリ失敗時の SNS 通知 (prod のみ)
        if (notificationTopic) {
            newsFetchRole.addToPolicy(new aws_cdk_lib_1.aws_iam.PolicyStatement({
                actions: ['sns:Publish'],
                resources: [notificationTopic.topicArn],
            }));
        }
        const newsFetchEnv = {
            S3_BUCKET: dataBucket.bucketName,
            SSM_PREFIX: ssmPrefix,
        };
        if (notificationTopic) {
            newsFetchEnv.SNS_TOPIC_ARN = notificationTopic.topicArn;
        }
        const newsFetchLambda = new aws_cdk_lib_1.aws_lambda.DockerImageFunction(this, 'NkflowNewsFetchLambda', {
            functionName: `nkflow-news-fetch-${suffix}`,
            code: aws_cdk_lib_1.aws_lambda.DockerImageCode.fromImageAsset(DATALAKE, {
                file: 'Dockerfile.news',
                platform: aws_ecr_assets_1.Platform.LINUX_AMD64,
            }),
            memorySize: 512,
            timeout: aws_cdk_lib_1.Duration.seconds(300),
            // [IMPORTANT] stocks.db は 500MB+ になるため /tmp に余裕が必要。
            // 3072MB 未満に減らすと "No space left on device" で正規化が失敗する。
            ephemeralStorageSize: cdk.Size.mebibytes(3072),
            role: newsFetchRole,
            environment: newsFetchEnv,
        });
        // EventBridge Scheduler: 毎時 30 分 (バッチ UTC 09:00 との競合を避けるため :30)
        const newsFetchSchedulerRole = new aws_cdk_lib_1.aws_iam.Role(this, 'NkflowNewsFetchSchedulerRole', {
            assumedBy: new aws_cdk_lib_1.aws_iam.ServicePrincipal('scheduler.amazonaws.com'),
        });
        newsFetchLambda.grantInvoke(newsFetchSchedulerRole);
        new aws_cdk_lib_1.aws_scheduler.CfnSchedule(this, 'NkflowNewsFetchSchedule', {
            name: `nkflow-news-fetch-${suffix}`,
            scheduleExpression: 'cron(30 * ? * * *)',
            scheduleExpressionTimezone: 'UTC',
            flexibleTimeWindow: { mode: 'OFF' },
            target: {
                arn: newsFetchLambda.functionArn,
                roleArn: newsFetchSchedulerRole.roleArn,
                input: JSON.stringify({}),
            },
        });
        // ─────────────────────────────────────────────────────────────
        // 10. API Gateway REST API — フロントエンド + API を1つの URL で公開
        // ─────────────────────────────────────────────────────────────
        const restApi = new aws_cdk_lib_1.aws_apigateway.LambdaRestApi(this, 'NkflowApiGateway', {
            handler: apiLambda,
            proxy: true,
            restApiName: `nkflow-${suffix}`,
            binaryMediaTypes: ['*/*'],
            deployOptions: { stageName: 'prod' },
            endpointTypes: [aws_cdk_lib_1.aws_apigateway.EndpointType.REGIONAL],
        });
        // ─────────────────────────────────────────────────────────────
        // 11. カスタムドメイン — Route 53 + ACM + API GW
        // ─────────────────────────────────────────────────────────────
        // senken.app の Hosted Zone を参照
        const hostedZone = aws_cdk_lib_1.aws_route53.HostedZone.fromLookup(this, 'SenkenAppZone', {
            domainName: HOSTED_ZONE_DOMAIN,
        });
        // ACM 証明書 (REGIONAL エンドポイントなので同じリージョンで発行)
        const certificate = new aws_cdk_lib_1.aws_certificatemanager.Certificate(this, 'NkflowCertificate', {
            domainName,
            validation: aws_cdk_lib_1.aws_certificatemanager.CertificateValidation.fromDns(hostedZone),
        });
        // API Gateway カスタムドメイン
        const customDomain = new aws_cdk_lib_1.aws_apigateway.DomainName(this, 'NkflowCustomDomain', {
            domainName,
            certificate,
            endpointType: aws_cdk_lib_1.aws_apigateway.EndpointType.REGIONAL,
            securityPolicy: aws_cdk_lib_1.aws_apigateway.SecurityPolicy.TLS_1_2,
        });
        // カスタムドメイン → prod ステージのマッピング
        new aws_cdk_lib_1.aws_apigateway.BasePathMapping(this, 'NkflowBasePathMapping', {
            domainName: customDomain,
            restApi,
            stage: restApi.deploymentStage,
        });
        // Route 53: {domainName} → API GW カスタムドメイン
        new aws_cdk_lib_1.aws_route53.ARecord(this, 'NkflowARecord', {
            zone: hostedZone,
            recordName: domainName,
            target: aws_cdk_lib_1.aws_route53.RecordTarget.fromAlias(new aws_cdk_lib_1.aws_route53_targets.ApiGatewayDomain(customDomain)),
        });
        // ─────────────────────────────────────────────────────────────
        // 12. EventBridge Scheduler (毎営業日 UTC 09:00 = JST 18:00)
        // ─────────────────────────────────────────────────────────────
        const schedulerRole = new aws_cdk_lib_1.aws_iam.Role(this, 'NkflowSchedulerRole', {
            assumedBy: new aws_cdk_lib_1.aws_iam.ServicePrincipal('scheduler.amazonaws.com'),
        });
        batchLambda.grantInvoke(schedulerRole);
        new aws_cdk_lib_1.aws_scheduler.CfnSchedule(this, 'NkflowDailySchedule', {
            name: `nkflow-daily-batch-${suffix}`,
            scheduleExpression: 'cron(0 9 ? * MON-FRI *)',
            scheduleExpressionTimezone: 'UTC',
            flexibleTimeWindow: { mode: 'OFF' },
            target: {
                arn: batchLambda.functionArn,
                roleArn: schedulerRole.roleArn,
                input: JSON.stringify({}),
            },
        });
        // ─────────────────────────────────────────────────────────────
        // Outputs
        // ─────────────────────────────────────────────────────────────
        new cdk.CfnOutput(this, 'DataBucketName', { value: dataBucket.bucketName });
        new cdk.CfnOutput(this, 'FrontendBucketName', { value: frontendBucket.bucketName });
        new cdk.CfnOutput(this, 'ApiLambdaUrl', { value: apiUrl.url });
        new cdk.CfnOutput(this, 'FrontendUrl', {
            value: restApi.url,
            description: 'フロントエンド + API の公開 URL (API Gateway)',
        });
        new cdk.CfnOutput(this, 'CustomDomainUrl', {
            value: `https://${domainName}`,
            description: 'カスタムドメイン URL',
        });
        if (notificationTopic) {
            new cdk.CfnOutput(this, 'NotificationTopicArn', {
                value: notificationTopic.topicArn,
                description: 'SNS 通知トピック ARN (Phase 12)',
            });
        }
    }
}
exports.NkflowStack = NkflowStack;
