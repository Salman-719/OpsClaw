#!/usr/bin/env python3
"""
CDK App — Conut AI Operations Pipeline
=======================================
Entry point for ``cdk deploy``.

Usage:
    cdk synth                    # generate CloudFormation
    cdk deploy                   # deploy to AWS
    cdk deploy --context env=prod  # deploy to prod
    cdk diff                     # preview changes
    cdk destroy                  # tear down
"""

import sys
from pathlib import Path

# Ensure project root is on sys.path so ``infra`` is importable.
PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import aws_cdk as cdk

from infra.cdk_stack import ConutPipelineStack

app = cdk.App()

env_name = app.node.try_get_context("env") or "dev"

ConutPipelineStack(
    app,
    f"ConutPipeline-{env_name}",
    env_name=env_name,
    env=cdk.Environment(
        # Uses your configured AWS CLI profile / env vars automatically.
        # Override explicitly if needed:
        #   account="123456789012",
        #   region="eu-west-1",
    ),
)

app.synth()
