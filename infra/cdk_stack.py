"""
CDK Stack — Conut AI Operations Pipeline
=========================================
Defines all AWS resources:
  - S3 bucket  (raw input + processed + results)
  - DynamoDB tables  (forecast + combo + expansion + staffing + growth)
  - Lambda functions  (ETL + Forecast + Combo + Expansion + Staffing + Growth)
  - Step Functions state machine  (ETL → all 5 analytics in parallel)
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

        # ── DynamoDB: Forecast Table ─────────────────────────────────────
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

        # ── DynamoDB: Combo Table ────────────────────────────────────────
        combo_table = dynamodb.Table(
            self,
            "ComboTable",
            table_name=f"{project}-combo-{env_name}",
            partition_key=dynamodb.Attribute(
                name="pk", type=dynamodb.AttributeType.STRING   # scope (e.g. "overall", "branch:Conut Jnah")
            ),
            sort_key=dynamodb.Attribute(
                name="sk", type=dynamodb.AttributeType.STRING   # "item_a#item_b"
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.DESTROY if env_name != "prod" else RemovalPolicy.RETAIN,
        )

        # ── DynamoDB: Expansion Table ────────────────────────────────────
        expansion_table = dynamodb.Table(
            self,
            "ExpansionTable",
            table_name=f"{project}-expansion-{env_name}",
            partition_key=dynamodb.Attribute(
                name="pk", type=dynamodb.AttributeType.STRING   # branch or "recommendation"
            ),
            sort_key=dynamodb.Attribute(
                name="sk", type=dynamodb.AttributeType.STRING   # "kpi" | "feasibility" | "expansion"
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.DESTROY if env_name != "prod" else RemovalPolicy.RETAIN,
        )

        # ── DynamoDB: Staffing Table ─────────────────────────────────────
        staffing_table = dynamodb.Table(
            self,
            "StaffingTable",
            table_name=f"{project}-staffing-{env_name}",
            partition_key=dynamodb.Attribute(
                name="pk", type=dynamodb.AttributeType.STRING   # branch
            ),
            sort_key=dynamodb.Attribute(
                name="sk", type=dynamodb.AttributeType.STRING   # "findings" | "gap#<day>#<hour>"
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.DESTROY if env_name != "prod" else RemovalPolicy.RETAIN,
        )

        # ── DynamoDB: Growth Table ───────────────────────────────────────
        growth_table = dynamodb.Table(
            self,
            "GrowthTable",
            table_name=f"{project}-growth-{env_name}",
            partition_key=dynamodb.Attribute(
                name="pk", type=dynamodb.AttributeType.STRING   # branch or "recommendation"
            ),
            sort_key=dynamodb.Attribute(
                name="sk", type=dynamodb.AttributeType.STRING   # "growth_potential" | "beverage_kpi" | "rule#..." | "growth"
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
            "DYNAMODB_COMBO_TABLE": combo_table.table_name,
            "DYNAMODB_EXPANSION_TABLE": expansion_table.table_name,
            "DYNAMODB_STAFFING_TABLE": staffing_table.table_name,
            "DYNAMODB_GROWTH_TABLE": growth_table.table_name,
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

        # ── Combo Lambda (Docker image) ─────────────────────────────────
        combo_fn = _lambda.DockerImageFunction(
            self,
            "ComboFunction",
            function_name=f"{project}-combo-{env_name}",
            code=_lambda.DockerImageCode.from_image_asset(
                directory=str(PROJECT_ROOT),
                file="infra/Dockerfile",
                target="combo",
            ),
            timeout=Duration.minutes(15),
            memory_size=1024,
            environment=common_env,
        )

        # ── Expansion Lambda (Docker image) ─────────────────────────────
        expansion_fn = _lambda.DockerImageFunction(
            self,
            "ExpansionFunction",
            function_name=f"{project}-expansion-{env_name}",
            code=_lambda.DockerImageCode.from_image_asset(
                directory=str(PROJECT_ROOT),
                file="infra/Dockerfile",
                target="expansion",
            ),
            timeout=Duration.minutes(15),
            memory_size=1024,
            environment=common_env,
        )

        # ── Staffing Lambda (Docker image) ──────────────────────────────
        staffing_fn = _lambda.DockerImageFunction(
            self,
            "StaffingFunction",
            function_name=f"{project}-staffing-{env_name}",
            code=_lambda.DockerImageCode.from_image_asset(
                directory=str(PROJECT_ROOT),
                file="infra/Dockerfile",
                target="staffing",
            ),
            timeout=Duration.minutes(15),
            memory_size=1024,
            environment=common_env,
        )

        # ── Growth Lambda (Docker image) ────────────────────────────────
        growth_fn = _lambda.DockerImageFunction(
            self,
            "GrowthFunction",
            function_name=f"{project}-growth-{env_name}",
            code=_lambda.DockerImageCode.from_image_asset(
                directory=str(PROJECT_ROOT),
                file="infra/Dockerfile",
                target="growth",
            ),
            timeout=Duration.minutes(15),
            memory_size=1024,
            environment=common_env,
        )

        # ── IAM: grant S3 + DynamoDB access ─────────────────────────────
        for fn in [etl_fn, forecast_fn, combo_fn, expansion_fn, staffing_fn, growth_fn]:
            data_bucket.grant_read_write(fn)
        forecast_table.grant_read_write_data(forecast_fn)
        combo_table.grant_read_write_data(combo_fn)
        expansion_table.grant_read_write_data(expansion_fn)
        staffing_table.grant_read_write_data(staffing_fn)
        growth_table.grant_read_write_data(growth_fn)

        # ── Step Functions: ETL → (Forecast + Combo) in parallel ─────────
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

        combo_task = tasks.LambdaInvoke(
            self,
            "RunCombo",
            lambda_function=combo_fn,
            payload=sfn.TaskInput.from_object(
                {
                    "s3_bucket": data_bucket.bucket_name,
                    "s3_processed_prefix": "processed/",
                    "s3_results_prefix": "results/combo/",
                    "dynamodb_table": combo_table.table_name,
                }
            ),
            result_path="$.combo_result",
            output_path="$",
        )

        expansion_task = tasks.LambdaInvoke(
            self,
            "RunExpansion",
            lambda_function=expansion_fn,
            payload=sfn.TaskInput.from_object(
                {
                    "s3_bucket": data_bucket.bucket_name,
                    "s3_input_prefix": "input/",
                    "s3_results_prefix": "results/expansion/",
                    "dynamodb_table": expansion_table.table_name,
                }
            ),
            result_path="$.expansion_result",
            output_path="$",
        )

        staffing_task = tasks.LambdaInvoke(
            self,
            "RunStaffing",
            lambda_function=staffing_fn,
            payload=sfn.TaskInput.from_object(
                {
                    "s3_bucket": data_bucket.bucket_name,
                    "s3_processed_prefix": "processed/",
                    "s3_results_prefix": "results/staffing/",
                    "dynamodb_table": staffing_table.table_name,
                }
            ),
            result_path="$.staffing_result",
            output_path="$",
        )

        growth_task = tasks.LambdaInvoke(
            self,
            "RunGrowth",
            lambda_function=growth_fn,
            payload=sfn.TaskInput.from_object(
                {
                    "s3_bucket": data_bucket.bucket_name,
                    "s3_processed_prefix": "processed/",
                    "s3_results_prefix": "results/growth/",
                    "dynamodb_table": growth_table.table_name,
                }
            ),
            result_path="$.growth_result",
            output_path="$",
        )

        # All 5 analytics run in parallel after ETL
        analytics_parallel = sfn.Parallel(
            self, "RunAnalytics",
            result_path="$.analytics_results",
        )
        analytics_parallel.branch(forecast_task)
        analytics_parallel.branch(combo_task)
        analytics_parallel.branch(expansion_task)
        analytics_parallel.branch(staffing_task)
        analytics_parallel.branch(growth_task)

        pipeline_chain = etl_task.next(analytics_parallel)

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

        # ── Expose for cross-stack references ─────────────────────────
        self.data_bucket = data_bucket
        self.state_machine = state_machine

        # ── Outputs ──────────────────────────────────────────────────────
        cdk.CfnOutput(self, "DataBucketName", value=data_bucket.bucket_name)
        cdk.CfnOutput(self, "ForecastTableName", value=forecast_table.table_name)
        cdk.CfnOutput(self, "ComboTableName", value=combo_table.table_name)
        cdk.CfnOutput(self, "ExpansionTableName", value=expansion_table.table_name)
        cdk.CfnOutput(self, "StaffingTableName", value=staffing_table.table_name)
        cdk.CfnOutput(self, "GrowthTableName", value=growth_table.table_name)
        cdk.CfnOutput(self, "EtlFunctionArn", value=etl_fn.function_arn)
        cdk.CfnOutput(self, "ForecastFunctionArn", value=forecast_fn.function_arn)
        cdk.CfnOutput(self, "ComboFunctionArn", value=combo_fn.function_arn)
        cdk.CfnOutput(self, "ExpansionFunctionArn", value=expansion_fn.function_arn)
        cdk.CfnOutput(self, "StaffingFunctionArn", value=staffing_fn.function_arn)
        cdk.CfnOutput(self, "GrowthFunctionArn", value=growth_fn.function_arn)
        cdk.CfnOutput(self, "StateMachineArn", value=state_machine.state_machine_arn)
