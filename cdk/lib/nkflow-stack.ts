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
  Duration,
  RemovalPolicy,
  Stack,
  StackProps,
} from 'aws-cdk-lib';
import { Platform } from 'aws-cdk-lib/aws-ecr-assets';
import { Construct } from 'constructs';

const BACKEND = path.join(__dirname, '../../backend');

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
    // Phase 12: SNS publish 権限
    batchRole.addToPolicy(new iam.PolicyStatement({
      actions: ['sns:Publish'],
      resources: [notificationTopic.topicArn],
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
      code: lambda.DockerImageCode.fromImageAsset(BACKEND, {
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
    // 9. Lambda (通知) — Phase 12
    // ─────────────────────────────────────────────────────────────
    const notificationLambda = new lambda.DockerImageFunction(this, 'NkflowNotificationLambda', {
      functionName: 'nkflow-notification',
      code: lambda.DockerImageCode.fromImageAsset(BACKEND, {
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
    new cdk.CfnOutput(this, 'NotificationTopicArn', {
      value: notificationTopic.topicArn,
      description: 'SNS 通知トピック ARN (Phase 12)',
    });
  }
}
