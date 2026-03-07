import * as cdk from 'aws-cdk-lib';
import {
  aws_s3 as s3,
  Duration,
  RemovalPolicy,
  Stack,
  StackProps,
} from 'aws-cdk-lib';
import { Construct } from 'constructs';

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
    // Outputs
    // ─────────────────────────────────────────────────────────────
    new cdk.CfnOutput(this, 'BucketName', { value: dataBucket.bucketName });
    new cdk.CfnOutput(this, 'BucketArn', { value: dataBucket.bucketArn });
  }
}
