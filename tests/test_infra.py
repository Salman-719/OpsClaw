"""
Unit tests — CDK infrastructure stacks (synthesize and validate).
"""

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import aws_cdk as cdk
from aws_cdk.assertions import Match, Template


# ---------------------------------------------------------------------------
# Pipeline Stack
# ---------------------------------------------------------------------------

class TestPipelineStack:
    @pytest.fixture(scope="class")
    def stack(self):
        from infra.cdk_stack import ConutPipelineStack
        app = cdk.App()
        return ConutPipelineStack(app, "TestPipeline", env_name="test")

    @pytest.fixture(scope="class")
    def template(self, stack):
        return Template.from_stack(stack)

    def test_s3_bucket_created(self, template):
        template.resource_count_is("AWS::S3::Bucket", 1)

    def test_dynamodb_tables_count(self, template):
        """5 DynamoDB tables: forecast, combo, expansion, staffing, growth."""
        template.resource_count_is("AWS::DynamoDB::Table", 5)

    def test_lambda_functions_count(self, template):
        """6 Docker-image Lambdas: ETL + 5 analytics."""
        image_lambdas = [
            resource
            for resource in template.find_resources("AWS::Lambda::Function").values()
            if resource["Properties"].get("PackageType") == "Image"
        ]
        assert len(image_lambdas) == 6

    def test_state_machine_created(self, template):
        template.resource_count_is("AWS::StepFunctions::StateMachine", 1)

    def test_bucket_has_versioning(self, template):
        template.has_resource_properties("AWS::S3::Bucket", {
            "VersioningConfiguration": {"Status": "Enabled"},
        })

    def test_bucket_name_stays_stable(self, template):
        template.has_resource_properties("AWS::S3::Bucket", {
            "BucketName": "conut-ops-data-test",
        })

    def test_tables_use_pay_per_request(self, template):
        template.has_resource_properties("AWS::DynamoDB::Table", {
            "BillingMode": "PAY_PER_REQUEST",
        })

    def test_exports_data_bucket(self, stack):
        assert hasattr(stack, "data_bucket")
        assert hasattr(stack, "state_machine")


# ---------------------------------------------------------------------------
# Agent Stack
# ---------------------------------------------------------------------------

class TestAgentStack:
    @pytest.fixture(scope="class")
    def standard_template(self):
        from infra.cdk_stack import ConutPipelineStack
        from infra.agent_stack import AgentStack
        app = cdk.App()
        pipeline = ConutPipelineStack(app, "TestPipeline2", env_name="test")
        agent = AgentStack(
            app, "TestAgent", env_name="test",
            deployment_profile="standard",
            data_bucket=pipeline.data_bucket,
            state_machine=pipeline.state_machine,
        )
        return Template.from_stack(agent)

    @pytest.fixture(scope="class")
    def budget_template(self):
        from infra.cdk_stack import ConutPipelineStack
        from infra.agent_stack import AgentStack
        app = cdk.App()
        pipeline = ConutPipelineStack(app, "TestPipelineBudget", env_name="test")
        agent = AgentStack(
            app, "TestAgentBudget", env_name="test",
            deployment_profile="budget",
            data_bucket=pipeline.data_bucket,
            state_machine=pipeline.state_machine,
        )
        return Template.from_stack(agent)

    def test_ec2_instance_created(self, standard_template):
        standard_template.resource_count_is("AWS::EC2::Instance", 1)

    def test_both_profiles_use_t3_micro(self, standard_template, budget_template):
        standard_template.has_resource_properties("AWS::EC2::Instance", {
            "InstanceType": "t3.micro",
        })
        budget_template.has_resource_properties("AWS::EC2::Instance", {
            "InstanceType": "t3.micro",
        })

    def test_no_alb_created(self, standard_template):
        standard_template.resource_count_is(
            "AWS::ElasticLoadBalancingV2::LoadBalancer", 0
        )

    def test_no_nat_gateway_created(self, standard_template):
        standard_template.resource_count_is("AWS::EC2::NatGateway", 0)

    def test_standard_profile_uses_two_public_subnets(self, standard_template):
        standard_template.resource_count_is("AWS::EC2::Subnet", 2)

    def test_budget_profile_uses_one_public_subnet(self, budget_template):
        budget_template.resource_count_is("AWS::EC2::Subnet", 1)

    def test_standard_root_volume_is_30_gb(self, standard_template):
        standard_template.has_resource_properties("AWS::EC2::Instance", {
            "BlockDeviceMappings": Match.array_with([
                Match.object_like({
                    "DeviceName": "/dev/xvda",
                    "Ebs": Match.object_like({"VolumeSize": 30}),
                }),
            ]),
        })

    def test_budget_root_volume_is_20_gb(self, budget_template):
        budget_template.has_resource_properties("AWS::EC2::Instance", {
            "BlockDeviceMappings": Match.array_with([
                Match.object_like({
                    "DeviceName": "/dev/xvda",
                    "Ebs": Match.object_like({"VolumeSize": 20}),
                }),
            ]),
        })

    def test_has_iam_role(self, standard_template):
        standard_template.has_resource_properties("AWS::IAM::Role", {
            "AssumeRolePolicyDocument": {
                "Statement": [{
                    "Effect": "Allow",
                    "Principal": {"Service": "ec2.amazonaws.com"},
                }],
            },
        })

    def test_agent_origin_outputs(self, standard_template):
        standard_template.has_output("AgentOriginUrl", {})
        standard_template.has_output("AgentOriginDomain", {})

    def test_legacy_alb_export_is_preserved_for_migration(self, standard_template):
        standard_template.has_output(
            "ExportsOutputFnGetAttAgentALB66702F0FDNSNameB72FA1CB",
            Match.object_like(
                {
                    "Export": {
                        "Name": "TestAgent:ExportsOutputFnGetAttAgentALB66702F0FDNSNameB72FA1CB",
                    }
                }
            ),
        )

    def test_vpc_created(self, standard_template):
        standard_template.resource_count_is("AWS::EC2::VPC", 1)


# ---------------------------------------------------------------------------
# Frontend Stack
# ---------------------------------------------------------------------------

class TestFrontendStack:
    @pytest.fixture(scope="class")
    def template(self):
        from infra.frontend_stack import FrontendStack
        app = cdk.App()
        stack = FrontendStack(
            app,
            "TestFrontend",
            env_name="test",
            api_origin_domain="ec2-198-51-100-10.eu-west-1.compute.amazonaws.com",
            origin_header_name="X-Origin-Verify",
            origin_header_value="test-secret",
        )
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

    def test_api_origin_uses_public_endpoint_with_custom_header(self, template):
        template.has_resource_properties("AWS::CloudFront::Distribution", {
            "DistributionConfig": Match.object_like({
                "Origins": Match.array_with([
                    Match.object_like({
                        "DomainName": "ec2-198-51-100-10.eu-west-1.compute.amazonaws.com",
                        "CustomOriginConfig": Match.object_like({
                            "OriginProtocolPolicy": "http-only",
                            "HTTPPort": 80,
                        }),
                        "OriginCustomHeaders": Match.array_with([
                            Match.object_like({
                                "HeaderName": "X-Origin-Verify",
                                "HeaderValue": "test-secret",
                            }),
                        ]),
                    }),
                ]),
            }),
        })
