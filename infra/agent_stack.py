"""
CDK Stack — OpsClaw Agent Service (EC2 + ALB)
==============================================
Deploys the FastAPI agent on an EC2 instance behind an ALB,
with IAM roles for DynamoDB + Bedrock + S3 + Step Functions access.
"""

from __future__ import annotations

from pathlib import Path

import aws_cdk as cdk
from aws_cdk import (
    Duration,
    RemovalPolicy,
    Stack,
    aws_ec2 as ec2,
    aws_iam as iam,
    aws_elasticloadbalancingv2 as elbv2,
    aws_elasticloadbalancingv2_targets as targets,
    aws_s3 as s3,
    aws_stepfunctions as sfn,
)
from constructs import Construct

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class AgentStack(Stack):
    """EC2-based agent service behind an ALB."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        env_name: str = "dev",
        data_bucket: s3.IBucket | None = None,
        state_machine: sfn.IStateMachine | None = None,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        project = "conut-ops"

        # ── VPC ──────────────────────────────────────────────────────────
        vpc = ec2.Vpc(
            self,
            "AgentVpc",
            max_azs=2,
            nat_gateways=1,
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    name="Public",
                    subnet_type=ec2.SubnetType.PUBLIC,
                    cidr_mask=24,
                ),
                ec2.SubnetConfiguration(
                    name="Private",
                    subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS,
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
            "ALB HTTP",
        )
        agent_sg.add_ingress_rule(
            ec2.Peer.any_ipv4(),
            ec2.Port.tcp(8000),
            "Agent API direct",
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

        # DynamoDB read access to all 5 tables
        for table_suffix in ["forecast", "combo", "expansion", "staffing", "growth"]:
            table_arn = f"arn:aws:dynamodb:*:*:table/{project}-{table_suffix}-{env_name}"
            agent_role.add_to_policy(
                iam.PolicyStatement(
                    actions=[
                        "dynamodb:GetItem",
                        "dynamodb:Query",
                        "dynamodb:Scan",
                        "dynamodb:BatchGetItem",
                    ],
                    resources=[table_arn, f"{table_arn}/index/*"],
                )
            )

        # Bedrock invoke access
        agent_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "bedrock:InvokeModel",
                    "bedrock:InvokeModelWithResponseStream",
                ],
                resources=["arn:aws:bedrock:*::foundation-model/*"],
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
                ],
                resources=[bucket_arn, f"{bucket_arn}/*"],
            )
        )

        # Step Functions — start + describe executions
        sfn_arn = state_machine.state_machine_arn if state_machine else f"arn:aws:states:*:*:stateMachine:{project}-pipeline-{env_name}"
        agent_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "states:StartExecution",
                    "states:DescribeExecution",
                    "states:ListExecutions",
                ],
                resources=[sfn_arn, f"{sfn_arn}:*"],
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
            "  -p 8000:8000 \\",
            f'  -e AWS_REGION=eu-west-1 \\',
            f'  -e ENV_NAME={env_name} \\',
            f'  -e LOCAL_MODE=false \\',
            f'  -e S3_DATA_BUCKET={bucket_name} \\',
            f'  -e STATE_MACHINE_ARN={sfn_arn_str} \\',
            f'  -e BEDROCK_MODEL_ID=anthropic.claude-sonnet-4-20250514 \\',
            "  opsclaw-agent",
            "",
            "echo 'OpsClaw Agent started successfully'",
        )

        # ── EC2 Instance ────────────────────────────────────────────────
        instance = ec2.Instance(
            self,
            "AgentInstance",
            instance_type=ec2.InstanceType("t3.medium"),
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
                        30,
                        volume_type=ec2.EbsDeviceVolumeType.GP3,
                    ),
                ),
            ],
        )

        # ── Application Load Balancer ───────────────────────────────────
        alb = elbv2.ApplicationLoadBalancer(
            self,
            "AgentALB",
            vpc=vpc,
            internet_facing=True,
            security_group=agent_sg,
        )

        listener = alb.add_listener(
            "HttpListener",
            port=80,
            protocol=elbv2.ApplicationProtocol.HTTP,
        )

        listener.add_targets(
            "AgentTarget",
            port=8000,
            protocol=elbv2.ApplicationProtocol.HTTP,
            targets=[targets.InstanceTarget(instance, port=8000)],
            health_check=elbv2.HealthCheck(
                path="/api/health",
                interval=Duration.seconds(30),
                healthy_threshold_count=2,
                unhealthy_threshold_count=5,
                timeout=Duration.seconds(10),
            ),
        )

        # ── Store ALB URL for the frontend stack ────────────────────────
        self.api_url = f"http://{alb.load_balancer_dns_name}"

        # ── Outputs ─────────────────────────────────────────────────────
        cdk.CfnOutput(self, "AgentALBUrl", value=self.api_url,
                       description="Agent API URL (ALB)")
        cdk.CfnOutput(self, "AgentInstanceId", value=instance.instance_id)
