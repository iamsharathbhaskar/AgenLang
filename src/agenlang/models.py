"""Pydantic v2 models mirroring schema/v1.0.json.

Full nested models for type-safe contract validation and serialization.
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
    ttl: str  # pattern \d+[smhd]
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


class SerResourceUsage(BaseModel):
    """SER resource usage."""

    joules_used: Optional[float] = None
    usd_cost: Optional[float] = None
    efficiency_score: Optional[float] = None


class SerSafetyChecks(BaseModel):
    """SER safety checks."""

    capability_violations: Optional[int] = None
    intent_anchor_verified: Optional[bool] = None


class Ser(BaseModel):
    """Structured Execution Record."""

    execution_id: str
    timestamps: SerTimestamps
    resource_usage: SerResourceUsage
    decision_points: list[dict[str, Any]] = Field(default_factory=list)
    safety_checks: Optional[SerSafetyChecks] = None
    replay_ref: Optional[str] = None
