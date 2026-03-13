"""
CDK Stack — OpsClaw Frontend (S3 + CloudFront)
===============================================
Deploys the React dashboard to S3, served via CloudFront CDN.

NOTE: Run ``cd frontend && npm install && npm run build`` before
      ``cdk deploy`` so that ``frontend/dist/`` exists.
"""

from __future__ import annotations
import os
import shutil
import subprocess
from pathlib import Path

import aws_cdk as cdk
import jsii
from aws_cdk import (
    RemovalPolicy,
    Stack,
    aws_cloudfront as cloudfront,
    aws_cloudfront_origins as origins,
    aws_s3 as s3,
    aws_s3_deployment as s3deploy,
)
from constructs import Construct

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FRONTEND_ROOT = PROJECT_ROOT / "frontend"


def _copy_directory_contents(source_dir: Path, output_dir: str) -> None:
    output_path = Path(output_dir)
    for child in source_dir.iterdir():
        destination = output_path / child.name
        if child.is_dir():
            shutil.copytree(child, destination, dirs_exist_ok=True)
        else:
            shutil.copy2(child, destination)


@jsii.implements(cdk.ILocalBundling)
class _FrontendLocalBundling:
    def try_bundle(self, output_dir: str, *args, **_kwargs) -> bool:
        dist_dir = FRONTEND_ROOT / "dist"
        if dist_dir.is_dir():
            _copy_directory_contents(dist_dir, output_dir)
            return True

        if shutil.which("npm") is None:
            return False

        env = os.environ.copy()
        env.setdefault("CI", "true")
        subprocess.run(["npm", "ci"], cwd=FRONTEND_ROOT, check=True, env=env)
        subprocess.run(["npm", "run", "build"], cwd=FRONTEND_ROOT, check=True, env=env)

        if not dist_dir.is_dir():
            raise RuntimeError(f"Frontend build did not produce {dist_dir}")

        _copy_directory_contents(dist_dir, output_dir)
        return True


class FrontendStack(Stack):
    """S3 + CloudFront static hosting for the React dashboard."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        env_name: str = "dev",
        api_origin_domain: str = "",
        origin_header_name: str = "X-Origin-Verify",
        origin_header_value: str = "",
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        project = "conut-ops"

        # ── S3 Bucket for static assets ─────────────────────────────────
        site_bucket = s3.Bucket(
            self,
            "FrontendBucket",
            website_index_document="index.html",
            website_error_document="index.html",  # SPA fallback
            public_read_access=False,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            removal_policy=RemovalPolicy.DESTROY if env_name != "prod" else RemovalPolicy.RETAIN,
            auto_delete_objects=(env_name != "prod"),
        )

        # ── API origin (public EC2 origin) — CloudFront proxies /api/* ──
        additional_behaviors = {}
        if api_origin_domain:
            api_origin = origins.HttpOrigin(
                api_origin_domain,
                protocol_policy=cloudfront.OriginProtocolPolicy.HTTP_ONLY,
                http_port=80,
                custom_headers={
                    origin_header_name: origin_header_value,
                },
            )
            additional_behaviors["/api/*"] = cloudfront.BehaviorOptions(
                origin=api_origin,
                viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                allowed_methods=cloudfront.AllowedMethods.ALLOW_ALL,
                cache_policy=cloudfront.CachePolicy.CACHING_DISABLED,
                origin_request_policy=cloudfront.OriginRequestPolicy.ALL_VIEWER,
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
            additional_behaviors=additional_behaviors,
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

        # ── Build and deploy frontend to S3 during synth/deploy ────────
        s3deploy.BucketDeployment(
            self,
            "DeployFrontend",
            sources=[
                s3deploy.Source.asset(
                    str(FRONTEND_ROOT),
                    exclude=["dist", "node_modules", ".vite", ".cache"],
                    bundling=cdk.BundlingOptions(
                        image=cdk.DockerImage.from_registry("public.ecr.aws/docker/library/node:20"),
                        local=_FrontendLocalBundling(),
                        command=[
                            "bash",
                            "-lc",
                            "npm ci && npm run build && cp -r dist/* /asset-output/",
                        ],
                    ),
                ),
            ],
            destination_bucket=site_bucket,
            distribution=distribution,
            distribution_paths=["/*"],
            wait_for_distribution_invalidation=True,
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
