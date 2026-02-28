"""
CDK Stack — OpsClaw Frontend (S3 + CloudFront)
===============================================
Deploys the React dashboard to S3, served via CloudFront CDN.

NOTE: Run ``cd frontend && npm install && npm run build`` before
      ``cdk deploy`` so that ``frontend/dist/`` exists.
"""

from __future__ import annotations

import os
from pathlib import Path

import aws_cdk as cdk
from aws_cdk import (
    RemovalPolicy,
    Stack,
    aws_s3 as s3,
    aws_s3_deployment as s3deploy,
    aws_cloudfront as cloudfront,
    aws_cloudfront_origins as origins,
)
from constructs import Construct

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class FrontendStack(Stack):
    """S3 + CloudFront static hosting for the React dashboard."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        env_name: str = "dev",
        api_url: str = "",
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        project = "conut-ops"

        # ── S3 Bucket for static assets ─────────────────────────────────
        site_bucket = s3.Bucket(
            self,
            "FrontendBucket",
            bucket_name=f"{project}-frontend-{env_name}",
            website_index_document="index.html",
            website_error_document="index.html",  # SPA fallback
            public_read_access=False,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            removal_policy=RemovalPolicy.DESTROY if env_name != "prod" else RemovalPolicy.RETAIN,
            auto_delete_objects=(env_name != "prod"),
        )

        # ── CloudFront Distribution ─────────────────────────────────────
        distribution = cloudfront.Distribution(
            self,
            "FrontendCDN",
            default_behavior=cloudfront.BehaviorOptions(
                origin=origins.S3BucketOrigin.with_origin_access_control(
                    site_bucket,
                ),
                viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                cache_policy=cloudfront.CachePolicy.CACHING_OPTIMIZED,
            ),
            default_root_object="index.html",
            error_responses=[
                # SPA: serve index.html for all 404s (React Router)
                cloudfront.ErrorResponse(
                    http_status=404,
                    response_http_status=200,
                    response_page_path="/index.html",
                    ttl=cdk.Duration.seconds(0),
                ),
                cloudfront.ErrorResponse(
                    http_status=403,
                    response_http_status=200,
                    response_page_path="/index.html",
                    ttl=cdk.Duration.seconds(0),
                ),
            ],
        )

        # ── Deploy built frontend to S3 ────────────────────────────────
        dist_path = PROJECT_ROOT / "frontend" / "dist"
        if dist_path.is_dir():
            s3deploy.BucketDeployment(
                self,
                "DeployFrontend",
                sources=[
                    s3deploy.Source.asset(str(dist_path)),
                ],
                destination_bucket=site_bucket,
                distribution=distribution,
                distribution_paths=["/*"],
            )
        else:
            import warnings
            warnings.warn(
                f"frontend/dist not found at {dist_path}. "
                "Run 'cd frontend && npm install && npm run build' before deploying.",
                stacklevel=2,
            )

        # ── Outputs ─────────────────────────────────────────────────────
        cdk.CfnOutput(
            self,
            "FrontendURL",
            value=f"https://{distribution.distribution_domain_name}",
            description="Frontend CloudFront URL",
        )
        cdk.CfnOutput(
            self,
            "FrontendBucketName",
            value=site_bucket.bucket_name,
        )
        cdk.CfnOutput(
            self,
            "DistributionId",
            value=distribution.distribution_id,
        )
