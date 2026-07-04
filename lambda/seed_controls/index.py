"""
Seed script — populates initial controls and agent identities.
Run once after deployment via Custom Resource or manual invocation.
"""
import os
import json
import boto3
import time

dynamodb = boto3.resource("dynamodb")
CONTROLS_TABLE = os.environ.get("CONTROLS_TABLE", "safr-controls")
AGENTS_TABLE = os.environ.get("AGENTS_TABLE", "safr-agents")


SEED_CONTROLS = [
    {
        "control_id": "ctrl-auth-001",
        "category": "authorization",
        "description": "Verify agent is authorized for the requested action type",
        "rule_type": "boolean",
        "parameters": {},
        "enforcement": "hard",
        "outcome_on_violation": "DENY",
        "priority": 10,
        "enabled": True,
    },
    {
        "control_id": "ctrl-exposure-001",
        "category": "exposure_limit",
        "description": "Limit per-action financial exposure to configured maximum",
        "rule_type": "threshold",
        "parameters": {"max_amount": 25000},
        "enforcement": "soft",
        "outcome_on_violation": "ESCALATE",
        "priority": 20,
        "enabled": True,
    },
    {
        "control_id": "ctrl-exposure-002",
        "category": "exposure_limit",
        "description": "Hard block on transactions exceeding absolute ceiling",
        "rule_type": "threshold",
        "parameters": {"max_amount": 500000},
        "enforcement": "hard",
        "outcome_on_violation": "DENY",
        "priority": 15,
        "enabled": True,
    },
    {
        "control_id": "ctrl-rate-001",
        "category": "rate_limit",
        "description": "Limit agent actions to configured rate per minute",
        "rule_type": "rate",
        "parameters": {"max_per_minute": 60},
        "enforcement": "soft",
        "outcome_on_violation": "OBSERVE",
        "priority": 30,
        "enabled": True,
    },
    {
        "control_id": "ctrl-evidence-001",
        "category": "evidence_quality",
        "description": "Require minimum confidence threshold for autonomous execution",
        "rule_type": "threshold",
        "parameters": {"min_confidence": 0.85},
        "enforcement": "soft",
        "outcome_on_violation": "ESCALATE",
        "priority": 25,
        "enabled": True,
    },
    {
        "control_id": "ctrl-sanctions-001",
        "category": "sanctions",
        "description": "Block transactions with sanctioned counterparties",
        "rule_type": "list",
        "parameters": {
            "blocked_counterparties": [
                "SANCTIONED-BANK-01",
                "SANCTIONED-ENTITY-02",
            ]
        },
        "enforcement": "hard",
        "outcome_on_violation": "DENY",
        "priority": 5,
        "enabled": True,
    },
]


SEED_AGENTS = [
    {
        "agent_id": "agt-treasury-01",
        "agent_name": "Treasury Operations Agent",
        "principal_id": "user-treasury-chief",
        "permitted_actions": ["payment", "fx_spot", "liquidity_sweep", "balance_check"],
        "max_exposure_per_action": 100000,
        "max_exposure_aggregate": 1000000,
        "max_rate_per_minute": 30,
        "min_confidence_threshold": 0.80,
        "status": "active",
        "registered_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    },
    {
        "agent_id": "agt-compliance-01",
        "agent_name": "Compliance Screening Agent",
        "principal_id": "user-compliance-head",
        "permitted_actions": ["sanctions_check", "kyc_refresh", "transaction_monitor", "report_file"],
        "max_exposure_per_action": 0,
        "max_exposure_aggregate": 0,
        "max_rate_per_minute": 100,
        "min_confidence_threshold": 0.90,
        "status": "active",
        "registered_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    },
    {
        "agent_id": "agt-wealth-01",
        "agent_name": "Wealth Advisory Agent",
        "principal_id": "user-wealth-advisor",
        "permitted_actions": ["portfolio_rebalance", "trade_equity", "generate_report", "client_alert"],
        "max_exposure_per_action": 50000,
        "max_exposure_aggregate": 500000,
        "max_rate_per_minute": 20,
        "min_confidence_threshold": 0.85,
        "status": "active",
        "registered_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    },
]


def lambda_handler(event, context):
    """Custom Resource Lambda — seed controls and agents on stack creation."""
    request_type = event.get("RequestType", "Create")

    if request_type == "Delete":
        # Cleanup handled by CloudFormation
        return {"Status": "SUCCESS"}

    controls_table = dynamodb.Table(CONTROLS_TABLE)
    agents_table = dynamodb.Table(AGENTS_TABLE)

    seeded_controls = 0
    for ctrl in SEED_CONTROLS:
        controls_table.put_item(Item=ctrl)
        seeded_controls += 1

    seeded_agents = 0
    for agent in SEED_AGENTS:
        agents_table.put_item(Item=agent)
        seeded_agents += 1

    print(f"Seeded {seeded_controls} controls and {seeded_agents} agents")
    return {
        "Status": "SUCCESS",
        "Data": {
            "controls_seeded": str(seeded_controls),
            "agents_seeded": str(seeded_agents),
        },
    }
