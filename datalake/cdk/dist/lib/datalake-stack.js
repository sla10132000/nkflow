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
exports.DatalakeStack = void 0;
const cdk = __importStar(require("aws-cdk-lib"));
const aws_cdk_lib_1 = require("aws-cdk-lib");
const aws_ecr_assets_1 = require("aws-cdk-lib/aws-ecr-assets");
const path = __importStar(require("path"));
class DatalakeStack extends aws_cdk_lib_1.Stack {
    constructor(scope, id, props) {
        super(scope, id, props);
        const { envName } = props;
        // ─────────────────────────────────────────────────────────────
        // S3 Bucket — 共有データレイク
        // 複数サービス (nkflow, hazardbrief 等) が共用する
        // ─────────────────────────────────────────────────────────────
        const dataBucket = new aws_cdk_lib_1.aws_s3.Bucket(this, 'DatalakeBucket', {
            bucketName: `senken-datalake-${envName}`,
            removalPolicy: aws_cdk_lib_1.RemovalPolicy.RETAIN,
            blockPublicAccess: aws_cdk_lib_1.aws_s3.BlockPublicAccess.BLOCK_ALL,
            versioned: true,
            lifecycleRules: [
                {
                    // SQLite バックアップ: 非最新バージョンを7世代まで保持
                    prefix: 'data/stocks.db',
                    noncurrentVersionExpiration: aws_cdk_lib_1.Duration.days(1),
                    noncurrentVersionsToRetain: 7,
                },
            ],
        });
        // ─────────────────────────────────────────────────────────────
        // SQS — raw イベントキュー
        // S3 PutObject (raw/**) → SQS → ingestor Lambda (直列処理)
        // ─────────────────────────────────────────────────────────────
        // DLQ: 3 回失敗したメッセージを保管 (14 日)
        const rawEventsDlq = new aws_cdk_lib_1.aws_sqs.Queue(this, 'RawEventsDlq', {
            queueName: `datalake-raw-events-dlq-${envName}`,
            retentionPeriod: aws_cdk_lib_1.Duration.days(14),
            removalPolicy: aws_cdk_lib_1.RemovalPolicy.RETAIN,
        });
        // メインキュー: visibility timeout は Lambda timeout (900s) より大きく設定
        const rawEventsQueue = new aws_cdk_lib_1.aws_sqs.Queue(this, 'RawEventsQueue', {
            queueName: `datalake-raw-events-${envName}`,
            visibilityTimeout: aws_cdk_lib_1.Duration.seconds(960),
            retentionPeriod: aws_cdk_lib_1.Duration.days(4),
            deadLetterQueue: {
                queue: rawEventsDlq,
                maxReceiveCount: 3,
            },
        });
        // S3 が SQS に SendMessage できるリソースポリシー
        rawEventsQueue.addToResourcePolicy(new aws_cdk_lib_1.aws_iam.PolicyStatement({
            principals: [new aws_cdk_lib_1.aws_iam.ServicePrincipal('s3.amazonaws.com')],
            actions: ['sqs:SendMessage'],
            resources: [rawEventsQueue.queueArn],
            conditions: {
                ArnLike: { 'aws:SourceArn': dataBucket.bucketArn },
            },
        }));
        // ─────────────────────────────────────────────────────────────
        // Lambda — raw ingestor
        // reservedConcurrentExecutions: 1 で同時実行を 1 に制限し
        // stocks.db への書き込み競合を防ぐ
        // ─────────────────────────────────────────────────────────────
        const ingestorRole = new aws_cdk_lib_1.aws_iam.Role(this, 'RawIngestorRole', {
            assumedBy: new aws_cdk_lib_1.aws_iam.ServicePrincipal('lambda.amazonaws.com'),
            managedPolicies: [
                aws_cdk_lib_1.aws_iam.ManagedPolicy.fromAwsManagedPolicyName('service-role/AWSLambdaBasicExecutionRole'),
            ],
        });
        // raw ファイル読み取り
        ingestorRole.addToPolicy(new aws_cdk_lib_1.aws_iam.PolicyStatement({
            actions: ['s3:GetObject'],
            resources: [`${dataBucket.bucketArn}/raw/*`],
        }));
        // stocks.db 読み書き
        ingestorRole.addToPolicy(new aws_cdk_lib_1.aws_iam.PolicyStatement({
            actions: ['s3:GetObject', 's3:PutObject'],
            resources: [`${dataBucket.bucketArn}/data/stocks.db`],
        }));
        // SQS メッセージ処理権限
        rawEventsQueue.grantConsumeMessages(ingestorRole);
        // __dirname は dist/lib/ (コンパイル後) のため、datalake/ ルートへは 3 階層上
        const datalakeSrcDir = path.join(__dirname, '../../../');
        const ingestorLambda = new aws_cdk_lib_1.aws_lambda.DockerImageFunction(this, 'RawIngestorLambda', {
            functionName: `datalake-raw-ingestor-${envName}`,
            code: aws_cdk_lib_1.aws_lambda.DockerImageCode.fromImageAsset(datalakeSrcDir, {
                file: 'Dockerfile.ingestor',
                platform: aws_ecr_assets_1.Platform.LINUX_AMD64,
            }),
            memorySize: 2048,
            timeout: aws_cdk_lib_1.Duration.seconds(900),
            ephemeralStorageSize: aws_cdk_lib_1.Size.mebibytes(2048),
            role: ingestorRole,
            // 直列化の保証: 同時実行数を 1 に固定
            reservedConcurrentExecutions: 1,
            environment: {
                S3_BUCKET: dataBucket.bucketName,
            },
        });
        // SQS → Lambda トリガー (batchSize=1 で 1 メッセージずつ処理)
        ingestorLambda.addEventSource(new aws_cdk_lib_1.aws_lambda_event_sources.SqsEventSource(rawEventsQueue, {
            batchSize: 1,
        }));
        // ─────────────────────────────────────────────────────────────
        // S3 Event Notification — raw/** PutObject → SQS
        // ─────────────────────────────────────────────────────────────
        dataBucket.addEventNotification(aws_cdk_lib_1.aws_s3.EventType.OBJECT_CREATED, new aws_cdk_lib_1.aws_s3_notifications.SqsDestination(rawEventsQueue), { prefix: 'raw/', suffix: '.json' });
        // ─────────────────────────────────────────────────────────────
        // CloudWatch Alarm — DLQ に積まれたら通知
        // ─────────────────────────────────────────────────────────────
        new aws_cdk_lib_1.aws_cloudwatch.Alarm(this, 'RawDlqAlarm', {
            alarmName: `datalake-raw-dlq-nonempty-${envName}`,
            metric: rawEventsDlq.metricApproximateNumberOfMessagesVisible(),
            threshold: 1,
            evaluationPeriods: 1,
            comparisonOperator: aws_cdk_lib_1.aws_cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
            treatMissingData: aws_cdk_lib_1.aws_cloudwatch.TreatMissingData.NOT_BREACHING,
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
exports.DatalakeStack = DatalakeStack;
