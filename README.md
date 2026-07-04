# SAFR on AWS

> **A working prototype implementing the MAS SAFR framework on AWS — one-click deploy.**
>
> Built for MAS-regulated financial institutions deploying agentic AI in production.

---

## Background

In July 2026, the **Monetary Authority of Singapore (MAS)** published *[Safeguards for Agentic Finance at Runtime](https://www.mas.gov.sg/publications/monographs-or-information-paper/2026/safeguards-for-agentic-finance-at-runtime)* (SAFR) — an industry whitepaper developed with contributions from Ant International, Circle, HSBC, J.P. Morgan Chase, Manulife, Mastercard, OCBC, and Visa.

SAFR proposes a **runtime governance layer** that sits between every AI agent decision and its execution. It defines five components:

| SAFR Component | What It Does |
|---|---|
| **Governance Envelope** | Packages agent intent (action + trace + context) into a structured record before execution |
| **Agent Identity** | Verifies the agent is who it claims to be against a registry — identity gates all other checks |
| **Controls Repository** | The institution's configurable rulebook: authorization rules, exposure limits, rate limits, evidence quality thresholds |
| **Disposition Engine** | Evaluates each proposed action against controls → **DENY / ESCALATE / AUTO_EXECUTE / OBSERVE** |
| **Audit Log** | Tamper-evident, append-only record of every governance decision — independent of the agent |

SAFR is a **reference architecture, not a product.** MAS invited FinTechs and financial institutions to contribute implementations. This project is one such contribution — a concrete, deployable implementation on AWS.

---

## What This Project Does

This project implements **all five SAFR components** as a single CDK stack with a one-click deploy script. It combines AWS managed services with custom engineering to produce a governance checkpoint that:

- Accepts agent action proposals via REST API
- Verifies agent identity against a DynamoDB registry
- Evaluates proposed actions against configurable controls
- Returns **DENY**, **ESCALATE**, **AUTO_EXECUTE**, or **OBSERVE** outcomes
- Writes tamper-evident audit entries to S3 with Object Lock (Compliance mode)
- Provides a CloudWatch dashboard for operations monitoring

**It is a working prototype** — not a production-governed system. It demonstrates the art of the possible and provides a foundation institutions can build on.

---

## Architecture

```
                    ┌─────────────────────────────────┐
                    │       Amazon Bedrock              │
                    │       Guardrails                  │
                    │   (content filtering / PII)       │
                    └─────────────┬───────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────┐
│                        Amazon API Gateway                        │
│                    (API key auth + throttling)                    │
└─────────────────────────────┬───────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    SAFR Disposition Engine                       │
│                      (AWS Lambda — ARM64)                        │
│                                                                  │
│  ┌──────────────────┐  ┌────────────────┐  ┌─────────────────┐  │
│  │ Governance        │  │ Agent Identity  │  │ Controls        │  │
│  │ Envelope          │→ │ Verification    │→ │ Evaluation      │  │
│  │ (action + trace   │  │ (DynamoDB       │  │ (6 seeded rules │  │
│  │  + context)       │  │  safr-agents)   │  │  + pagination   │  │
│  └──────────────────┘  └────────────────┘  │  + TTL cache)    │  │
│                                             └────────┬────────┘  │
│                                                      │           │
│                                                      ▼           │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                    Disposition Outcome                     │   │
│  │        DENY │ ESCALATE │ AUTO_EXECUTE │ OBSERVE          │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────┬───────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                        Audit Log                                 │
│              Amazon S3 — Object Lock (Compliance mode)           │
│                   KMS encryption · Versioned · Immutable         │
└─────────────────────────────────────────────────────────────────┘
```

### AWS Service Mapping

| SAFR Component | AWS Implementation | Custom Engineering |
|---|---|---|
| **Governance Envelope** | API Gateway + Lambda | Envelope assembly from request body + trace |
| **Agent Identity** | DynamoDB `safr-agents` | Identity resolution + status checking |
| **Controls Repository** | DynamoDB `safr-controls` | Paginated scan, in-memory TTL cache, priority-sorted evaluation |
| **Disposition Engine** | Lambda (ARM64, Python 3.11) | 5 evaluator functions, severity-ordered outcome logic, human escalation SLA |
| **Audit Log** | S3 Object Lock (Compliance mode) + KMS | Structured JSON entries, date-partitioned keys |

---

## Quick Start

### One-Click Deploy

[![GitHub repo](https://img.shields.io/badge/GitHub-kdeath83%2Fsafr--on--aws-blue?style=flat&logo=github)](https://github.com/kdeath83/safr-on-aws)
[![CDK](https://img.shields.io/badge/AWS%20CDK-TypeScript-blue?style=flat&logo=amazonwebservices)](https://aws.amazon.com/cdk/)
[![License](https://img.shields.io/badge/license-MIT-green?style=flat)](LICENSE)

```bash
git clone https://github.com/kdeath83/safr-on-aws.git
cd safr-on-aws
./deploy.sh
```

**Prerequisites:** AWS CLI configured, Node.js ≥ 18, `npx` available.

The script:
1. Verifies AWS credentials
2. Installs CDK dependencies
3. Bootstraps CDK in your region
4. Deploys the full stack
5. Seeds 6 controls and 3 agent identities
6. Prints the API URL

### Test It

```bash
# Get API key
API_KEY=$(aws apigateway get-api-key \
  --api-key-id $(python3 -c "import json; d=json.load(open('cdk-outputs.json')); print(list(d.values())[0]['ApiKeyIdOutput'])") \
  --include-value --query value --output text)

API_URL=$(python3 -c "import json; d=json.load(open('cdk-outputs.json')); print(list(d.values())[0]['ApiUrlOutput'])")

# Authorized payment → AUTO_EXECUTE (200)
curl -s -X POST "$API_URL/govern" \
  -H "x-api-key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "agt-treasury-01",
    "action_type": "payment",
    "action_params": {"amount": 10000, "currency": "USD", "counterparty": "BANK-OK-1234"},
    "action_trace": ["checked_balance", "verified_counterparty"],
    "mandate_id": "mnd-2026-001",
    "agent_confidence": 0.95
  }'
```

More test scenarios: [`examples/test_requests.sh`](examples/test_requests.sh)

### Tear Down

```bash
./deploy.sh --destroy
```

Note: the S3 audit bucket is retained on destroy (Object Lock prevents accidental deletion).

---

## API Reference

### `POST /govern`

Evaluate a proposed agent action.

**Headers:**
- `x-api-key: <api-key>` (required)
- `Content-Type: application/json`

**Request Body:**

```json
{
  "agent_id": "agt-treasury-01",
  "action_type": "payment",
  "action_params": {
    "amount": 10000,
    "currency": "USD",
    "counterparty": "BANK-XX-1234"
  },
  "action_trace": ["checked_balance", "verified_counterparty"],
  "mandate_id": "mnd-2026-001",
  "agent_confidence": 0.95
}
```

**Responses:**

| Outcome | HTTP | Meaning |
|---|---|---|
| `AUTO_EXECUTE` | 200 | All controls passed; action proceeds |
| `OBSERVE` | 200 | Action proceeds but flagged for monitoring |
| `ESCALATE` | 202 | Held for human review; includes escalation deadline |
| `DENY` | 403 | Blocked by one or more controls |

**Response Body:**

```json
{
  "decision_id": "dec-abc123def456",
  "envelope_id": "env-789012345abc",
  "outcome": "AUTO_EXECUTE",
  "reason": "All controls passed",
  "rules_applied": [],
  "controls_checked": 6,
  "agent_identity_verified": true,
  "evaluation_time_ms": 42.17,
  "timestamp": "2026-07-04T12:00:00Z",
  "audit_log_key": "decisions/2026-07-04/dec-abc123def456.json"
}
```

### `GET /health`

Health check — no API key required.

---

## Seeded Controls

The stack seeds 6 controls on first deploy:

| Control | Category | Threshold | Violation Outcome |
|---|---|---|---|
| `ctrl-auth-001` | Authorization | Agent must be permitted for action type | **DENY** |
| `ctrl-sanctions-001` | Sanctions | Blocked counterparty list | **DENY** |
| `ctrl-exposure-002` | Exposure Limit | $500,000 absolute ceiling | **DENY** |
| `ctrl-exposure-001` | Exposure Limit | $25,000 soft limit | **ESCALATE** |
| `ctrl-evidence-001` | Evidence Quality | 85% confidence minimum | **ESCALATE** |
| `ctrl-rate-001` | Rate Limit | 60 actions/minute | **OBSERVE** |

Controls are evaluated in priority order. Multiple violations resolve to the most severe outcome.

---

## Seeded Agents

| Agent | Permitted Actions | Per-Action Limit | Confidence Threshold |
|---|---|---|---|
| `agt-treasury-01` | payment, fx_spot, liquidity_sweep, balance_check | $100,000 | 0.80 |
| `agt-compliance-01` | sanctions_check, kyc_refresh, transaction_monitor, report_file | $0 (read-only) | 0.90 |
| `agt-wealth-01` | portfolio_rebalance, trade_equity, generate_report, client_alert | $50,000 | 0.85 |

---

## Key Design Decisions

### Pre-execution governance
Every action is evaluated **before** it reaches execution — not after. SAFR operates between the agent's decision and the downstream system.

### Deterministic, not probabilistic
The Disposition Engine evaluates controls deterministically. This is intentional — financial actions need precise structural constraints (amount thresholds, allowed actions, blocked counterparties), not probabilistic guardrails.

### Tamper-evident audit
Audit entries are written to S3 with Object Lock in **Compliance mode**. Once written, no user — including AWS root — can modify or delete the entry for the retention period. This satisfies SAFR's requirement: *"an entry cannot be modified by the agent or by any downstream system."*

### Human escalation with SLA
When the outcome is `ESCALATE`, the response includes a 1-hour deadline. This addresses SAFR's operational requirement: *"If no decision is made within that period, the action should default to block or be escalated to a senior reviewer."*

### Custom engineering beyond managed services
While AWS services cover ~80% of SAFR's architecture, the remaining ~20% required custom engineering:

- **Governance Envelope assembly** — no AWS service produces SAFR's structured envelope; this is built in application logic
- **Controls priority ordering** — controls are evaluated by priority, with severity-ordered outcome resolution
- **Paginated scan with caching** — DynamoDB scan with `LastEvaluatedKey` loop + 60-second in-memory TTL
- **Human escalation SLA** — deadline calculation and reviewer assignment in application logic

---

## Monitoring

The stack deploys a CloudWatch dashboard (`SAFR-Governance`) with:

- **SAFR Decisions by Outcome** — invocation count over time
- **Evaluation Latency** — p50 and p99 response times
- **Errors** — Lambda error rate

An alarm fires when errors exceed 5 per 5-minute window.

---

## Project Structure

```
safr-on-aws/
├── README.md
├── deploy.sh                          # One-click deploy
├── .github/workflows/deploy.yml       # CI/CD via GitHub Actions
├── cdk/
│   ├── bin/app.ts                     # CDK entry point
│   └── lib/safr-stack.ts              # Full stack definition
├── lambda/
│   ├── disposition_engine/index.py    # Main API handler
│   ├── seed_controls/index.py         # Seed data (Custom Resource)
│   └── shared/
│       ├── models.py                  # GovernanceEnvelope, Disposition, Control, AuditEntry
│       ├── controls.py                # Disposition Engine core logic
│       └── audit.py                   # S3 Object Lock audit writer
└── examples/
    └── test_requests.sh               # Test scenarios
```

---

## Security

- API key authentication on `/govern`
- IAM least-privilege: Lambda can only read DynamoDB tables, write to audit bucket
- S3 Object Lock in Compliance mode — nobody can modify audit entries
- KMS encryption on all S3 objects
- CORS restricted to configured origin (not wildcard)
- No tracebacks returned to clients — errors logged to CloudWatch only
- X-Ray active tracing on all Lambda invocations

---

## Limitations

This is a **working prototype**, not a production system. Known gaps:

- **Rate limiting** — the `evaluate_rate_limit` control is stubbed; full implementation requires CloudWatch metrics integration
- **Cross-institution identity** — agent registry is single-table; federated identity not implemented
- **Human escalation workflow** — ESCALATE outcome returns a deadline but no Step Functions workflow for reviewer routing
- **No cryptographic envelope signing** — the envelope integrity problem is acknowledged but not solved
- **No unit tests** — test suite to follow
- **DynamoDB tables use `removalPolicy: DESTROY`** — accidental stack deletion would lose control/agent data

---

## References

- [SAFR Whitepaper — MAS, July 2026](https://www.mas.gov.sg/publications/monographs-or-information-paper/2026/safeguards-for-agentic-finance-at-runtime)
- [SAFR on AWS — Architecture & Service Mapping](SAFR_AWS_Mapping.md)
- [Amazon Bedrock AgentCore Documentation](https://docs.aws.amazon.com/bedrock-agentcore/)
- [AWS CDK Documentation](https://docs.aws.amazon.com/cdk/)

---

## License

MIT — see [LICENSE](LICENSE)

---

*Built for the BuildFin.ai community. Contributions welcome.*
