"""Pydantic v2 models mirroring schema/v1.0.json.

Full nested models for type-safe contract validation and serialization.
Includes root Contract model and SER output.
"""

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class Issuer(BaseModel):
    """Issuer agent identity and public key."""

    agent_id: str
    pubkey: str
    proof: Optional[str] = None


class IntentAnchor(BaseModel):
    """Hash anchoring user intent."""

    hash: str
    user_signature: Optional[str] = None


class ErrorHandler(BaseModel):
    """Error handler for workflow steps."""

    retry: int = Field(default=0, ge=0)
    fallback: Optional[str] = None
    escalate_to: Optional[str] = None
    notify_intent_anchor: bool = True


class WorkflowStep(BaseModel):
    """Single workflow step."""

    action: Literal["tool", "skill", "subcontract", "embed"]
    target: str
    args: dict[str, Any] = Field(default_factory=dict)
    on_error: Optional[ErrorHandler] = None


class Workflow(BaseModel):
    """Workflow definition with steps and optional error handler."""

    type: Literal["sequence", "parallel", "probabilistic"]
    steps: list[WorkflowStep]
    on_error: Optional[ErrorHandler] = None


class Constraints(BaseModel):
    """Execution constraints."""

    joule_budget: float = Field(ge=0)
    max_usd: Optional[float] = Field(default=None, ge=0)
    pii_level: Literal["none", "minimal", "gdpr_standard", "hipaa"] = "gdpr_standard"
    ethical: Optional[list[str]] = None


class MemoryContract(BaseModel):
    """Memory handoff and purge configuration."""

    handoff_keys: list[str]
    ttl: str
    purge_on_complete: bool = True
    data_subject: Optional[str] = None


class Settlement(BaseModel):
    """Settlement configuration."""

    joule_recipient: str
    rate: float = Field(ge=0)
    micro_payment_address: Optional[str] = None


class CapabilityAttestation(BaseModel):
    """Capability attestation with proof."""

    capability: str
    proof: str
    scope: Optional[str] = None


class SerConfig(BaseModel):
    """SER configuration."""

    redaction: Literal["none", "minimal", "gdpr_standard", "hipaa"] = "gdpr_standard"
    replay_enabled: bool = True


class SerTimestamps(BaseModel):
    """SER timestamps."""

    start: str
    end: Optional[str] = None


class DecisionPoint(BaseModel):
    """SER decision point record."""

    type: Optional[str] = None
    location: Optional[str] = None
    rationale: Optional[str] = None
    chosen: Optional[bool] = None


class SerResourceUsage(BaseModel):
    """SER resource usage."""

    joules_used: float = 0.0
    usd_cost: float = 0.0
    efficiency_score: float = 0.0


class SerSafetyChecks(BaseModel):
    """SER safety checks."""

    capability_violations: int = 0
    intent_anchor_verified: bool = False


class SettlementReceipt(BaseModel):
    """Settlement receipt in SER."""

    joule_recipient: str
    rate: float
    total_joules_owed: float


class Ser(BaseModel):
    """Structured Execution Record (output)."""

    execution_id: str
    timestamps: SerTimestamps
    resource_usage: SerResourceUsage
    decision_points: list[DecisionPoint] = Field(default_factory=list)
    safety_checks: SerSafetyChecks = Field(default_factory=SerSafetyChecks)
    replay_ref: Optional[str] = None
    reputation_score: float = 0.0
    settlement_receipt: Optional[SettlementReceipt] = None


class ContractModel(BaseModel):
    """Root AgenLang v1.0 Contract model (full schema)."""

    agenlang_version: str = "1.0"
    contract_id: str
    issuer: Issuer
    goal: str
    intent_anchor: IntentAnchor
    constraints: Constraints
    workflow: Workflow
    memory_contract: MemoryContract
    settlement: Settlement
    capability_attestations: list[CapabilityAttestation]
    ser_config: SerConfig = Field(default_factory=SerConfig)
    ser: Optional[Ser] = None
