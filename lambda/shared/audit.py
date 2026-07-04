"""
Audit logging — tamper-evident, append-only storage in S3 with Object Lock.
"""
import os
import json
import time
import boto3
from shared.models import AuditEntry, DispositionResult, GovernanceEnvelope

s3 = boto3.client("s3")
AUDIT_BUCKET = os.environ.get("AUDIT_BUCKET", "safr-audit-log")


def write_audit_entry(envelope: GovernanceEnvelope, result: DispositionResult) -> str:
    """Write an immutable audit log entry to S3."""
    entry = AuditEntry(
        decision_id=result.decision_id,
        envelope={
            "envelope_id": envelope.envelope_id,
            "agent_id": envelope.agent_id,
            "action_type": envelope.action_type,
            "action_params": envelope.action_params,
            "action_trace": envelope.action_trace,
            "mandate_id": envelope.mandate_id,
            "agent_confidence": envelope.agent_confidence,
            "timestamp": envelope.timestamp,
        },
        outcome=result.outcome.value,
        rules_applied=result.rules_applied,
        agent_identity=result.identity_details,
        timestamp=result.timestamp,
    )

    key = f"decisions/{result.timestamp[:10]}/{result.decision_id}.json"
    s3.put_object(
        Bucket=AUDIT_BUCKET,
        Key=key,
        Body=json.dumps(entry.__dict__, default=str, indent=2),
        ContentType="application/json",
        ServerSideEncryption="aws:kms",
    )
    return key
