import * as cdk from 'aws-cdk-lib';
import {
  aws_s3 as s3,
  aws_sqs as sqs,
  aws_lambda as lambda,
  aws_s3_notifications as s3n,
  aws_lambda_event_sources as lambdaEventSources,
  aws_iam as iam,
  aws_cloudwatch as cloudwatch,
  Duration,
  RemovalPolicy,
  Size,
  Stack,
  StackProps,
} from 'aws-cdk-lib';
import { Platform } from 'aws-cdk-lib/aws-ecr-assets';
import { Construct } from 'constructs';
import * as path from 'path';

export interface DatalakeStackProps extends StackProps {
  envName: 'dev' | 'prod';
}

export class DatalakeStack extends Stack {
  constructor(scope: Construct, id: string, props: DatalakeStackProps) {
    super(scope, id, props);

    const { envName } = props;

    // ─────────────────────────────────────────────────────────────
    // S3 Bucket — 共有データレイク
    // 複数サービス (nkflow, hazardbrief 等) が共用する
    // ─────────────────────────────────────────────────────────────
    const dataBucket = new s3.Bucket(this, 'DatalakeBucket', {
      bucketName: `senken-datalake-${envName}`,
      removalPolicy: RemovalPolicy.RETAIN,
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      versioned: true,
      lifecycleRules: [
        {
          // SQLite バックアップ: 非最新バージョンを7世代まで保持
          prefix: 'data/stocks.db',
          noncurrentVersionExpiration: Duration.days(1),
          noncurrentVersionsToRetain: 7,
        },
      ],
    });

    // ─────────────────────────────────────────────────────────────
    // SQS — raw イベントキュー
    // S3 PutObject (raw/**) → SQS → ingestor Lambda (直列処理)
    // ─────────────────────────────────────────────────────────────

    // DLQ: 3 回失敗したメッセージを保管 (14 日)
    const rawEventsDlq = new sqs.Queue(this, 'RawEventsDlq', {
      queueName: `datalake-raw-events-dlq-${envName}`,
      retentionPeriod: Duration.days(14),
      removalPolicy: RemovalPolicy.RETAIN,
    });

    // メインキュー: visibility timeout は Lambda timeout (900s) より大きく設定
    const rawEventsQueue = new sqs.Queue(this, 'RawEventsQueue', {
      queueName: `datalake-raw-events-${envName}`,
      visibilityTimeout: Duration.seconds(960),
      retentionPeriod: Duration.days(4),
      deadLetterQueue: {
        queue: rawEventsDlq,
        maxReceiveCount: 3,
      },
    });

    // S3 が SQS に SendMessage できるリソースポリシー
    rawEventsQueue.addToResourcePolicy(
      new iam.PolicyStatement({
        principals: [new iam.ServicePrincipal('s3.amazonaws.com')],
        actions: ['sqs:SendMessage'],
        resources: [rawEventsQueue.queueArn],
        conditions: {
          ArnLike: { 'aws:SourceArn': dataBucket.bucketArn },
        },
      }),
    );

    // ─────────────────────────────────────────────────────────────
    // Lambda — raw ingestor
    // reservedConcurrentExecutions: 1 で同時実行を 1 に制限し
    // stocks.db への書き込み競合を防ぐ
    // ─────────────────────────────────────────────────────────────
    const ingestorRole = new iam.Role(this, 'RawIngestorRole', {
      assumedBy: new iam.ServicePrincipal('lambda.amazonaws.com'),
      managedPolicies: [
        iam.ManagedPolicy.fromAwsManagedPolicyName(
          'service-role/AWSLambdaBasicExecutionRole',
        ),
      ],
    });

    // raw ファイル読み取り
    ingestorRole.addToPolicy(
      new iam.PolicyStatement({
        actions: ['s3:GetObject'],
        resources: [`${dataBucket.bucketArn}/raw/*`],
      }),
    );

    // stocks.db 読み書き
    ingestorRole.addToPolicy(
      new iam.PolicyStatement({
        actions: ['s3:GetObject', 's3:PutObject'],
        resources: [`${dataBucket.bucketArn}/data/stocks.db`],
      }),
    );

    // SQS メッセージ処理権限
    rawEventsQueue.grantConsumeMessages(ingestorRole);

    // __dirname は dist/lib/ (コンパイル後) のため、datalake/ ルートへは 3 階層上
    const datalakeSrcDir = path.join(__dirname, '../../../');

    const ingestorLambda = new lambda.DockerImageFunction(this, 'RawIngestorLambda', {
      functionName: `datalake-raw-ingestor-${envName}`,
      code: lambda.DockerImageCode.fromImageAsset(datalakeSrcDir, {
        file: 'Dockerfile.ingestor',
        platform: Platform.LINUX_AMD64,
        exclude: ['cdk/', 'cdk/**', '.venv/', '.venv/**'],
      }),
      memorySize: 2048,
      timeout: Duration.seconds(900),
      ephemeralStorageSize: Size.mebibytes(2048),
      role: ingestorRole,
      // 直列化の保証: 同時実行数を 1 に固定
      reservedConcurrentExecutions: 1,
      environment: {
        S3_BUCKET: dataBucket.bucketName,
      },
    });

    // SQS → Lambda トリガー (batchSize=1 で 1 メッセージずつ処理)
    ingestorLambda.addEventSource(
      new lambdaEventSources.SqsEventSource(rawEventsQueue, {
        batchSize: 1,
      }),
    );

    // ─────────────────────────────────────────────────────────────
    // S3 Event Notification — raw/** PutObject → SQS
    // ─────────────────────────────────────────────────────────────
    dataBucket.addEventNotification(
      s3.EventType.OBJECT_CREATED,
      new s3n.SqsDestination(rawEventsQueue),
      { prefix: 'raw/', suffix: '.json' },
    );

    // ─────────────────────────────────────────────────────────────
    // CloudWatch Alarm — DLQ に積まれたら通知
    // ─────────────────────────────────────────────────────────────
    new cloudwatch.Alarm(this, 'RawDlqAlarm', {
      alarmName: `datalake-raw-dlq-nonempty-${envName}`,
      metric: rawEventsDlq.metricApproximateNumberOfMessagesVisible(),
      threshold: 1,
      evaluationPeriods: 1,
      comparisonOperator: cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
      treatMissingData: cloudwatch.TreatMissingData.NOT_BREACHING,
    });

    // ─────────────────────────────────────────────────────────────
    // Outputs
    // ─────────────────────────────────────────────────────────────
    new cdk.CfnOutput(this, 'BucketName', { value: dataBucket.bucketName });
    new cdk.CfnOutput(this, 'BucketArn', { value: dataBucket.bucketArn });
    new cdk.CfnOutput(this, 'RawEventsQueueUrl', { value: rawEventsQueue.queueUrl });
    new cdk.CfnOutput(this, 'RawEventsDlqUrl', { value: rawEventsDlq.queueUrl });
    new cdk.CfnOutput(this, 'IngestorLambdaName', { value: ingestorLambda.functionName });
  }
}
