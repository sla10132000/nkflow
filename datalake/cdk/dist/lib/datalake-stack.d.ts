import { Stack, StackProps } from 'aws-cdk-lib';
import { Construct } from 'constructs';
export interface DatalakeStackProps extends StackProps {
    envName: 'dev' | 'prod';
}
export declare class DatalakeStack extends Stack {
    constructor(scope: Construct, id: string, props: DatalakeStackProps);
}
