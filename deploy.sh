#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# SAFR on AWS — One-Click Deploy
# ============================================================

REGION="${CDK_DEFAULT_REGION:-ap-southeast-1}"
AWS_PROFILE="${AWS_PROFILE:-}"
DESTROY=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --region) REGION="$2"; shift 2;;
    --profile) AWS_PROFILE="$2"; shift 2;;
    --destroy) DESTROY=true; shift;;
    *) echo "Usage: $0 [--region ap-southeast-1] [--profile default] [--destroy]"; exit 1;;
  esac
done

AWS_OPTS=""
[[ -n "$AWS_PROFILE" ]] && AWS_OPTS="--profile $AWS_PROFILE"
export CDK_DEFAULT_REGION="$REGION"

echo ""
echo "============================================"
echo " SAFR on AWS — Governance Deployment"
echo " Target: $REGION"
echo "============================================"
echo ""

# Prerequisites
echo "→ Checking prerequisites..."
for cmd in aws node npx; do
  command -v "$cmd" >/dev/null 2>&1 || { echo "  ✗ Missing: $cmd"; exit 1; }
  echo "  ✓ $cmd"
done

# Auth
aws sts get-caller-identity $AWS_OPTS >/dev/null 2>&1 || {
  echo "  ✗ AWS credentials not configured. Run: aws configure"
  exit 1
}
ACCOUNT=$(aws sts get-caller-identity $AWS_OPTS --query Account --output text)
echo "  ✓ AWS authenticated (account: $ACCOUNT)"

if $DESTROY; then
  echo ""
  echo "→ Destroying SAFR stack..."
  cd cdk
  npm install --silent
  npm run build
  npx cdk destroy --force --region "$REGION" $AWS_OPTS
  cd ..
  echo "✓ SAFR stack destroyed"
  exit 0
fi

# Install & build
echo ""
echo "→ Installing CDK dependencies..."
cd cdk
npm install --silent
echo "→ Building TypeScript..."
npm run build

# Bootstrap CDK (idempotent)
echo "→ Bootstrapping CDK in $REGION..."
npx cdk bootstrap --region "$REGION" $AWS_OPTS --require-approval never

# Deploy
echo ""
echo "→ Deploying SAFR stack..."
npx cdk deploy --region "$REGION" $AWS_OPTS --require-approval never --outputs-file ../cdk-outputs.json
cd ..

# Post-deploy
echo ""
echo "============================================"
echo " ✓ SAFR deployed successfully"
echo "============================================"
echo ""

# Parse outputs
API_URL=$(python3 -c "
import json, sys
d = json.load(open('cdk-outputs.json'))
stack = list(d.values())[0]
print(stack.get('ApiUrlOutput', 'N/A'))
" 2>/dev/null || echo "N/A")

API_KEY_ID=$(python3 -c "
import json, sys
d = json.load(open('cdk-outputs.json'))
stack = list(d.values())[0]
print(stack.get('ApiKeyIdOutput', 'N/A'))
" 2>/dev/null || echo "N/A")

DASHBOARD=$(python3 -c "
import json, sys
d = json.load(open('cdk-outputs.json'))
stack = list(d.values())[0]
print(stack.get('DashboardOutput', 'N/A'))
" 2>/dev/null || echo "N/A")

echo "API URL:     $API_URL"
echo "API Key ID:  $API_KEY_ID"
echo "Dashboard:   $DASHBOARD"
echo ""
echo "Retrieve API key value:"
echo "  aws apigateway get-api-key --api-key-id $API_KEY_ID --include-value --query value --output text"
echo ""
echo "Test the API:"
echo "  curl -X POST $API_URL/govern \\"
echo "    -H 'x-api-key: <api-key>' \\"
echo "    -H 'Content-Type: application/json' \\"
echo "    -d @examples/payment_request.json"
echo ""
echo "Destroy: ./deploy.sh --destroy"
echo ""
