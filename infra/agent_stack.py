"""
CDK Stack — OpsClaw Agent Service (public EC2 origin)
=====================================================
Deploys the FastAPI agent on a public EC2 instance with a stable Elastic IP,
with IAM roles for DynamoDB + Bedrock + S3 + Step Functions access.
"""

from __future__ import annotations

import aws_cdk as cdk
from aws_cdk import (
    ArnFormat,
    Stack,
    aws_ec2 as ec2,
    aws_iam as iam,
    aws_s3 as s3,
    aws_stepfunctions as sfn,
)
from constructs import Construct


class AgentStack(Stack):
    """EC2-based agent service with a direct public origin."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        env_name: str = "dev",
        deployment_profile: str = "standard",
        origin_header_name: str = "X-Origin-Verify",
        origin_header_value: str = "",
        data_bucket: s3.IBucket | None = None,
        state_machine: sfn.IStateMachine | None = None,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        project = "conut-ops"
        stack_region = Stack.of(self).region
        if deployment_profile not in {"standard", "budget"}:
            raise ValueError(
                f"Unsupported deployment_profile={deployment_profile!r}. "
                "Expected 'standard' or 'budget'."
            )

        max_azs = 2 if deployment_profile == "standard" else 1
        root_volume_size = 30 if deployment_profile == "standard" else 20

        # ── VPC ──────────────────────────────────────────────────────────
        vpc = ec2.Vpc(
            self,
            "AgentVpc",
            max_azs=max_azs,
            nat_gateways=0,
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    name="Public",
                    subnet_type=ec2.SubnetType.PUBLIC,
                    cidr_mask=24,
                ),
            ],
        )

        # ── Security Group ───────────────────────────────────────────────
        agent_sg = ec2.SecurityGroup(
            self,
            "AgentSG",
            vpc=vpc,
            description="Agent service SG",
            allow_all_outbound=True,
        )
        agent_sg.add_ingress_rule(
            ec2.Peer.any_ipv4(),
            ec2.Port.tcp(80),
            "CloudFront and public HTTP",
        )

        # ── IAM Role ────────────────────────────────────────────────────
        agent_role = iam.Role(
            self,
            "AgentRole",
            assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "AmazonSSMManagedInstanceCore"
                ),
            ],
        )

        # DynamoDB read + reset access to all 5 tables
        for table_suffix in ["forecast", "combo", "expansion", "staffing", "growth"]:
            table_arn = f"arn:aws:dynamodb:*:*:table/{project}-{table_suffix}-{env_name}"
            agent_role.add_to_policy(
                iam.PolicyStatement(
                    actions=[
                        "dynamodb:GetItem",
                        "dynamodb:Query",
                        "dynamodb:Scan",
                        "dynamodb:BatchGetItem",
                        "dynamodb:DeleteItem",
                        "dynamodb:BatchWriteItem",
                        "dynamodb:DescribeTable",
                    ],
                    resources=[table_arn, f"{table_arn}/index/*"],
                )
            )

        # Bedrock invoke access (foundation models + cross-region inference profiles)
        agent_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "bedrock:InvokeModel",
                    "bedrock:InvokeModelWithResponseStream",
                ],
                resources=[
                    "arn:aws:bedrock:*::foundation-model/*",
                    "arn:aws:bedrock:*:*:inference-profile/*",
                ],
            )
        )

        # S3 data bucket — upload (PutObject) + read for presigned URLs
        bucket_name = data_bucket.bucket_name if data_bucket else f"{project}-data-{env_name}"
        bucket_arn = data_bucket.bucket_arn if data_bucket else f"arn:aws:s3:::{project}-data-{env_name}"
        agent_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "s3:PutObject",
                    "s3:GetObject",
                    "s3:ListBucket",
                    "s3:DeleteObject",
                    "s3:CopyObject",
                ],
                resources=[bucket_arn, f"{bucket_arn}/*"],
            )
        )

        # Step Functions — start + describe executions
        sfn_arn = state_machine.state_machine_arn if state_machine else f"arn:aws:states:*:*:stateMachine:{project}-pipeline-{env_name}"
        # Execution ARNs use a different resource type and cannot be derived
        # reliably by string replacement once the state machine ARN is tokenized.
        exec_arn_pattern = Stack.of(self).format_arn(
            service="states",
            resource="execution",
            resource_name=f"{project}-pipeline-{env_name}:*",
            arn_format=ArnFormat.COLON_RESOURCE_NAME,
        )
        agent_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "states:StartExecution",
                    "states:DescribeExecution",
                    "states:ListExecutions",
                ],
                resources=[sfn_arn, exec_arn_pattern],
            )
        )

        # ── User Data (bootstrap script) ────────────────────────────────
        sfn_arn_str = state_machine.state_machine_arn if state_machine else ""
        user_data = ec2.UserData.for_linux()
        user_data.add_commands(
            "#!/bin/bash",
            "set -euxo pipefail",
            "",
            "# System packages",
            "yum update -y",
            "yum install -y docker git",
            "systemctl enable docker && systemctl start docker",
            "",
            "# Clone repo and build agent image",
            "cd /opt",
            "git clone https://github.com/Salman-719/OpsClaw.git app",
            "cd app",
            "",
            "# Build the agent Docker image",
            "docker build -f agent/Dockerfile -t opsclaw-agent .",
            "",
            f"# Run the agent container",
            "docker run -d --name opsclaw-agent \\",
            "  --restart always \\",
            "  -p 80:8000 \\",
            f'  -e AWS_REGION={stack_region} \\',
            f'  -e ENV_NAME={env_name} \\',
            f'  -e LOCAL_MODE=false \\',
            f'  -e S3_DATA_BUCKET={bucket_name} \\',
            f'  -e STATE_MACHINE_ARN={sfn_arn_str} \\',
            f'  -e BEDROCK_MODEL_ID=anthropic.claude-haiku-4-5-20251001-v1:0 \\',
            f'  -e ORIGIN_VERIFY_HEADER_NAME={origin_header_name} \\',
            f'  -e ORIGIN_VERIFY_HEADER_VALUE={origin_header_value} \\',
            "  opsclaw-agent",
            "",
            "echo 'OpsClaw Agent started successfully'",
        )

        # ── EC2 Instance ────────────────────────────────────────────────
        instance = ec2.Instance(
            self,
            "AgentInstance",
            instance_type=ec2.InstanceType("t3.micro"),
            machine_image=ec2.AmazonLinuxImage(
                generation=ec2.AmazonLinuxGeneration.AMAZON_LINUX_2023,
            ),
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PUBLIC),
            security_group=agent_sg,
            role=agent_role,
            user_data=user_data,
            block_devices=[
                ec2.BlockDevice(
                    device_name="/dev/xvda",
                    volume=ec2.BlockDeviceVolume.ebs(
                        root_volume_size,
                        volume_type=ec2.EbsDeviceVolumeType.GP3,
                    ),
                ),
            ],
        )

        eip = ec2.CfnEIP(
            self,
            "AgentEip",
            domain="vpc",
        )
        ec2.CfnEIPAssociation(
            self,
            "AgentEipAssociation",
            allocation_id=eip.attr_allocation_id,
            instance_id=instance.instance_id,
        )

        self.api_origin_domain = instance.instance_public_dns_name
        self.api_origin_port = 80
        self.api_origin_protocol = "http"

        # ── Outputs ─────────────────────────────────────────────────────
        cdk.CfnOutput(
            self,
            "AgentOriginUrl",
            value=f"http://{self.api_origin_domain}",
            description="Agent API origin URL",
        )
        cdk.CfnOutput(
            self,
            "AgentOriginDomain",
            value=self.api_origin_domain,
            description="Public DNS origin for CloudFront",
        )
        # Temporary compatibility export so existing frontend stacks that still
        # import the old ALB DNS output can migrate without blocking this stack
        # update. Once the frontend has been redeployed on the EC2 origin, this
        # compatibility output can be removed in a later cleanup pass.
        legacy_alb_dns_output = cdk.CfnOutput(
            self,
            "LegacyAgentAlbDnsExport",
            value=self.api_origin_domain,
            export_name=f"{self.stack_name}:ExportsOutputFnGetAttAgentALB66702F0FDNSNameB72FA1CB",
            description="Compatibility export for legacy frontend ALB origin import",
        )
        legacy_alb_dns_output.override_logical_id(
            "ExportsOutputFnGetAttAgentALB66702F0FDNSNameB72FA1CB"
        )
        cdk.CfnOutput(
            self,
            "AgentElasticIp",
            value=eip.ref,
            description="Elastic IP attached to the agent instance",
        )
        cdk.CfnOutput(
            self,
            "DeploymentProfile",
            value=deployment_profile,
            description="Deployment profile used for the agent stack",
        )
        cdk.CfnOutput(self, "AgentInstanceId", value=instance.instance_id)
