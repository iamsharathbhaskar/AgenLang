"""Schema module - Pydantic v2 models for message envelope and FIPA-ACL performatives."""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


class Performative(str, Enum):
    """FIPA-ACL performatives."""

    REQUEST = "REQUEST"
    PROPOSE = "PROPOSE"
    ACCEPT_PROPOSAL = "ACCEPT-PROPOSAL"
    REJECT_PROPOSAL = "REJECT-PROPOSAL"
    INFORM = "INFORM"
    AGREE = "AGREE"
    REFUSE = "REFUSE"
    FAILURE = "FAILURE"
    CANCEL = "CANCEL"
    CFP = "CFP"
    NOT_UNDERSTOOD = "NOT_UNDERSTOOD"


class ErrorCode(str, Enum):
    """Standardized error registry for programmatic recovery."""

    ERR_CAPABILITY_MISMATCH = "ERR_CAPABILITY_MISMATCH"
    ERR_INSUFFICIENT_JOULES = "ERR_INSUFFICIENT_JOULES"
    ERR_PAYLOAD_TOO_LARGE = "ERR_PAYLOAD_TOO_LARGE"
    ERR_TASK_TIMEOUT = "ERR_TASK_TIMEOUT"
    ERR_JOULE_VALIDATION_FAILED = "ERR_JOULE_VALIDATION_FAILED"
    ERR_SIGNATURE_INVALID = "ERR_SIGNATURE_INVALID"
    ERR_DID_UNKNOWN = "ERR_DID_UNKNOWN"
    ERR_DID_BLOCKED = "ERR_DID_BLOCKED"


class ProtocolMeta(BaseModel):
    """Protocol version negotiation metadata for NOT_UNDERSTOOD responses."""

    min_version: str = Field(default="0.1.0", pattern=r"^\d+\.\d+\.\d+$")
    max_version: str = Field(default="0.1.0", pattern=r"^\d+\.\d+\.\d+$")


MAX_PAYLOAD_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB


class MessageContent(BaseModel):
    """Message content with encoding support for binary data."""

    payload: Any
    payload_encoding: str = Field(default="identity")
    media_type: str = Field(default="application/json")

    @field_validator("payload_encoding")
    @classmethod
    def validate_encoding(cls, v: str) -> str:
        allowed = {"identity", "base64"}
        if v not in allowed:
            raise ValueError(f"payload_encoding must be one of {allowed}")
        return v

    @field_validator("payload")
    @classmethod
    def validate_payload_size(cls, v: Any) -> Any:
        """Validate Base64 payload doesn't exceed 10MB limit."""
        import base64

        if isinstance(v, str):
            try:
                decoded = base64.b64decode(v)
                if len(decoded) > MAX_PAYLOAD_SIZE_BYTES:
                    raise ValueError(
                        f"Base64 payload exceeds {MAX_PAYLOAD_SIZE_BYTES} byte limit. "
                        f"Got {len(decoded)} bytes."
                    )
            except Exception:
                pass
        return v


class MessageEnvelope(BaseModel):
    """Signed message envelope following the protocol specification."""

    protocol_version: str = Field(default="0.1.0", pattern=r"^\d+\.\d+\.\d+$")
    message_id: str = Field(default_factory=lambda: f"msg_{uuid4().hex[:24]}")
    sender_did: str = Field(pattern=r"^did:key:z")
    receiver_did: str = Field(pattern=r"^did:key:z")
    nonce: str = Field(min_length=32, max_length=64)
    timestamp: str
    expires_at: Optional[str] = None
    trace_id: Optional[str] = None
    parent_contract_id: Optional[str] = Field(default=None, pattern=r"^ctr_")
    conversation_id: Optional[str] = Field(default=None, pattern=r"^conv_")
    reply_with: Optional[str] = None
    in_reply_to: Optional[str] = None
    signature: str

    @field_validator("timestamp", "expires_at", mode="before")
    @classmethod
    def validate_timestamp(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        if isinstance(v, datetime):
            return v.isoformat(timespec="milliseconds").replace("+00:00", "Z")
        return v

    @classmethod
    def create(
        cls,
        sender_did: str,
        receiver_did: str,
        nonce: str,
        signature: str,
        trace_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
        parent_contract_id: Optional[str] = None,
        expires_at: Optional[str] = None,
    ) -> "MessageEnvelope":
        """Create a new message envelope with current timestamp."""
        now = datetime.now(timezone.utc)
        timestamp = now.isoformat(timespec="milliseconds").replace("+00:00", "Z")

        return cls(
            sender_did=sender_did,
            receiver_did=receiver_did,
            nonce=nonce,
            timestamp=timestamp,
            signature=signature,
            trace_id=trace_id,
            conversation_id=conversation_id,
            parent_contract_id=parent_contract_id,
            expires_at=expires_at,
        )


class Message(BaseModel):
    """Full message with envelope and content."""

    envelope: MessageEnvelope
    content: MessageContent
    performative: Performative

    @classmethod
    def create(
        cls,
        sender_did: str,
        receiver_did: str,
        performative: Performative,
        payload: Any,
        signature: str,
        trace_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
        parent_contract_id: Optional[str] = None,
    ) -> "Message":
        """Create a new message with automatic ID and nonce generation."""
        from agenlang.identity import generate_nonce

        nonce = generate_nonce()
        envelope = MessageEnvelope.create(
            sender_did=sender_did,
            receiver_did=receiver_did,
            nonce=nonce,
            signature=signature,
            trace_id=trace_id,
            conversation_id=conversation_id,
            parent_contract_id=parent_contract_id,
        )

        content = MessageContent(payload=payload)

        return cls(
            envelope=envelope,
            content=content,
            performative=performative,
        )


class AgentCard(BaseModel):
    """Agent Card for discovery - self-describing agent metadata."""

    did: str = Field(pattern=r"^did:key:z")
    name: str = Field(max_length=100)
    description: str = Field(max_length=1000)
    capabilities: list[dict] = Field(default_factory=list)
    pricing: Optional[dict] = None
    transports: list[dict] = Field(default_factory=list)
    mcp_tools: list[dict] = Field(default_factory=list)
    updated_at: str
    signature: str

    @field_validator("updated_at", mode="before")
    @classmethod
    def set_updated_at(cls, v: Optional[str]) -> str:
        if v is None:
            now = datetime.now(timezone.utc)
            return now.isoformat(timespec="milliseconds").replace("+00:00", "Z")
        return v

    @classmethod
    def create(
        cls,
        did: str,
        name: str,
        description: str,
        capabilities: list[dict],
        transports: list[dict],
        signature: str,
        pricing: Optional[dict] = None,
        mcp_tools: Optional[list[dict]] = None,
    ) -> "AgentCard":
        """Create a new agent card."""
        now = datetime.now(timezone.utc)
        updated_at = now.isoformat(timespec="milliseconds").replace("+00:00", "Z")

        return cls(
            did=did,
            name=name,
            description=description,
            capabilities=capabilities,
            pricing=pricing,
            transports=transports,
            mcp_tools=mcp_tools or [],
            updated_at=updated_at,
            signature=signature,
        )
