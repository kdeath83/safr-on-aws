"""
SAFR Disposition Engine — main Lambda handler.
Receives agent action proposals, evaluates against controls, and returns outcomes.
All 5 SAFR components: Governance Envelope → Identity → Controls → Disposition → Audit
"""
import json
import os
import sys
import traceback

# Lambda files are at zip root
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from shared.models import GovernanceEnvelope, Disposition, DispositionResult
from shared.controls import evaluate_envelope
from shared.audit import write_audit_entry


def lambda_handler(event, context):
    """API Gateway → SAFR evaluation → response."""
    try:
        # Parse request
        body = _parse_body(event)
        if not body:
            return _response(400, {"error": "Invalid JSON body"})

        # Step 1: Assemble Governance Envelope
        envelope = GovernanceEnvelope(
            agent_id=body.get("agent_id", ""),
            action_type=body.get("action_type", ""),
            action_params=body.get("action_params", {}),
            action_trace=body.get("action_trace", []),
            mandate_id=body.get("mandate_id", ""),
            agent_confidence=body.get("agent_confidence"),
        )

        if not envelope.agent_id or not envelope.action_type:
            return _response(400, {"error": "agent_id and action_type are required"})

        # Steps 2-4: Identity → Controls → Disposition
        result = evaluate_envelope(envelope)

        # Step 5: Audit Log
        try:
            log_key = write_audit_entry(envelope, result)
        except Exception as e:
            print(f"CRITICAL: Audit log write failed for {envelope.envelope_id}: {e}", flush=True)
            log_key = f"audit-write-failed: {str(e)}"

        # Build response
        resp = {
            "decision_id": result.decision_id,
            "envelope_id": envelope.envelope_id,
            "outcome": result.outcome.value,
            "reason": result.reason,
            "rules_applied": result.rules_applied,
            "controls_checked": result.controls_checked,
            "agent_identity_verified": result.agent_identity_verified,
            "evaluation_time_ms": round(result.evaluation_time_ms, 2),
            "timestamp": result.timestamp,
            "audit_log_key": log_key,
        }

        if result.outcome == Disposition.ESCALATE:
            resp["escalation_deadline"] = result.escalation_deadline
            resp["escalation_reviewer"] = result.escalation_reviewer

        http_status = {
            Disposition.AUTO_EXECUTE: 200,
            Disposition.OBSERVE: 200,
            Disposition.ESCALATE: 202,  # Accepted, pending review
            Disposition.DENY: 403,
        }.get(result.outcome, 500)

        return _response(http_status, resp)

    except Exception:
        print(f"SAFR evaluation error: {traceback.format_exc()}", flush=True)
        return _response(500, {
            "error": "Internal evaluation error",
            "reference_id": envelope.envelope_id if 'envelope' in dir() else "unknown",
        })


def _parse_body(event) -> dict:
    """Parse request body from API Gateway event."""
    body = event.get("body")
    if isinstance(body, str):
        try:
            return json.loads(body)
        except json.JSONDecodeError:
            return {}
    if isinstance(body, dict):
        return body
    return {}


def _response(status_code: int, body: dict) -> dict:
    cors_origin = os.environ.get("CORS_ORIGIN", "")
    headers = {
        "Content-Type": "application/json",
        "Access-Control-Allow-Headers": "Content-Type,Authorization,X-Api-Key",
        "Access-Control-Allow-Methods": "POST,OPTIONS,GET",
    }
    if cors_origin:
        headers["Access-Control-Allow-Origin"] = cors_origin
    return {
        "statusCode": status_code,
        "headers": headers,
        "body": json.dumps(body, default=str),
    }
