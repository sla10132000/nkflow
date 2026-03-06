import * as path from 'path';
import * as cdk from 'aws-cdk-lib';
import {
  aws_s3 as s3,
  aws_lambda as lambda,
  aws_iam as iam,
  aws_apigateway as apigateway,
  aws_scheduler as scheduler,
  aws_sns as sns,
  aws_sns_subscriptions as snsSubscriptions,
  aws_ssm as ssm,
  aws_route53 as route53,
  aws_route53_targets as route53Targets,
  aws_certificatemanager as acm,
  Duration,
  RemovalPolicy,
  Stack,
  StackProps,
} from 'aws-cdk-lib';
import { Platform } from 'aws-cdk-lib/aws-ecr-assets';
import { Construct } from 'constructs';

const DOMAIN_NAME = 'nkflow.senken.app';
const HOSTED_ZONE_DOMAIN = 'senken.app';

const BACKEND = path.join(__dirname, '../../backend');
// datalake is a shared module at repo root, not under nkflow/
const DATALAKE = path.join(__dirname, '../../../datalake');

export class NkflowStack extends Stack {
  constructor(scope: Construct, id: string, props?: StackProps) {
    super(scope, id, props);

    // ─────────────────────────────────────────────────────────────
    // 1. S3 Bucket
    // ─────────────────────────────────────────────────────────────
    const dataBucket = new s3.Bucket(this, 'NkflowDataBucket', {
      bucketName: `nkflow-data-${this.account}`,
      removalPolicy: RemovalPolicy.RETAIN,
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      versioned: true,
      lifecycleRules: [
        {
          // SQLite バックアップ: 非最新バージョンを7世代まで保持し、それ以上は削除
          prefix: 'data/stocks.db',
          noncurrentVersionExpiration: Duration.days(1),
          noncurrentVersionsToRetain: 7,
        },
      ],
    });

    // ─────────────────────────────────────────────────────────────
    // 2. SSM Parameter Store (枠のみ — 値は手動で SecureString に上書き)
    // ─────────────────────────────────────────────────────────────
    new ssm.StringParameter(this, 'JQuantsApiKeyParam', {
      parameterName: '/nkflow/jquants-api-key',
      stringValue: 'PLACEHOLDER_SET_MANUALLY',
    });

    // Phase 12: 通知先パラメータ (枠のみ — 値は手動で SecureString に上書き)
    new ssm.StringParameter(this, 'SlackWebhookUrlParam', {
      parameterName: '/nkflow/slack-webhook-url',
      stringValue: 'PLACEHOLDER_SET_MANUALLY',
      description: 'Slack Incoming Webhook URL (Phase 12)',
    });

    new ssm.StringParameter(this, 'LineNotifyTokenParam', {
      parameterName: '/nkflow/line-notify-token',
      stringValue: 'PLACEHOLDER_SET_MANUALLY',
      description: 'LINE Notify アクセストークン (Phase 12)',
    });

    // ─────────────────────────────────────────────────────────────
    // 3. SNS トピック (Phase 12)
    // ─────────────────────────────────────────────────────────────
    const notificationTopic = new sns.Topic(this, 'NkflowNotificationTopic', {
      topicName: 'nkflow-notifications',
      displayName: 'nkflow 日次レポート通知',
    });

    // ─────────────────────────────────────────────────────────────
    // 4. IAM ロール (バッチ)
    // ─────────────────────────────────────────────────────────────
    const batchRole = new iam.Role(this, 'NkflowBatchRole', {
      assumedBy: new iam.ServicePrincipal('lambda.amazonaws.com'),
      managedPolicies: [
        iam.ManagedPolicy.fromAwsManagedPolicyName('service-role/AWSLambdaBasicExecutionRole'),
      ],
    });
    dataBucket.grantReadWrite(batchRole);
    batchRole.addToPolicy(new iam.PolicyStatement({
      actions: ['ssm:GetParameter'],
      resources: [`arn:aws:ssm:${this.region}:${this.account}:parameter/nkflow/*`],
    }));
    // Phase 18: ニュース raw データ読み取り権限 (fetch_news.normalize_news で使用)
    batchRole.addToPolicy(new iam.PolicyStatement({
      actions: ['s3:GetObject'],
      resources: [`${dataBucket.bucketArn}/news/raw/*`],
    }));
    // Phase 12: SNS publish 権限
    batchRole.addToPolicy(new iam.PolicyStatement({
      actions: ['sns:Publish'],
      resources: [notificationTopic.topicArn],
    }));
    // Phase 18: AWS Translate 翻訳権限
    batchRole.addToPolicy(new iam.PolicyStatement({
      actions: ['translate:TranslateText'],
      resources: ['*'],
    }));

    // ─────────────────────────────────────────────────────────────
    // 5. IAM ロール (API)
    // ─────────────────────────────────────────────────────────────
    const apiRole = new iam.Role(this, 'NkflowApiRole', {
      assumedBy: new iam.ServicePrincipal('lambda.amazonaws.com'),
      managedPolicies: [
        iam.ManagedPolicy.fromAwsManagedPolicyName('service-role/AWSLambdaBasicExecutionRole'),
      ],
    });
    dataBucket.grantRead(apiRole);

    // ─────────────────────────────────────────────────────────────
    // 6. IAM ロール (通知 Lambda) — Phase 12
    // ─────────────────────────────────────────────────────────────
    const notificationRole = new iam.Role(this, 'NkflowNotificationRole', {
      assumedBy: new iam.ServicePrincipal('lambda.amazonaws.com'),
      managedPolicies: [
        iam.ManagedPolicy.fromAwsManagedPolicyName('service-role/AWSLambdaBasicExecutionRole'),
      ],
    });
    notificationRole.addToPolicy(new iam.PolicyStatement({
      actions: ['ssm:GetParameter'],
      resources: [
        `arn:aws:ssm:${this.region}:${this.account}:parameter/nkflow/slack-webhook-url`,
        `arn:aws:ssm:${this.region}:${this.account}:parameter/nkflow/line-notify-token`,
      ],
    }));

    // ─────────────────────────────────────────────────────────────
    // 7. Lambda (バッチ) — Apple Silicon 対応で linux/amd64 を指定
    // ─────────────────────────────────────────────────────────────
    const batchLambda = new lambda.DockerImageFunction(this, 'NkflowBatchLambda', {
      functionName: 'nkflow-batch',
      code: lambda.DockerImageCode.fromImageAsset(DATALAKE, {
        file: 'Dockerfile.batch',
        platform: Platform.LINUX_AMD64,
      }),
      memorySize: 2048,
      timeout: Duration.seconds(900),
      ephemeralStorageSize: cdk.Size.mebibytes(2048),
      role: batchRole,
      environment: {
        S3_BUCKET: dataBucket.bucketName,
        JQUANTS_PLAN: 'standard',
        SNS_TOPIC_ARN: notificationTopic.topicArn,
      },
    });

    // ─────────────────────────────────────────────────────────────
    // 8. Lambda (API) + Function URL
    // ─────────────────────────────────────────────────────────────
    const apiLambda = new lambda.DockerImageFunction(this, 'NkflowApiLambda', {
      functionName: 'nkflow-api',
      code: lambda.DockerImageCode.fromImageAsset(BACKEND, {
        file: 'Dockerfile.api',
        platform: Platform.LINUX_AMD64,
      }),
      memorySize: 512,
      timeout: Duration.seconds(30),
      ephemeralStorageSize: cdk.Size.mebibytes(2048),
      role: apiRole,
      environment: {
        S3_BUCKET: dataBucket.bucketName,
        // CACHE_BUST: Lambda 環境変数を手動更新する際に S3_BUCKET が消えるのを防ぐためここで管理する。
        // キャッシュを強制破棄したい場合はこの値を変更して cdk deploy する。
        CACHE_BUST: '1',
      },
    });

    const apiUrl = apiLambda.addFunctionUrl({
      authType: lambda.FunctionUrlAuthType.NONE,
      cors: {
        allowedOrigins: ['*'],
        allowedMethods: [lambda.HttpMethod.GET],
      },
    });

    // ─────────────────────────────────────────────────────────────
    // 9. IAM ロール / Lambda / Scheduler (news-fetch) — Phase 18
    // ─────────────────────────────────────────────────────────────
    const newsFetchRole = new iam.Role(this, 'NkflowNewsFetchRole', {
      assumedBy: new iam.ServicePrincipal('lambda.amazonaws.com'),
      managedPolicies: [
        iam.ManagedPolicy.fromAwsManagedPolicyName('service-role/AWSLambdaBasicExecutionRole'),
      ],
    });
    // news/raw/* への読み書きのみ許可
    newsFetchRole.addToPolicy(new iam.PolicyStatement({
      actions: ['s3:PutObject', 's3:GetObject'],
      resources: [`${dataBucket.bucketArn}/news/raw/*`],
    }));
    // stocks.db の読み書き (ニュース正規化で使用)
    newsFetchRole.addToPolicy(new iam.PolicyStatement({
      actions: ['s3:GetObject', 's3:PutObject'],
      resources: [`${dataBucket.bucketArn}/data/stocks.db`],
    }));
    // 英語記事の日本語翻訳 (Amazon Translate)
    newsFetchRole.addToPolicy(new iam.PolicyStatement({
      actions: ['translate:TranslateText'],
      resources: ['*'],
    }));
    // 全クエリ失敗時の SNS 通知
    newsFetchRole.addToPolicy(new iam.PolicyStatement({
      actions: ['sns:Publish'],
      resources: [notificationTopic.topicArn],
    }));

    const newsFetchLambda = new lambda.DockerImageFunction(this, 'NkflowNewsFetchLambda', {
      functionName: 'nkflow-news-fetch',
      code: lambda.DockerImageCode.fromImageAsset(DATALAKE, {
        file: 'Dockerfile.news',
        platform: Platform.LINUX_AMD64,
      }),
      memorySize: 512,
      timeout: Duration.seconds(300),
      // [IMPORTANT] stocks.db は 500MB+ になるため /tmp に余裕が必要。
      // 3072MB 未満に減らすと "No space left on device" で正規化が失敗する。
      ephemeralStorageSize: cdk.Size.mebibytes(3072),
      role: newsFetchRole,
      environment: {
        S3_BUCKET: dataBucket.bucketName,
        SNS_TOPIC_ARN: notificationTopic.topicArn,
      },
    });

    // EventBridge Scheduler: 毎時 30 分 (バッチ UTC 09:00 との競合を避けるため :30)
    const newsFetchSchedulerRole = new iam.Role(this, 'NkflowNewsFetchSchedulerRole', {
      assumedBy: new iam.ServicePrincipal('scheduler.amazonaws.com'),
    });
    newsFetchLambda.grantInvoke(newsFetchSchedulerRole);

    new scheduler.CfnSchedule(this, 'NkflowNewsFetchSchedule', {
      name: 'nkflow-news-fetch',
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
    // 10. Lambda (通知) — Phase 12
    // ─────────────────────────────────────────────────────────────

    const notificationLambda = new lambda.DockerImageFunction(this, 'NkflowNotificationLambda', {
      functionName: 'nkflow-notification',
      code: lambda.DockerImageCode.fromImageAsset(DATALAKE, {
        file: 'Dockerfile.notification',
        platform: Platform.LINUX_AMD64,
      }),
      memorySize: 256,
      timeout: Duration.seconds(30),
      role: notificationRole,
    });

    // SNS → Notification Lambda サブスクリプション
    notificationTopic.addSubscription(
      new snsSubscriptions.LambdaSubscription(notificationLambda)
    );

    // ─────────────────────────────────────────────────────────────
    // 10. API Gateway REST API — フロントエンド + API を1つの URL で公開
    // ─────────────────────────────────────────────────────────────
    const restApi = new apigateway.LambdaRestApi(this, 'NkflowApiGateway', {
      handler: apiLambda,
      proxy: true,
      restApiName: 'nkflow',
      binaryMediaTypes: ['*/*'],
      deployOptions: { stageName: 'prod' },
      endpointTypes: [apigateway.EndpointType.REGIONAL],
    });

    // ─────────────────────────────────────────────────────────────
    // 12. カスタムドメイン (nkflow.senken.app) — Route 53 + ACM + API GW
    // ─────────────────────────────────────────────────────────────

    // senken.app の Hosted Zone を参照
    const hostedZone = route53.HostedZone.fromLookup(this, 'SenkenAppZone', {
      domainName: HOSTED_ZONE_DOMAIN,
    });

    // ACM 証明書 (REGIONAL エンドポイントなので同じリージョンで発行)
    const certificate = new acm.Certificate(this, 'NkflowCertificate', {
      domainName: DOMAIN_NAME,
      validation: acm.CertificateValidation.fromDns(hostedZone),
    });

    // API Gateway カスタムドメイン
    const customDomain = new apigateway.DomainName(this, 'NkflowCustomDomain', {
      domainName: DOMAIN_NAME,
      certificate,
      endpointType: apigateway.EndpointType.REGIONAL,
      securityPolicy: apigateway.SecurityPolicy.TLS_1_2,
    });

    // カスタムドメイン → prod ステージのマッピング
    new apigateway.BasePathMapping(this, 'NkflowBasePathMapping', {
      domainName: customDomain,
      restApi,
      stage: restApi.deploymentStage,
    });

    // Route 53: nkflow.senken.app → API GW カスタムドメイン
    new route53.ARecord(this, 'NkflowARecord', {
      zone: hostedZone,
      recordName: DOMAIN_NAME,
      target: route53.RecordTarget.fromAlias(
        new route53Targets.ApiGatewayDomain(customDomain)
      ),
    });

    // ─────────────────────────────────────────────────────────────
    // 11. EventBridge Scheduler (毎営業日 UTC 09:00 = JST 18:00)
    // ─────────────────────────────────────────────────────────────
    const schedulerRole = new iam.Role(this, 'NkflowSchedulerRole', {
      assumedBy: new iam.ServicePrincipal('scheduler.amazonaws.com'),
    });
    batchLambda.grantInvoke(schedulerRole);

    new scheduler.CfnSchedule(this, 'NkflowDailySchedule', {
      name: 'nkflow-daily-batch',
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
    new cdk.CfnOutput(this, 'ApiLambdaUrl', { value: apiUrl.url });
    new cdk.CfnOutput(this, 'FrontendUrl', {
      value: restApi.url,
      description: 'フロントエンド + API の公開 URL (API Gateway)',
    });
    new cdk.CfnOutput(this, 'CustomDomainUrl', {
      value: `https://${DOMAIN_NAME}`,
      description: 'カスタムドメイン URL',
    });
    new cdk.CfnOutput(this, 'NotificationTopicArn', {
      value: notificationTopic.topicArn,
      description: 'SNS 通知トピック ARN (Phase 12)',
    });
  }
}
