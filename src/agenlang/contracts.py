"""Contracts module - Task lifecycle state machine."""

from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field
from datetime import datetime


class ContractState(str, Enum):
    """Task lifecycle states."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class Contract(BaseModel):
    """Contract metadata and state."""

    contract_id: str
    task: str
    sender_did: str
    receiver_did: str
    state: ContractState = ContractState.PENDING
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    updated_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    trace_id: Optional[str] = None
    parent_contract_id: Optional[str] = None


class ContractStore:
    """Contract storage interface."""

    async def create(self, contract: Contract) -> None:
        """Create a new contract."""
        ...

    async def get(self, contract_id: str) -> Optional[Contract]:
        """Get a contract by ID."""
        ...

    async def update(self, contract_id: str, state: ContractState) -> None:
        """Update contract state."""
        ...

    async def list_by_sender(self, sender_did: str) -> list[Contract]:
        """List contracts by sender."""
        ...

    async def list_by_receiver(self, receiver_did: str) -> list[Contract]:
        """List contracts by receiver."""
        ...
