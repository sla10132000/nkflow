#!/usr/bin/env node
import * as cdk from 'aws-cdk-lib';
import { DatalakeStack } from '../lib/datalake-stack';

const app = new cdk.App();
const envName = (app.node.tryGetContext('env') as 'dev' | 'prod') || 'prod';

new DatalakeStack(app, `DatalakeStack-${envName}`, {
  env: {
    account: process.env.CDK_DEFAULT_ACCOUNT,
    region: process.env.CDK_DEFAULT_REGION ?? 'ap-northeast-1',
  },
  envName,
});
