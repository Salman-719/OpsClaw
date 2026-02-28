"""
CDK Stack — Conut AI Operations Pipeline
=========================================
Defines all AWS resources:
  - S3 bucket  (raw input + processed + results)
  - DynamoDB table  (forecast results for agent queries)
  - Lambda functions  (ETL + Forecast, Docker-based)
  - Step Functions state machine  (ETL → Forecast chain)
  - S3 event trigger  (auto-kicks pipeline on CSV upload)
"""

from __future__ import annotations

from pathlib import Path

import aws_cdk as cdk
from aws_cdk import (
    Duration,
    RemovalPolicy,
    Stack,
    aws_dynamodb as dynamodb,
    aws_lambda as _lambda,
    aws_s3 as s3,
    aws_s3_notifications as s3n,
    aws_stepfunctions as sfn,
    aws_stepfunctions_tasks as tasks,
)
from constructs import Construct

# Path to project root (parent of infra/)
PROJECT_ROOT = Path(__file__).resolve().parent.parent


class ConutPipelineStack(Stack):
    """Single-stack deployment for the Conut data pipeline."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        env_name: str = "dev",
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        project = "conut-ops"

        # ── S3 Bucket ────────────────────────────────────────────────────
        data_bucket = s3.Bucket(
            self,
            "DataBucket",
            bucket_name=f"{project}-data-{env_name}",
            versioned=True,
            removal_policy=RemovalPolicy.RETAIN if env_name == "prod" else RemovalPolicy.DESTROY,
            auto_delete_objects=(env_name != "prod"),
            lifecycle_rules=[
                s3.LifecycleRule(
                    id="ExpireOldVersions",
                    noncurrent_version_expiration=Duration.days(30),
                ),
            ],
        )

        # ── DynamoDB Table ───────────────────────────────────────────────
        forecast_table = dynamodb.Table(
            self,
            "ForecastTable",
            table_name=f"{project}-forecast-{env_name}",
            partition_key=dynamodb.Attribute(
                name="pk", type=dynamodb.AttributeType.STRING   # "branch#scenario"
            ),
            sort_key=dynamodb.Attribute(
                name="sk", type=dynamodb.AttributeType.STRING   # "period#1"
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.DESTROY if env_name != "prod" else RemovalPolicy.RETAIN,
        )

        # ── Shared Lambda environment ────────────────────────────────────
        common_env = {
            "S3_BUCKET": data_bucket.bucket_name,
            "S3_INPUT_PREFIX": "input/",
            "S3_PROCESSED_PREFIX": "processed/",
            "S3_RESULTS_PREFIX": "results/forecast/",
            "DYNAMODB_TABLE": forecast_table.table_name,
        }

        # ── ETL Lambda (Docker image) ───────────────────────────────────
        etl_fn = _lambda.DockerImageFunction(
            self,
            "EtlFunction",
            function_name=f"{project}-etl-{env_name}",
            code=_lambda.DockerImageCode.from_image_asset(
                directory=str(PROJECT_ROOT),
                file="infra/Dockerfile",
                target="etl",
            ),
            timeout=Duration.minutes(15),
            memory_size=1024,
            environment=common_env,
        )

        # ── Forecast Lambda (Docker image) ──────────────────────────────
        forecast_fn = _lambda.DockerImageFunction(
            self,
            "ForecastFunction",
            function_name=f"{project}-forecast-{env_name}",
            code=_lambda.DockerImageCode.from_image_asset(
                directory=str(PROJECT_ROOT),
                file="infra/Dockerfile",
                target="forecast",
            ),
            timeout=Duration.minutes(15),
            memory_size=1024,
            environment=common_env,
        )

        # ── IAM: grant S3 + DynamoDB access ─────────────────────────────
        data_bucket.grant_read_write(etl_fn)
        data_bucket.grant_read_write(forecast_fn)
        forecast_table.grant_read_write_data(forecast_fn)

        # ── Step Functions: ETL → Forecast pipeline ──────────────────────
        etl_task = tasks.LambdaInvoke(
            self,
            "RunETL",
            lambda_function=etl_fn,
            payload=sfn.TaskInput.from_object(
                {
                    "s3_bucket": data_bucket.bucket_name,
                    "s3_input_prefix": "input/",
                    "s3_output_prefix": "processed/",
                }
            ),
            result_path="$.etl_result",
            output_path="$",
        )

        forecast_task = tasks.LambdaInvoke(
            self,
            "RunForecast",
            lambda_function=forecast_fn,
            payload=sfn.TaskInput.from_object(
                {
                    "s3_bucket": data_bucket.bucket_name,
                    "s3_processed_prefix": "processed/",
                    "s3_results_prefix": "results/forecast/",
                    "dynamodb_table": forecast_table.table_name,
                }
            ),
            result_path="$.forecast_result",
            output_path="$",
        )

        pipeline_chain = etl_task.next(forecast_task)

        state_machine = sfn.StateMachine(
            self,
            "PipelineStateMachine",
            state_machine_name=f"{project}-pipeline-{env_name}",
            definition_body=sfn.DefinitionBody.from_chainable(pipeline_chain),
            timeout=Duration.minutes(30),
        )

        # ── S3 event: auto-trigger ETL on CSV upload ─────────────────────
        data_bucket.add_event_notification(
            s3.EventType.OBJECT_CREATED,
            s3n.LambdaDestination(etl_fn),
            s3.NotificationKeyFilter(prefix="input/", suffix=".csv"),
        )

        # ── Outputs ──────────────────────────────────────────────────────
        cdk.CfnOutput(self, "DataBucketName", value=data_bucket.bucket_name)
        cdk.CfnOutput(self, "ForecastTableName", value=forecast_table.table_name)
        cdk.CfnOutput(self, "EtlFunctionArn", value=etl_fn.function_arn)
        cdk.CfnOutput(self, "ForecastFunctionArn", value=forecast_fn.function_arn)
        cdk.CfnOutput(self, "StateMachineArn", value=state_machine.state_machine_arn)
