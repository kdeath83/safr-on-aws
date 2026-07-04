# AWS Services → SAFR Framework Mapping

*Analysis: July 2026 — based on SAFR whitepaper (MAS) and Amazon Bedrock AgentCore documentation*

---

## Mapping Summary

| SAFR Component | Primary AWS Service(s) | How It Maps |
|---|---|---|
| **Governance Envelope** | AgentCore Runtime + AgentCore Gateway | Runtime captures agent context; Gateway intercepts API calls — together they produce the structured "envelope" before execution |
| **Agent Identity** | AgentCore Identity + AWS Agent Registry | Workload identities for agents, JWT authorization, credential providers, centralized catalog |
| **Controls Repository** | Policy in AgentCore + Amazon Verified Permissions + DynamoDB | Cedar-based policy engine (Allow/Deny decisions) + configurable rulebook storage |
| **Disposition Engine** | Policy in AgentCore + Lambda + Step Functions | Policy engine evaluates against controls → Deny/Auto-Execute; Lambda for custom escalation logic; Step Functions for human-review workflows |
| **Audit Log** | AgentCore Observability + CloudWatch + CloudTrail + S3 (Object Lock) | Invocation metrics, span traces, API audit logs, immutable append-only storage |

---

## Detailed Service Mapping

### 1. Governance Envelope → AgentCore Runtime + Gateway

**SAFR concept:** Before any agent action executes, it must be packaged with action + action trace + context metadata into a structured "governance envelope."

**AWS mapping:**

- **AgentCore Runtime** — serverless runtime that hosts agents with session isolation. Each agent invocation carries session context, tool call history, and identity — the raw material of the governance envelope.

- **AgentCore Gateway** — intercepts outbound API calls from agents. The Gateway pattern in AgentCore directly mirrors SAFR's "Gateway Integration" deployment pattern: "A SAFR gateway intercepts outbound API calls at the infrastructure layer, wrapping each call in a Governance Envelope and evaluating it without any changes to the agent code itself."

- **AgentCore Memory** — maintains short-term (multi-turn) and long-term (cross-session) context. This provides the "action trace" component of the envelope — the chain of reasoning that led to the proposed action.

**Gaps:** AgentCore does not natively produce a "governance envelope" data structure. You'd need to compose one from Gateway intercept output + Memory session state + Identity claims. This would be a custom integration layer.

---

### 2. Agent Identity → AgentCore Identity + AWS Agent Registry

**SAFR concept:** Every proposed action must be bound to a recognized, registered agent verified against a registry before any other evaluation.

**AWS mapping:**

- **AgentCore Identity** — "an identity and credential management service designed specifically for AI agents and automated workloads." Key features:
  - Workload identities with agent-specific attributes
  - Inbound JWT authorization
  - Credential providers for AWS and third-party services
  - Private identity provider connectivity
  - Audit trails for all identity operations
  - Direct integration with AgentCore Gateway and Runtime

- **AWS Agent Registry (Preview)** — "centrally catalog and discover AI resources." This maps to SAFR's agent registry concept — a central store of registered agents with metadata about their permitted capabilities.

- **AWS IAM** — traditional identity foundation. AgentCore Identity extends IAM with agent-specific workload identity patterns.

- **AWS Signer** — can cryptographically sign agent code/images, providing verifiable identity that an agent is what it claims to be.

**SAFR alignment:** Strong. AgentCore Identity directly addresses the closed-loop identity scenario (single institution). The "private identity providers" feature maps to SAFR's multi-registry open-network challenge. The JWT authorizer provides cryptographic binding that SAFR's envelope integrity problem needs.

**Gaps:** Cross-institution identity resolution (SAFR's open-network scenario) is not fully solved — the private identity provider integration is a bridge, not a standard.

---

### 3. Controls Repository → Policy in AgentCore + Verified Permissions

**SAFR concept:** The institution's configurable rulebook — controls drawn from policies, regulations, product rules, and user mandates against which proposed actions are checked.

**AWS mapping:**

- **Policy in AgentCore** — a dedicated policy engine with:
  - ALLOW/DENY decisions (maps to SAFR's Deny/Auto-Execute)
  - Enforcement modes: LOG_ONLY and ENFORCE (maps to Observe vs. active enforcement)
  - Policy matching and evaluation
  - Determining policies tracking
  - Metrics: AllowDecisions, DenyDecisions, MismatchErrors
  - Dimensions: OperationName, PolicyEngine, Policy, ToolName, Mode

- **Amazon Verified Permissions** — Cedar-based policy-as-code engine. Cedar policies are:
  - Deterministic (not probabilistic) — matches SAFR's deterministic evaluation requirement
  - Human-readable and auditable
  - Testable with automated reasoning

- **Amazon DynamoDB** — for the "Controls Repository" as a configurable data store. Each control (authorization rules, exposure limits, rate limits, evidence quality thresholds) becomes a DynamoDB item that the policy engine reads at runtime.

- **AWS Config** — tracks configuration changes to controls over time; provides the versioning/audit trail for "who changed the controls and when."

**SAFR alignment:** Very strong. The Policy in AgentCore engine with ALLOW/DENY decisions + LOG_ONLY/ENFORCE modes directly maps to SAFR's Deny/Auto-Execute/Observe outcomes. Cedar policies map to the deterministic rule evaluation SAFR requires.

**Gaps:** SAFR's "Escalate" outcome (hold for human review) is not a native Policy outcome — it requires orchestration (Step Functions). Rate limits and evidence quality thresholds would need custom implementation.

---

### 4. Disposition Engine → Policy in AgentCore + Lambda + Step Functions

**SAFR concept:** Evaluates each in-scope action against controls and resolves to one of four outcomes: Deny, Escalate, Auto-Execute, Observe.

**AWS mapping:**

| SAFR Outcome | AWS Implementation |
|---|---|
| **Deny** | Policy in AgentCore → DENY decision |
| **Auto-Execute** | Policy in AgentCore → ALLOW decision (ENFORCE mode) |
| **Observe** | Policy in AgentCore → ALLOW decision (LOG_ONLY mode) + CloudWatch alert on matching patterns |
| **Escalate** | Policy in AgentCore → ALLOW with condition → Step Functions workflow for human approval → Lambda for timeout/default-to-deny |

- **AWS Step Functions** — orchestrates the human escalation workflow: routes to reviewer, enforces timeout window, defaults to deny if no response. Maps to SAFR's escalation operational requirements (reviewer authority, turnaround timeout).

- **AWS Lambda** — executes custom evaluation logic: checks against exposure limits, rate limits, evidence quality thresholds. Lambda functions are the "custom rules" beyond what the policy engine natively supports.

- **Amazon CloudWatch Alarms** — triggers on anomaly patterns that warrant "Observe" escalation.

- **AgentCore Evaluations** — provides pre-deployment testing of agent behavior against scenarios. Maps to SAFR's need for testing disposition engine rules before production.

**SAFR alignment:** Strong. Policy in AgentCore provides the deterministic core; Lambda + Step Functions handle the custom logic and human-in-the-loop workflows that the policy engine alone can't express.

**Gaps:** SAFR's multi-step workflow rule ("prior authorization does not carry forward") must be enforced in application logic — Step Functions can model this but it's not built-in.

---

### 5. Audit Log → AgentCore Observability + CloudTrail + S3

**SAFR concept:** Tamper-evident, append-only record of every governance decision — envelope, mandate, rules applied, outcome, timing.

**AWS mapping:**

- **AgentCore Observability** — publishes invocation metrics and span traces to CloudWatch. Metrics include: Invocations, SystemErrors, UserErrors, Latency, AllowDecisions, DenyDecisions, TotalMismatchedPolicies. Spans provide end-to-end trace data across Runtime, Memory, Gateway, Identity, and Policy operations.

- **AWS CloudTrail** — records every API call as an event. Captures: who made the call, when, from where, what parameters. CloudTrail is append-only and tamper-evident by design.

- **Amazon S3 with Object Lock** — for the immutable audit log store. Object Lock in Compliance mode prevents any user (including root) from modifying or deleting objects. This directly satisfies SAFR's requirement: "an entry cannot be modified by the agent or by any downstream system."

- **Amazon CloudWatch Logs** — structured application logs with log group retention policies and export to S3.

- **AWS Audit Manager** — maps audit evidence to compliance frameworks. Can continuously collect evidence from CloudTrail, CloudWatch, and Config, mapping to specific control requirements.

**SAFR alignment:** Very strong. S3 Object Lock provides the tamper-evident guarantee. CloudTrail provides the independent record (not reliant on the agent's own account). AgentCore Observability provides agent-specific telemetry that CloudTrail alone would miss (action traces, tool calls, policy decisions).

---

## Beyond AgentCore: Supporting AWS Services

### Bedrock Guardrails (Pre-SAFR Content Filtering)

SAFR explicitly positions itself *after* content filtering. Amazon Bedrock Guardrails provides that layer:
- Denied topics
- Content filters (harmful content thresholds)
- Sensitive information masking (PII redaction)
- Contextual grounding checks (hallucination detection)
- Prompt injection defense

Guardrails → SAFR (AgentCore Policy) → Execution. This maps cleanly to SAFR's Figure 4 stack.

### AWS KMS (Cryptographic Envelope Integrity)

SAFR's acknowledged-but-unsolved envelope integrity problem: "an agent can fabricate its own action trace." AWS KMS asymmetric signing can address this:
- Each agent gets a KMS signing key
- The governance envelope is signed at creation
- The Disposition Engine verifies the signature before evaluation
- The Audit Log stores the verified signature

This doesn't prevent fabrication entirely (the agent could sign a fabricated trace) but it provides non-repudiation — you know which agent signed what, and a compromised key can be revoked.

### Amazon EventBridge (Cross-Service Governance Events)

Connects SAFR components: Policy evaluation results → EventBridge → Lambda (escalation) / SNS (notifications) / Step Functions (workflows). Enables the "Observe" → "Escalate" pipeline that SAFR underspecifies.

---

## SAFR Gaps vs. AWS Coverage

| SAFR Gap (from analysis) | AWS Mitigation |
|---|---|
| No technical specification | AgentCore provides actual APIs, SDKs, and CLI |
| Envelope integrity unsolved | KMS signing + Gateway intercept = verifiable envelope |
| Agent identity in open networks | AgentCore private identity providers + JWT federation |
| Controls Repository is a black box | Cedar policies in Verified Permissions are testable, auditable, versionable |
| No performance analysis | CloudWatch metrics provide latency/error data; AgentCore is serverless (auto-scaling) |
| "Observe" outcome vague | CloudWatch Alarms + EventBridge → automated escalation paths |
| Single point of failure | AWS HA across AZs; AgentCore is managed/serverless |
| No testing methodology | AgentCore Evaluations for pre-deployment scenario testing |
| No rollback/remediation | Step Functions for remediation workflows; CloudTrail for root cause |
| Multi-agent coordination | Agent Registry + cross-account Gateway tools |

---

## Recommended SAFR-on-AWS Architecture

```
Agent → Bedrock Guardrails → AgentCore Gateway (intercept) 
    → AgentCore Identity (verify) 
    → Policy in AgentCore + Verified Permissions (evaluate controls)
    → Disposition: Deny | Auto-Execute | Observe (LOG_ONLY) | Escalate (Step Functions)
    → AgentCore Observability + CloudTrail + S3 Object Lock (audit log)
    → Execution (AgentCore Runtime or external system)
```

**Key integration points:**

1. **Governance Envelope** = Gateway intercept output + Identity claims JWT + Memory session context → custom Lambda to assemble into structured JSON → stored in DynamoDB with KMS signature
2. **Controls Repository** = DynamoDB tables (authorization rules, exposure limits, rate limits, evidence thresholds) + Cedar policies in Verified Permissions
3. **Disposition Engine** = Policy in AgentCore (core evaluation) + Lambda (custom rules) + Step Functions (escalation orchestration)
4. **Audit Log** = CloudTrail (API-level) + AgentCore Observability spans (agent-level) + S3 Object Lock (immutable storage) + Audit Manager (compliance mapping)

---

## Verdict

**AgentCore is the closest existing cloud service to a SAFR implementation.** It directly addresses four of five SAFR components (Identity, Controls/Policy, Disposition, and Audit/Observability), and the Gateway pattern maps to SAFR's deployment model. The Governance Envelope requires custom assembly from AgentCore primitives.

For an institution evaluating agentic AI governance on AWS: start with AgentCore Gateway + Identity + Policy, add Verified Permissions for complex rules, use Step Functions for human escalation, and back the audit trail with S3 Object Lock. This gets you ~80% of the SAFR architecture with managed services.

The remaining ~20% — envelope assembly, controls repository schema, cross-institution identity federation, and adversarial robustness testing — requires custom engineering regardless of platform choice.
