#!/usr/bin/env node
import 'source-map-support/register';
import * as cdk from 'aws-cdk-lib';
import { NkflowStack } from '../lib/nkflow-stack';

const app = new cdk.App();
const envName = (app.node.tryGetContext('env') as 'dev' | 'prod') || 'prod';

new NkflowStack(app, `NkflowStack-${envName}`, {
  env: {
    account: process.env.CDK_DEFAULT_ACCOUNT,
    region: process.env.CDK_DEFAULT_REGION ?? 'ap-northeast-1',
  },
  envName,
});
