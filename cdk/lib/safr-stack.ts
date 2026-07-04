import * as cdk from "aws-cdk-lib";
import * as lambda from "aws-cdk-lib/aws-lambda";
import * as apigateway from "aws-cdk-lib/aws-apigateway";
import * as dynamodb from "aws-cdk-lib/aws-dynamodb";
import * as s3 from "aws-cdk-lib/aws-s3";
import * as iam from "aws-cdk-lib/aws-iam";
import * as logs from "aws-cdk-lib/aws-logs";
import * as cloudwatch from "aws-cdk-lib/aws-cloudwatch";
import { Construct } from "constructs";
import * as path from "path";

export class SafrStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    // ============================================================
    // SAFR Component 3: Controls Repository (DynamoDB)
    // ============================================================
    const controlsTable = new dynamodb.Table(this, "ControlsTable", {
      tableName: "safr-controls",
      partitionKey: { name: "control_id", type: dynamodb.AttributeType.STRING },
      billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
      pointInTimeRecoverySpecification: {
        pointInTimeRecoveryEnabled: true,
      },
      encryption: dynamodb.TableEncryption.AWS_MANAGED,
    });

    // ============================================================
    // SAFR Component 2: Agent Identity Registry (DynamoDB)
    // ============================================================
    const agentsTable = new dynamodb.Table(this, "AgentsTable", {
      tableName: "safr-agents",
      partitionKey: { name: "agent_id", type: dynamodb.AttributeType.STRING },
      billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
      pointInTimeRecoverySpecification: {
        pointInTimeRecoveryEnabled: true,
      },
      encryption: dynamodb.TableEncryption.AWS_MANAGED,
    });

    // ============================================================
    // SAFR Component 5: Audit Log (S3 with Object Lock)
    // ============================================================
    const auditBucket = new s3.Bucket(this, "AuditBucket", {
      bucketName: `safr-audit-log-${this.account}-${this.region}`,
      encryption: s3.BucketEncryption.KMS_MANAGED,
      enforceSSL: true,
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      removalPolicy: cdk.RemovalPolicy.RETAIN,
      versioned: true,
      objectOwnership: s3.ObjectOwnership.BUCKET_OWNER_ENFORCED,
      objectLockEnabled: true,
    });

    // Add Object Lock default retention (1 year, compliance mode)
    // Note: Object Lock configuration requires the bucket to exist first,
    // so we apply it via a custom resource approach.
    // For the prototype, the bucket is created with objectLockEnabled: true
    // and retention is set at object write time.

    // ============================================================
    // Shared Lambda layer: SAFR shared models + controls logic
    // ============================================================
    const sharedCode = lambda.Code.fromAsset(
      path.join(__dirname, "..", "..", "lambda")
    );

    // ============================================================
    // SAFR Component 1+4: Disposition Engine Lambda
    // ============================================================
    const engineLambda = new lambda.Function(this, "DispositionEngine", {
      functionName: "safr-disposition-engine",
      runtime: lambda.Runtime.PYTHON_3_11,
      architecture: lambda.Architecture.ARM_64,
      handler: "disposition_engine.index.lambda_handler",
      code: sharedCode,
      timeout: cdk.Duration.seconds(30),
      memorySize: 512,
      logRetention: logs.RetentionDays.ONE_WEEK,
      environment: {
        CONTROLS_TABLE: controlsTable.tableName,
        AGENTS_TABLE: agentsTable.tableName,
        AUDIT_BUCKET: auditBucket.bucketName,
        CORS_ORIGIN: process.env.CORS_ORIGIN ?? "",
      },
      tracing: lambda.Tracing.ACTIVE,
    });

    // Grant DynamoDB access
    controlsTable.grantReadData(engineLambda);
    agentsTable.grantReadData(engineLambda);
    auditBucket.grantWrite(engineLambda);

    // ============================================================
    // Seed Lambda: Populate initial controls + agents
    // ============================================================
    const seedLambda = new lambda.Function(this, "SeedControls", {
      functionName: "safr-seed-controls",
      runtime: lambda.Runtime.PYTHON_3_11,
      architecture: lambda.Architecture.ARM_64,
      handler: "seed_controls.index.lambda_handler",
      code: sharedCode,
      timeout: cdk.Duration.minutes(2),
      memorySize: 256,
      logRetention: logs.RetentionDays.ONE_WEEK,
      environment: {
        CONTROLS_TABLE: controlsTable.tableName,
        AGENTS_TABLE: agentsTable.tableName,
      },
    });

    controlsTable.grantWriteData(seedLambda);
    agentsTable.grantWriteData(seedLambda);

    // Custom Resource to trigger seed on deploy (deterministic — runs once)
    const seedProvider = new cdk.CustomResource(
      this,
      "SeedProvider",
      {
        serviceToken: seedLambda.functionArn,
        properties: { SeedVersion: "v1" },
      }
    );

    // ============================================================
    // API Gateway (REST API with API key)
    // ============================================================
    const api = new apigateway.RestApi(this, "SafrApi", {
      restApiName: "SAFR Governance API",
      description: "SAFR — Safeguards for Agentic Finance at Runtime",
      deployOptions: {
        stageName: "v1",
        throttlingRateLimit: 100,
        throttlingBurstLimit: 200,
        loggingLevel: apigateway.MethodLoggingLevel.INFO,
        dataTraceEnabled: true,
        metricsEnabled: true,
        tracingEnabled: true,
      },
      defaultCorsPreflightOptions: {
        allowOrigins: apigateway.Cors.ALL_ORIGINS,
        allowMethods: apigateway.Cors.ALL_METHODS,
        allowHeaders: ["Content-Type", "Authorization", "X-Api-Key"],
      },
      endpointConfiguration: { types: [apigateway.EndpointType.REGIONAL] },
    });

    // API Key for authentication
    const apiKey = api.addApiKey("SafrApiKey", {
      apiKeyName: "safr-api-key",
      description: "API key for SAFR Governance API",
    });

    const usagePlan = api.addUsagePlan("SafrUsagePlan", {
      name: "safr-usage-plan",
      throttle: {
        rateLimit: 100,
        burstLimit: 200,
      },
    });
    usagePlan.addApiKey(apiKey);
    usagePlan.addApiStage({ stage: api.deploymentStage });

    // POST /govern — the main SAFR evaluation endpoint
    const governResource = api.root.addResource("govern");
    governResource.addMethod("POST", new apigateway.LambdaIntegration(engineLambda), {
      apiKeyRequired: true,
      methodResponses: [
        { statusCode: "200" },
        { statusCode: "202" },
        { statusCode: "400" },
        { statusCode: "403" },
        { statusCode: "500" },
      ],
    });

    // GET /health — health check
    const healthResource = api.root.addResource("health");
    healthResource.addMethod("GET", new apigateway.LambdaIntegration(
      new lambda.Function(this, "HealthCheck", {
        runtime: lambda.Runtime.PYTHON_3_11,
        architecture: lambda.Architecture.ARM_64,
        handler: "index.handler",
        code: lambda.Code.fromInline(`
def handler(event, context):
    return {"statusCode": 200, "body": '{"status":"healthy","service":"safr-governance"}'}
`),
        timeout: cdk.Duration.seconds(5),
        memorySize: 128,
        logRetention: logs.RetentionDays.ONE_WEEK,
      })
    ), {
      apiKeyRequired: false,
    });

    // ============================================================
    // CloudWatch Dashboard
    // ============================================================
    const dashboard = new cloudwatch.Dashboard(this, "SafrDashboard", {
      dashboardName: "SAFR-Governance",
    });

    dashboard.addWidgets(
      new cloudwatch.GraphWidget({
        title: "SAFR Decisions by Outcome",
        left: [
          engineLambda.metricInvocations({
            label: "Total Evaluations",
            statistic: "Sum",
            period: cdk.Duration.minutes(5),
          }),
        ],
        width: 12,
        height: 6,
      }),
      new cloudwatch.GraphWidget({
        title: "Evaluation Latency",
        left: [
          engineLambda.metricDuration({
            label: "p50",
            statistic: "p50",
            period: cdk.Duration.minutes(5),
          }),
          engineLambda.metricDuration({
            label: "p99",
            statistic: "p99",
            period: cdk.Duration.minutes(5),
          }),
        ],
        width: 12,
        height: 6,
      }),
      new cloudwatch.GraphWidget({
        title: "Errors",
        left: [
          engineLambda.metricErrors({
            label: "Errors",
            statistic: "Sum",
            period: cdk.Duration.minutes(5),
          }),
        ],
        width: 12,
        height: 4,
      })
    );

    // Alarms
    new cloudwatch.Alarm(this, "HighErrorRate", {
      alarmName: "safr-high-error-rate",
      metric: engineLambda.metricErrors({ period: cdk.Duration.minutes(5) }),
      threshold: 5,
      evaluationPeriods: 3,
      datapointsToAlarm: 2,
      comparisonOperator: cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
    });

    // ============================================================
    // Outputs
    // ============================================================
    new cdk.CfnOutput(this, "ApiUrlOutput", {
      value: api.url,
      description: "SAFR Governance API URL",
      exportName: "safr-api-url",
    });

    new cdk.CfnOutput(this, "ApiKeyIdOutput", {
      value: apiKey.keyId,
      description: "API Key ID (retrieve value: aws apigateway get-api-key --api-key-id <id> --include-value)",
    });

    new cdk.CfnOutput(this, "AuditBucketOutput", {
      value: auditBucket.bucketName,
      description: "S3 Audit Log bucket",
    });

    new cdk.CfnOutput(this, "ControlsTableOutput", {
      value: controlsTable.tableName,
      description: "DynamoDB Controls Repository",
    });

    new cdk.CfnOutput(this, "AgentsTableOutput", {
      value: agentsTable.tableName,
      description: "DynamoDB Agent Identity Registry",
    });

    new cdk.CfnOutput(this, "DashboardOutput", {
      value: `https://${this.region}.console.aws.amazon.com/cloudwatch/home?region=${this.region}#dashboards:name=SAFR-Governance`,
      description: "CloudWatch Dashboard URL",
    });
  }
}
