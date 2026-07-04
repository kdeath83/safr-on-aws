# SAFR on AWS — One-Click Deployment

> **SAFR:** Safeguards for Agentic Finance at Runtime (MAS, July 2026)  
> **This project:** Production-grade AWS CDK implementation of all 5 SAFR components

## Architecture

```
Agent → API Gateway (REST) → Governance Envelope Lambda
                                    │
                          ┌─────────┼─────────┐
                          ▼         ▼         ▼
                    Agent Identity  Controls   Disposition
                    (DynamoDB)     (DynamoDB)  Engine (Lambda)
                          │         │         │
                          └─────────┼─────────┘
                                    ▼
                              Audit Log
                           (S3 Object Lock +
                            CloudWatch +
                            CloudTrail)

SAFR Outcomes: Deny | Escalate | Auto-Execute | Observe
```

## SAFR Component Mapping

| SAFR Component | AWS Implementation |
|---|---|
| Governance Envelope | API Gateway + Lambda assembles action/trace/context JSON |
| Agent Identity | DynamoDB agent registry + API key auth + optional JWT |
| Controls Repository | DynamoDB table with authorization rules, exposure limits, rate limits, evidence thresholds |
| Disposition Engine | Lambda evaluates against controls → ALLOW/DENY/ESCALATE/OBSERVE |
| Audit Log | S3 Object Lock (Compliance mode) + CloudWatch Logs + X-Ray traces |

## Quick Start

```bash
./deploy.sh
```

## API

```
POST /govern
Authorization: Bearer <api-key>
Content-Type: application/json

{
  "agent_id": "agt-treasury-01",
  "action_type": "payment",
  "action_params": {
    "amount": 50000,
    "currency": "USD",
    "counterparty": "BANK-XX-1234"
  },
  "action_trace": ["checked_balance", "verified_counterparty", "within_mandate"],
  "mandate_id": "mnd-2026-001"
}

Response:
{
  "outcome": "ESCALATE",
  "decision_id": "dec-abc123",
  "rules_applied": ["exposure_limit_check"],
  "reason": "Amount 50000 exceeds auto-execute threshold 25000",
  "escalation_deadline": "2026-07-04T12:30:00Z"
}
```

## Deploy & Destroy

```bash
./deploy.sh              # one-click deploy
./deploy.sh --destroy    # tear down
```
