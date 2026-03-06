import * as path from "path";
import * as cdk from "aws-cdk-lib";
import {
  aws_s3 as s3,
  aws_lambda as lambda,
  aws_iam as iam,
  aws_apigateway as apigateway,
  aws_ssm as ssm,
  Duration,
  RemovalPolicy,
  Stack,
  StackProps,
} from "aws-cdk-lib";
import { Platform } from "aws-cdk-lib/aws-ecr-assets";
import { Construct } from "constructs";

const BACKEND = path.join(__dirname, "../../backend");

export class HazardBriefStack extends Stack {
  constructor(scope: Construct, id: string, props?: StackProps) {
    super(scope, id, props);

    // ─────────────────────────────────────────────────────────────
    // 1. S3 Bucket
    // ─────────────────────────────────────────────────────────────
    const dataBucket = new s3.Bucket(this, "HazardBriefDataBucket", {
      bucketName: `hazardbrief-data-${this.account}`,
      removalPolicy: RemovalPolicy.RETAIN,
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      versioned: true,
      lifecycleRules: [
        {
          // SQLite バックアップ: 非最新バージョンを7世代まで保持
          prefix: "data/hazardbrief.db",
          noncurrentVersionExpiration: Duration.days(1),
          noncurrentVersionsToRetain: 7,
        },
      ],
    });

    // ─────────────────────────────────────────────────────────────
    // 2. SSM Parameter Store (値は手動で設定が必要)
    // ─────────────────────────────────────────────────────────────
    new ssm.StringParameter(this, "Auth0DomainParam", {
      parameterName: "/hazardbrief/auth0-domain",
      stringValue: "PLACEHOLDER_SET_MANUALLY",
      description: "Auth0 テナントドメイン (例: xxx.auth0.com)",
    });

    new ssm.StringParameter(this, "Auth0AudienceParam", {
      parameterName: "/hazardbrief/auth0-audience",
      stringValue: "PLACEHOLDER_SET_MANUALLY",
      description: "Auth0 API Audience",
    });

    new ssm.StringParameter(this, "ReinfolibApiKeyParam", {
      parameterName: "/hazardbrief/reinfolib-api-key",
      stringValue: "PLACEHOLDER_SET_MANUALLY",
      description: "国土交通省 不動産情報ライブラリ API キー",
    });

    // ─────────────────────────────────────────────────────────────
    // 3. IAM ロール (API Lambda)
    // ─────────────────────────────────────────────────────────────
    const apiRole = new iam.Role(this, "HazardBriefApiRole", {
      assumedBy: new iam.ServicePrincipal("lambda.amazonaws.com"),
      managedPolicies: [
        iam.ManagedPolicy.fromAwsManagedPolicyName(
          "service-role/AWSLambdaBasicExecutionRole"
        ),
      ],
    });

    // S3 の読み書き権限 (ハザードレポートキャッシュ更新のため書き込みも必要)
    dataBucket.grantReadWrite(apiRole);

    // SSM パラメータ読み取り権限
    apiRole.addToPolicy(
      new iam.PolicyStatement({
        actions: ["ssm:GetParameter"],
        resources: [
          `arn:aws:ssm:${this.region}:${this.account}:parameter/hazardbrief/*`,
        ],
      })
    );

    // ─────────────────────────────────────────────────────────────
    // 4. Lambda (API) — Dockerfile.api でビルド
    // ─────────────────────────────────────────────────────────────
    const apiLambda = new lambda.DockerImageFunction(
      this,
      "HazardBriefApiLambda",
      {
        functionName: "hazardbrief-api",
        code: lambda.DockerImageCode.fromImageAsset(BACKEND, {
          file: "Dockerfile.api",
          platform: Platform.LINUX_AMD64,
        }),
        memorySize: 512,
        timeout: Duration.seconds(30),
        ephemeralStorageSize: cdk.Size.mebibytes(512),
        role: apiRole,
        environment: {
          S3_BUCKET: dataBucket.bucketName,
          CACHE_BUST: "1",
        },
      }
    );

    // Function URL (CORS設定付き)
    const apiUrl = apiLambda.addFunctionUrl({
      authType: lambda.FunctionUrlAuthType.NONE,
      cors: {
        allowedOrigins: ["*"],
        allowedMethods: [
          lambda.HttpMethod.GET,
          lambda.HttpMethod.POST,
          lambda.HttpMethod.DELETE,
          lambda.HttpMethod.PUT,
        ],
        allowedHeaders: ["*"],
      },
    });

    // ─────────────────────────────────────────────────────────────
    // 5. API Gateway REST API
    // ─────────────────────────────────────────────────────────────
    const restApi = new apigateway.LambdaRestApi(
      this,
      "HazardBriefApiGateway",
      {
        handler: apiLambda,
        proxy: true,
        restApiName: "hazardbrief",
        binaryMediaTypes: ["*/*"],
        deployOptions: { stageName: "prod" },
        endpointTypes: [apigateway.EndpointType.REGIONAL],
      }
    );

    // ─────────────────────────────────────────────────────────────
    // Outputs
    // ─────────────────────────────────────────────────────────────
    new cdk.CfnOutput(this, "DataBucketName", {
      value: dataBucket.bucketName,
      description: "HazardBrief データバケット名",
    });

    new cdk.CfnOutput(this, "ApiLambdaUrl", {
      value: apiUrl.url,
      description: "Lambda Function URL",
    });

    new cdk.CfnOutput(this, "FrontendUrl", {
      value: restApi.url,
      description: "フロントエンド + API の公開 URL (API Gateway)",
    });

    new cdk.CfnOutput(this, "FrontendBucketName", {
      value: dataBucket.bucketName,
      description: "フロントエンドデプロイ先バケット名 (frontend/ プレフィックス)",
    });
  }
}
