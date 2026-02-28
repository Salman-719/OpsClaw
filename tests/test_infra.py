"""
Unit tests — CDK infrastructure stacks (synthesize and validate).
"""

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import aws_cdk as cdk
from aws_cdk.assertions import Template


# ---------------------------------------------------------------------------
# Pipeline Stack
# ---------------------------------------------------------------------------

class TestPipelineStack:
    @pytest.fixture(scope="class")
    def template(self):
        from infra.cdk_stack import ConutPipelineStack
        app = cdk.App()
        stack = ConutPipelineStack(app, "TestPipeline", env_name="test")
        return Template.from_stack(stack)

    def test_s3_bucket_created(self, template):
        template.resource_count_is("AWS::S3::Bucket", 1)

    def test_dynamodb_tables_count(self, template):
        """5 DynamoDB tables: forecast, combo, expansion, staffing, growth."""
        template.resource_count_is("AWS::DynamoDB::Table", 5)

    def test_lambda_functions_count(self, template):
        """6 Lambdas: ETL + 5 analytics."""
        template.resource_count_is("AWS::Lambda::Function", 6)

    def test_state_machine_created(self, template):
        template.resource_count_is("AWS::StepFunctions::StateMachine", 1)

    def test_bucket_has_versioning(self, template):
        template.has_resource_properties("AWS::S3::Bucket", {
            "VersioningConfiguration": {"Status": "Enabled"},
        })

    def test_tables_use_pay_per_request(self, template):
        template.has_resource_properties("AWS::DynamoDB::Table", {
            "BillingMode": "PAY_PER_REQUEST",
        })

    def test_exports_data_bucket(self):
        from infra.cdk_stack import ConutPipelineStack
        app = cdk.App()
        stack = ConutPipelineStack(app, "TestExports", env_name="test")
        assert hasattr(stack, "data_bucket")
        assert hasattr(stack, "state_machine")


# ---------------------------------------------------------------------------
# Agent Stack
# ---------------------------------------------------------------------------

class TestAgentStack:
    @pytest.fixture(scope="class")
    def template(self):
        from infra.cdk_stack import ConutPipelineStack
        from infra.agent_stack import AgentStack
        app = cdk.App()
        pipeline = ConutPipelineStack(app, "TestPipeline2", env_name="test")
        agent = AgentStack(
            app, "TestAgent", env_name="test",
            data_bucket=pipeline.data_bucket,
            state_machine=pipeline.state_machine,
        )
        return Template.from_stack(agent)

    def test_ec2_instance_created(self, template):
        template.resource_count_is("AWS::EC2::Instance", 1)

    def test_instance_type_is_t3_small(self, template):
        template.has_resource_properties("AWS::EC2::Instance", {
            "InstanceType": "t3.small",
        })

    def test_alb_created(self, template):
        template.resource_count_is(
            "AWS::ElasticLoadBalancingV2::LoadBalancer", 1
        )

    def test_vpc_created(self, template):
        template.resource_count_is("AWS::EC2::VPC", 1)

    def test_has_iam_role(self, template):
        template.has_resource_properties("AWS::IAM::Role", {
            "AssumeRolePolicyDocument": {
                "Statement": [{
                    "Effect": "Allow",
                    "Principal": {"Service": "ec2.amazonaws.com"},
                }],
            },
        })


# ---------------------------------------------------------------------------
# Frontend Stack
# ---------------------------------------------------------------------------

class TestFrontendStack:
    @pytest.fixture(scope="class")
    def template(self):
        from infra.frontend_stack import FrontendStack
        app = cdk.App()
        stack = FrontendStack(app, "TestFrontend", env_name="test", api_url="http://test")
        return Template.from_stack(stack)

    def test_s3_bucket_created(self, template):
        template.resource_count_is("AWS::S3::Bucket", 1)

    def test_cloudfront_distribution_created(self, template):
        template.resource_count_is("AWS::CloudFront::Distribution", 1)

    def test_spa_error_responses(self, template):
        """CloudFront should handle 404 → index.html for SPA routing."""
        template.has_resource_properties("AWS::CloudFront::Distribution", {
            "DistributionConfig": {
                "CustomErrorResponses": [
                    {"ErrorCode": 404, "ResponseCode": 200, "ResponsePagePath": "/index.html"},
                    {"ErrorCode": 403, "ResponseCode": 200, "ResponsePagePath": "/index.html"},
                ],
            },
        })
