"""Negotiation module - Contract Net Protocol (CNP) state machine."""

from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field
from datetime import datetime


class CNPState(str, Enum):
    """CNP state machine states."""

    IDLE = "IDLE"
    CFP_SENT = "CFP_SENT"
    PROPOSE_RECEIVED = "PROPOSE_RECEIVED"
    NEGOTIATING = "NEGOTIATING"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    EXECUTING = "EXECUTING"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class Proposal(BaseModel):
    """CNP proposal."""

    proposal_id: str
    task: str
    pricing: dict
    weights: dict = Field(
        default_factory=lambda: {"w1_prompt": 1.0, "w2_completion": 3.0, "w3_compute_sec": 10.0}
    )
    max_rounds: int = 5
    timeout_seconds: int = 300
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    expires_at: str


class CNPSession(BaseModel):
    """CNP negotiation session."""

    session_id: str
    initiator_did: str
    responder_did: str
    state: CNPState = CNPState.IDLE
    current_round: int = 0
    max_rounds: int = 5
    proposals: list[Proposal] = Field(default_factory=list)
    accepted_proposal: Optional[Proposal] = None


class CNPManager:
    """CNP state machine manager."""

    def __init__(self):
        self._sessions: dict[str, CNPSession] = {}

    async def initiate_cfp(self, initiator_did: str, responder_did: str, task: str) -> CNPSession:
        """Initiate CNP with Call For Proposals."""
        ...

    async def receive_proposal(self, session_id: str, proposal: Proposal) -> None:
        """Receive a proposal."""
        ...

    async def accept_proposal(self, session_id: str, proposal_id: str) -> None:
        """Accept a proposal."""
        ...

    async def reject_proposal(self, session_id: str, proposal_id: str) -> None:
        """Reject a proposal."""
        ...

    async def counter_propose(self, session_id: str, proposal: Proposal) -> None:
        """Counter-propose during haggling."""
        ...

    async def cancel_session(self, session_id: str) -> None:
        """Cancel a CNP session."""
        ...

    async def check_expiration(self, session_id: str) -> None:
        """Check and handle expired proposals."""
        ...
