#!/usr/bin/env bash
# get_url.sh — Print the CloudFront frontend URL
set -euo pipefail

REGION="${AWS_REGION:-eu-west-1}"

url=$(aws cloudformation describe-stacks \
  --stack-name ConutFrontend-dev \
  --region "$REGION" \
  --query 'Stacks[0].Outputs[?OutputKey==`FrontendURL`].OutputValue' \
  --output text 2>/dev/null)

if [[ -z "$url" || "$url" == "None" ]]; then
  echo "❌ Frontend stack not deployed yet." >&2
  exit 1
fi

echo "🌐 $url"
