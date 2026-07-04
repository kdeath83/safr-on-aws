#!/usr/bin/env bash
# Test requests for SAFR Governance API
set -euo pipefail

API_URL="${1:-}"
API_KEY="${2:-}"

if [[ -z "$API_URL" ]]; then
  API_URL=$(python3 -c "import json; d=json.load(open('cdk-outputs.json')); print(list(d.values())[0]['ApiUrlOutput'])" 2>/dev/null || echo "")
fi

if [[ -z "$API_URL" ]]; then
  echo "Usage: $0 <api-url> <api-key>"
  echo "  or run after deploy.sh to auto-detect from cdk-outputs.json"
  exit 1
fi

echo "SAFR API: $API_URL"
echo ""

# Health check
echo "=== Health Check ==="
curl -s "$API_URL/health" | python3 -m json.tool
echo ""

# Test 1: Authorized payment (should AUTO_EXECUTE)
echo "=== Test 1: Payment $10,000 (should auto-execute) ==="
curl -s -X POST "$API_URL/govern" \
  -H "x-api-key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "agt-treasury-01",
    "action_type": "payment",
    "action_params": {
      "amount": 10000,
      "currency": "USD",
      "counterparty": "BANK-GOOD-1234"
    },
    "action_trace": ["checked_balance", "verified_counterparty"],
    "mandate_id": "mnd-2026-001",
    "agent_confidence": 0.95
  }' | python3 -m json.tool
echo ""

# Test 2: Large payment (should ESCALATE)
echo "=== Test 2: Payment $75,000 (should escalate — exceeds limit) ==="
curl -s -X POST "$API_URL/govern" \
  -H "x-api-key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "agt-treasury-01",
    "action_type": "payment",
    "action_params": {
      "amount": 75000,
      "currency": "USD",
      "counterparty": "BANK-GOOD-1234"
    },
    "action_trace": ["checked_balance", "verified_counterparty"],
    "mandate_id": "mnd-2026-001",
    "agent_confidence": 0.95
  }' | python3 -m json.tool
echo ""

# Test 3: Sanctioned counterparty (should DENY)
echo "=== Test 3: Payment to sanctioned entity (should deny) ==="
curl -s -X POST "$API_URL/govern" \
  -H "x-api-key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "agt-treasury-01",
    "action_type": "payment",
    "action_params": {
      "amount": 5000,
      "currency": "USD",
      "counterparty": "SANCTIONED-BANK-01"
    },
    "action_trace": ["checked_balance"],
    "mandate_id": "mnd-2026-001",
    "agent_confidence": 0.95
  }' | python3 -m json.tool
echo ""

# Test 4: Unauthorized action (should DENY)
echo "=== Test 4: Unauthorized action type (should deny) ==="
curl -s -X POST "$API_URL/govern" \
  -H "x-api-key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "agt-treasury-01",
    "action_type": "delete_records",
    "action_params": {"table": "customers"},
    "action_trace": [],
    "mandate_id": "mnd-2026-001",
    "agent_confidence": 0.99
  }' | python3 -m json.tool
echo ""

# Test 5: Low confidence (should ESCALATE)
echo "=== Test 5: Low confidence payment (should escalate) ==="
curl -s -X POST "$API_URL/govern" \
  -H "x-api-key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "agt-treasury-01",
    "action_type": "payment",
    "action_params": {
      "amount": 5000,
      "currency": "USD",
      "counterparty": "BANK-GOOD-1234"
    },
    "action_trace": ["checked_balance"],
    "mandate_id": "mnd-2026-001",
    "agent_confidence": 0.72
  }' | python3 -m json.tool
echo ""

echo "=== All tests complete ==="
