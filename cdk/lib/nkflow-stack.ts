import * as path from 'path';
import * as cdk from 'aws-cdk-lib';
import {
  aws_s3 as s3,
  aws_lambda as lambda,
  aws_iam as iam,
  aws_apigateway as apigateway,
  aws_scheduler as scheduler,
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
      versioned: false,
    });

    // ─────────────────────────────────────────────────────────────
    // 2. SSM Parameter Store (枠のみ — 値は手動で SecureString に上書き)
    // ─────────────────────────────────────────────────────────────
    new ssm.StringParameter(this, 'JQuantsApiKeyParam', {
      parameterName: '/nkflow/jquants-api-key',
      stringValue: 'PLACEHOLDER_SET_MANUALLY',
    });

    // ─────────────────────────────────────────────────────────────
    // 3. IAM ロール (バッチ)
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

    // ─────────────────────────────────────────────────────────────
    // 4. IAM ロール (API)
    // ─────────────────────────────────────────────────────────────
    const apiRole = new iam.Role(this, 'NkflowApiRole', {
      assumedBy: new iam.ServicePrincipal('lambda.amazonaws.com'),
      managedPolicies: [
        iam.ManagedPolicy.fromAwsManagedPolicyName('service-role/AWSLambdaBasicExecutionRole'),
      ],
    });
    dataBucket.grantRead(apiRole);

    // ─────────────────────────────────────────────────────────────
    // 5. Lambda (バッチ) — Apple Silicon 対応で linux/amd64 を指定
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
        JQUANTS_PLAN: 'free',
      },
    });

    // ─────────────────────────────────────────────────────────────
    // 6. Lambda (API) + Function URL
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
    // 7. API Gateway REST API — フロントエンド + API を1つの URL で公開
    // ─────────────────────────────────────────────────────────────
    const restApi = new apigateway.LambdaRestApi(this, 'NkflowApiGateway', {
      handler: apiLambda,
      proxy: true,
      restApiName: 'nkflow',
      binaryMediaTypes: ['*/*'],
      deployOptions: { stageName: 'prod' },
    });

    // ─────────────────────────────────────────────────────────────
    // 8. EventBridge Scheduler (毎営業日 UTC 09:00 = JST 18:00)
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
  }
}
