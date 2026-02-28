#!/usr/bin/env python3
"""
CDK App — Conut AI Operations Platform
=======================================
Entry point for ``cdk deploy``.

Stacks:
  1. ConutPipeline   — S3 + DynamoDB + Lambdas + Step Functions
  2. ConutAgent      — EC2 + ALB for the FastAPI agent service
  3. ConutFrontend   — S3 + CloudFront for the React dashboard

Usage:
    cdk synth                          # generate CloudFormation
    cdk deploy --all                   # deploy everything
    cdk deploy ConutPipeline-dev       # deploy just the pipeline
    cdk deploy ConutAgent-dev          # deploy just the agent
    cdk deploy ConutFrontend-dev       # deploy just the frontend
    cdk deploy --context env=prod --all  # deploy to prod
    cdk diff                           # preview changes
    cdk destroy --all                  # tear down
"""

import sys
from pathlib import Path

# Ensure project root is on sys.path so ``infra`` is importable.
PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import aws_cdk as cdk

from infra.cdk_stack import ConutPipelineStack
from infra.agent_stack import AgentStack
from infra.frontend_stack import FrontendStack

app = cdk.App()

env_name = app.node.try_get_context("env") or "dev"

aws_env = cdk.Environment(
    # Uses your configured AWS CLI profile / env vars automatically.
    # Override explicitly if needed:
    #   account="123456789012",
    #   region="eu-west-1",
)

# Stack 1 — Data Pipeline (S3, DynamoDB, Lambdas, Step Functions)
pipeline_stack = ConutPipelineStack(
    app,
    f"ConutPipeline-{env_name}",
    env_name=env_name,
    env=aws_env,
)

# Stack 2 — Agent Service (EC2 + ALB)
agent_stack = AgentStack(
    app,
    f"ConutAgent-{env_name}",
    env_name=env_name,
    env=aws_env,
)
# Agent depends on pipeline (needs DynamoDB tables to exist)
agent_stack.add_dependency(pipeline_stack)

# Stack 3 — Frontend (S3 + CloudFront)
frontend_stack = FrontendStack(
    app,
    f"ConutFrontend-{env_name}",
    env_name=env_name,
    api_url=agent_stack.api_url,
    env=aws_env,
)
frontend_stack.add_dependency(agent_stack)

app.synth()
