import { Stack, StackProps } from 'aws-cdk-lib';
import { Construct } from 'constructs';
export interface NkflowStackProps extends StackProps {
    envName: 'dev' | 'prod';
}
export declare class NkflowStack extends Stack {
    constructor(scope: Construct, id: string, props: NkflowStackProps);
}
