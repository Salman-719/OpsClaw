#!/usr/bin/env bash
# get_url.sh — Print the CloudFront frontend URL
set -euo pipefail

ENV_NAME="${ENV_NAME:-dev}"
REGION="${AWS_REGION:-${AWS_DEFAULT_REGION:-$(aws configure get region 2>/dev/null || echo eu-west-1)}}"
STACK_NAME="ConutFrontend-${ENV_NAME}"

url=$(aws cloudformation describe-stacks \
  --stack-name "$STACK_NAME" \
  --region "$REGION" \
  --query 'Stacks[0].Outputs[?OutputKey==`FrontendURL`].OutputValue' \
  --output text 2>/dev/null)

if [[ -z "$url" || "$url" == "None" ]]; then
  echo "❌ Frontend stack not deployed yet." >&2
  exit 1
fi

echo "🌐 $url"
