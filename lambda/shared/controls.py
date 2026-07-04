"""
Controls evaluation logic — the Disposition Engine core.
Evaluates a governance envelope against controls from the repository.
"""
import os
import time
import boto3
from typing import Optional
from decimal import Decimal
from shared.models import (
    Disposition, Control, AgentIdentity, GovernanceEnvelope,
    DispositionResult, ControlCategory
)

dynamodb = boto3.resource("dynamodb")
CONTROLS_TABLE = os.environ.get("CONTROLS_TABLE", "safr-controls")
AGENTS_TABLE = os.environ.get("AGENTS_TABLE", "safr-agents")

# In-memory cache for controls (reused across warm Lambda invocations)
_controls_cache: dict = {"data": None, "ts": 0.0, "ttl": 60.0}


def _serialize_dynamo_item(item: dict) -> dict:
    """Convert DynamoDB Decimal types to plain Python types."""
    out = {}
    for k, v in item.items():
        if isinstance(v, Decimal):
            out[k] = float(v) if v % 1 else int(v)
        elif isinstance(v, dict):
            out[k] = _serialize_dynamo_item(v)
        elif isinstance(v, list):
            out[k] = [
                _serialize_dynamo_item(i) if isinstance(i, dict)
                else float(i) if isinstance(i, Decimal)
                else i
                for i in v
            ]
        else:
            out[k] = v
    return out


def load_agent_identity(agent_id: str) -> Optional[AgentIdentity]:
    """Verify agent identity against the registry."""
    table = dynamodb.Table(AGENTS_TABLE)
    resp = table.get_item(Key={"agent_id": agent_id})
    item = resp.get("Item")
    if not item:
        return None
    item = _serialize_dynamo_item(item)
    if item.get("status") != "active":
        return None
    return AgentIdentity(
        agent_id=item["agent_id"],
        agent_name=item.get("agent_name", ""),
        principal_id=item.get("principal_id", ""),
        permitted_actions=item.get("permitted_actions", []),
        max_exposure_per_action=float(item.get("max_exposure_per_action", 0)),
        max_exposure_aggregate=float(item.get("max_exposure_aggregate", 0)),
        max_rate_per_minute=int(item.get("max_rate_per_minute", 60)),
        min_confidence_threshold=float(item.get("min_confidence_threshold", 0.0)),
        status=item.get("status", "inactive"),
        registered_at=item.get("registered_at", ""),
    )


def load_controls() -> list[Control]:
    """Load all active controls from the Controls Repository (with pagination + caching)."""
    now = time.time()
    if _controls_cache["data"] is not None and (now - _controls_cache["ts"]) < _controls_cache["ttl"]:
        return _controls_cache["data"]

    table = dynamodb.Table(CONTROLS_TABLE)
    controls = []
    scan_kwargs = {"Limit": 200}
    while True:
        resp = table.scan(**scan_kwargs)
        for item in resp.get("Items", []):
            item = _serialize_dynamo_item(item)
            if item.get("enabled", True):
                controls.append(Control(
                    control_id=item["control_id"],
                    category=ControlCategory(item.get("category", "authorization")),
                    description=item.get("description", ""),
                    rule_type=item.get("rule_type", "boolean"),
                    parameters=item.get("parameters", {}),
                    enforcement=item.get("enforcement", "hard"),
                    outcome_on_violation=Disposition(item.get("outcome_on_violation", "DENY")),
                    priority=int(item.get("priority", 100)),
                ))
        last_key = resp.get("LastEvaluatedKey")
        if not last_key:
            break
        scan_kwargs["ExclusiveStartKey"] = last_key
    controls.sort(key=lambda c: c.priority)
    _controls_cache["data"] = controls
    _controls_cache["ts"] = now
    return controls


def evaluate_authorization(agent: AgentIdentity, envelope: GovernanceEnvelope, control: Control) -> Optional[str]:
    """Check if the agent is authorized to perform this action type."""
    if envelope.action_type not in agent.permitted_actions:
        return f"Agent {agent.agent_id} not authorized for action '{envelope.action_type}'. Permitted: {agent.permitted_actions}"
    return None


def evaluate_exposure_limit(agent: AgentIdentity, envelope: GovernanceEnvelope, control: Control) -> Optional[str]:
    """Check if the action exceeds exposure limits."""
    amount_raw = envelope.action_params.get("amount")
    amount = float(amount_raw) if amount_raw is not None else 0.0
    limit = control.parameters.get("max_amount", agent.max_exposure_per_action)
    if amount > limit:
        return f"Amount {amount} exceeds limit {limit}"
    return None


def evaluate_rate_limit(agent: AgentIdentity, envelope: GovernanceEnvelope, control: Control) -> Optional[str]:
    """Check if the agent has exceeded rate limits (simplified — uses agent config)."""
    return None  # Simplified for prototype; full impl uses CloudWatch metrics


def evaluate_evidence_quality(agent: AgentIdentity, envelope: GovernanceEnvelope, control: Control) -> Optional[str]:
    """Check if agent confidence meets minimum threshold."""
    if envelope.agent_confidence is None:
        return None  # No confidence provided, skip check
    threshold = control.parameters.get("min_confidence", agent.min_confidence_threshold)
    if envelope.agent_confidence < threshold:
        return f"Agent confidence {envelope.agent_confidence} below threshold {threshold}"
    return None


def evaluate_sanctions(envelope: GovernanceEnvelope, control: Control) -> Optional[str]:
    """Check counterparty against sanctions list (simplified stub)."""
    counterparty = envelope.action_params.get("counterparty", "")
    blocked = control.parameters.get("blocked_counterparties", [])
    if counterparty in blocked:
        return f"Counterparty '{counterparty}' is on blocked list"
    return None


EVALUATORS = {
    ControlCategory.AUTHORIZATION: evaluate_authorization,
    ControlCategory.EXPOSURE_LIMIT: evaluate_exposure_limit,
    ControlCategory.RATE_LIMIT: evaluate_rate_limit,
    ControlCategory.EVIDENCE_QUALITY: evaluate_evidence_quality,
    ControlCategory.SANCTIONS: evaluate_sanctions,
}


def evaluate_envelope(envelope: GovernanceEnvelope) -> DispositionResult:
    """Full SAFR evaluation pipeline."""
    start = time.time()
    result = DispositionResult(envelope_id=envelope.envelope_id)

    # Step 1: Agent Identity verification
    agent = load_agent_identity(envelope.agent_id)
    if not agent:
        result.outcome = Disposition.DENY
        result.reason = f"Agent '{envelope.agent_id}' not found or not active in registry"
        result.agent_identity_verified = False
        result.evaluation_time_ms = (time.time() - start) * 1000
        return result

    result.agent_identity_verified = True
    result.identity_details = {
        "agent_id": agent.agent_id,
        "agent_name": agent.agent_name,
        "principal_id": agent.principal_id,
        "status": agent.status,
    }

    # Step 2: Load controls
    controls = load_controls()
    result.controls_checked = len(controls)

    # Step 3: Evaluate each control
    violations = []
    for control in controls:
        evaluator = EVALUATORS.get(control.category)
        if evaluator is None:
            continue
        violation_reason = evaluator(agent, envelope, control)
        if violation_reason:
            violations.append((control, violation_reason))

    # Step 4: Determine outcome
    if not violations:
        result.outcome = Disposition.AUTO_EXECUTE
        result.reason = "All controls passed"
    else:
        # Find the most severe outcome among violations
        severity_order = [Disposition.DENY, Disposition.ESCALATE, Disposition.OBSERVE]
        worst = Disposition.OBSERVE
        for control, reason in violations:
            result.rules_applied.append(control.control_id)
            outcome = control.outcome_on_violation
            # Guard: outcomes not in severity_order (e.g. AUTO_EXECUTE) are treated as OBSERVE
            try:
                outcome_idx = severity_order.index(outcome)
            except ValueError:
                outcome_idx = len(severity_order)  # treat as least severe
            if outcome_idx < severity_order.index(worst):
                worst = outcome
                result.reason = f"[{control.control_id}] {reason}"

        result.outcome = worst

        # Escalation details
        if result.outcome == Disposition.ESCALATE:
            result.escalation_deadline = time.strftime(
                "%Y-%m-%dT%H:%M:%SZ",
                time.gmtime(time.time() + 3600)  # 1-hour SLA
            )
            result.escalation_reviewer = "compliance-team"

    result.evaluation_time_ms = (time.time() - start) * 1000
    return result
