"""
SAFR shared data models — defines the canonical shapes for Governance Envelope,
Controls, Disposition outcomes, and Audit Log entries.
"""
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional
import uuid
import time


class Disposition(str, Enum):
    DENY = "DENY"
    ESCALATE = "ESCALATE"
    AUTO_EXECUTE = "AUTO_EXECUTE"
    OBSERVE = "OBSERVE"


class ControlCategory(str, Enum):
    AUTHORIZATION = "authorization"
    EXPOSURE_LIMIT = "exposure_limit"
    RATE_LIMIT = "rate_limit"
    EVIDENCE_QUALITY = "evidence_quality"
    SANCTIONS = "sanctions"
    GEOGRAPHY = "geography"
    TIME_WINDOW = "time_window"


@dataclass
class Control:
    """A single control rule from the Controls Repository."""
    control_id: str
    category: ControlCategory
    description: str
    rule_type: str  # "threshold", "boolean", "rate", "list"
    parameters: dict
    enforcement: str  # "hard" (block) or "soft" (escalate)
    outcome_on_violation: Disposition
    priority: int = 100  # lower = higher priority


@dataclass
class AgentIdentity:
    """Verified agent identity from the registry."""
    agent_id: str
    agent_name: str
    principal_id: str  # human or system owner
    permitted_actions: list[str]
    max_exposure_per_action: float
    max_exposure_aggregate: float
    max_rate_per_minute: int
    min_confidence_threshold: float
    status: str  # "active", "suspended", "revoked"
    registered_at: str = ""


@dataclass
class GovernanceEnvelope:
    """The structured record of what the agent intends to do."""
    envelope_id: str = field(default_factory=lambda: f"env-{uuid.uuid4().hex[:12]}")
    agent_id: str = ""
    action_type: str = ""
    action_params: dict = field(default_factory=dict)
    action_trace: list[str] = field(default_factory=list)
    mandate_id: str = ""
    agent_confidence: Optional[float] = None
    timestamp: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))


@dataclass
class DispositionResult:
    """The outcome of evaluating a governance envelope against controls."""
    decision_id: str = field(default_factory=lambda: f"dec-{uuid.uuid4().hex[:12]}")
    envelope_id: str = ""
    outcome: Disposition = Disposition.DENY
    rules_applied: list[str] = field(default_factory=list)
    reason: str = ""
    escalation_deadline: Optional[str] = None
    escalation_reviewer: Optional[str] = None
    agent_identity_verified: bool = False
    identity_details: Optional[dict] = None
    controls_checked: int = 0
    evaluation_time_ms: float = 0.0
    timestamp: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))


@dataclass
class AuditEntry:
    """Immutable audit log entry."""
    log_id: str = field(default_factory=lambda: f"log-{uuid.uuid4().hex[:16]}")
    decision_id: str = ""
    envelope: dict = field(default_factory=dict)
    outcome: str = ""
    rules_applied: list[str] = field(default_factory=list)
    agent_identity: Optional[dict] = None
    timestamp: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
