"""Negotiation module - Contract Net Protocol (CNP) state machine."""

import asyncio
import uuid
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Optional

import aiosqlite
from pydantic import BaseModel, Field


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
    pricing: dict = Field(default_factory=lambda: {"base_joules": 0.0, "per_1k_tokens": 0.0})
    weights: dict = Field(
        default_factory=lambda: {"w1_prompt": 1.0, "w2_completion": 3.0, "w3_compute_sec": 10.0}
    )
    max_rounds: int = 5
    timeout_seconds: int = 300
    created_at: str = Field(
        default_factory=lambda: (
            datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        )
    )
    expires_at: str

    @classmethod
    def create(
        cls,
        task: str,
        pricing: dict,
        weights: dict,
        max_rounds: int = 5,
        timeout_seconds: int = 300,
    ) -> "Proposal":
        """Create a new proposal with calculated expiration."""
        now = datetime.now(timezone.utc)
        expires_at = (
            (now + timedelta(seconds=timeout_seconds))
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z")
        )

        return cls(
            proposal_id=f"prop_{uuid.uuid4().hex[:24]}",
            task=task,
            pricing=pricing,
            weights=weights,
            max_rounds=max_rounds,
            timeout_seconds=timeout_seconds,
            expires_at=expires_at,
        )

    def is_expired(self) -> bool:
        """Check if proposal has expired."""
        expires = datetime.fromisoformat(self.expires_at.replace("Z", "+00:00"))
        return datetime.now(timezone.utc) > expires


class CNPSession(BaseModel):
    """CNP negotiation session."""

    session_id: str
    initiator_did: str
    responder_did: str
    task: str
    state: CNPState = CNPState.IDLE
    current_round: int = 0
    max_rounds: int = 5
    proposals: list[Proposal] = Field(default_factory=list)
    accepted_proposal: Optional[Proposal] = None
    created_at: str = Field(
        default_factory=lambda: (
            datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        )
    )
    updated_at: str = Field(
        default_factory=lambda: (
            datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        )
    )

    @classmethod
    def create(
        cls, initiator_did: str, responder_did: str, task: str, max_rounds: int = 5
    ) -> "CNPSession":
        """Create a new CNP session."""
        return cls(
            session_id=f"cnp_{uuid.uuid4().hex[:24]}",
            initiator_did=initiator_did,
            responder_did=responder_did,
            task=task,
            max_rounds=max_rounds,
        )


class CNPManager:
    """CNP state machine manager with full implementation."""

    def __init__(self, db_path: Optional[str] = None):
        from pathlib import Path

        self.db_path = db_path or str(Path.home() / ".agenlang" / "negotiation.db")
        self._sessions: dict[str, CNPSession] = {}
        self._running = False
        self._expiration_task: Optional[asyncio.Task] = None

    async def init_db(self) -> None:
        """Initialize the CNP session database."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS cnp_sessions (
                    session_id TEXT PRIMARY KEY,
                    initiator_did TEXT NOT NULL,
                    responder_did TEXT NOT NULL,
                    task TEXT NOT NULL,
                    state TEXT NOT NULL,
                    current_round INTEGER NOT NULL,
                    max_rounds INTEGER NOT NULL,
                    accepted_proposal_json TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS proposals (
                    proposal_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    task TEXT NOT NULL,
                    pricing_json TEXT NOT NULL,
                    weights_json TEXT NOT NULL,
                    max_rounds INTEGER NOT NULL,
                    timeout_seconds INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    FOREIGN KEY (session_id) REFERENCES cnp_sessions(session_id)
                )
                """
            )
            await db.commit()

    async def start(self) -> None:
        """Start the CNP manager."""
        self._running = True
        self._expiration_task = asyncio.create_task(self._check_expirations())

    async def stop(self) -> None:
        """Stop the CNP manager."""
        self._running = False
        if self._expiration_task:
            self._expiration_task.cancel()

    async def initiate_cfp(
        self, initiator_did: str, responder_did: str, task: str, max_rounds: int = 5
    ) -> CNPSession:
        """Initiate CNP with Call For Proposals."""
        session = CNPSession.create(initiator_did, responder_did, task, max_rounds)
        session.state = CNPState.CFP_SENT

        self._sessions[session.session_id] = session
        await self._save_session(session)

        return session

    async def receive_proposal(self, session_id: str, proposal: Proposal) -> CNPSession:
        """Receive a proposal."""
        session = self._sessions.get(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")

        if session.current_round >= session.max_rounds:
            raise ValueError("Max rounds reached")

        session.proposals.append(proposal)
        session.current_round += 1
        session.state = CNPState.NEGOTIATING
        session.updated_at = (
            datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        )

        await self._save_session(session)
        await self._save_proposal(session_id, proposal)

        return session

    async def accept_proposal(self, session_id: str, proposal_id: str) -> CNPSession:
        """Accept a proposal."""
        session = self._sessions.get(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")

        proposal = next((p for p in session.proposals if p.proposal_id == proposal_id), None)
        if not proposal:
            raise ValueError(f"Proposal {proposal_id} not found")

        session.accepted_proposal = proposal
        session.state = CNPState.ACCEPTED
        session.updated_at = (
            datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        )

        await self._save_session(session)

        return session

    async def reject_proposal(self, session_id: str, proposal_id: str) -> CNPSession:
        """Reject a proposal."""
        session = self._sessions.get(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")

        session.state = CNPState.REJECTED
        session.updated_at = (
            datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        )

        await self._save_session(session)

        return session

    async def counter_propose(self, session_id: str, proposal: Proposal) -> CNPSession:
        """Counter-propose during haggling."""
        session = self._sessions.get(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")

        if session.current_round >= session.max_rounds:
            raise ValueError("Max rounds reached")

        session.proposals.append(proposal)
        session.current_round += 1
        session.updated_at = (
            datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        )

        await self._save_session(session)
        await self._save_proposal(session_id, proposal)

        return session

    async def cancel_session(self, session_id: str) -> CNPSession:
        """Cancel a CNP session."""
        session = self._sessions.get(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")

        session.state = CNPState.CANCELLED
        session.updated_at = (
            datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        )

        await self._save_session(session)

        return session

    async def execute_session(self, session_id: str) -> CNPSession:
        """Mark session as executing."""
        session = self._sessions.get(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")

        session.state = CNPState.EXECUTING
        session.updated_at = (
            datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        )

        await self._save_session(session)

        return session

    async def complete_session(self, session_id: str) -> CNPSession:
        """Mark session as completed."""
        session = self._sessions.get(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")

        session.state = CNPState.COMPLETED
        session.updated_at = (
            datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        )

        await self._save_session(session)

        return session

    async def check_expiration(self, session_id: str) -> bool:
        """Check and handle expired proposals. Returns True if expired."""
        session = self._sessions.get(session_id)
        if not session:
            return False

        now = datetime.now(timezone.utc)

        for proposal in session.proposals:
            expires = datetime.fromisoformat(proposal.expires_at.replace("Z", "+00:00"))
            if now > expires:
                session.state = CNPState.CANCELLED
                session.updated_at = now.isoformat(timespec="milliseconds").replace("+00:00", "Z")
                await self._save_session(session)
                return True

        return False

    async def _check_expirations(self) -> None:
        """Background task to check proposal expirations."""
        while self._running:
            try:
                await asyncio.sleep(10)
                for session_id in list(self._sessions.keys()):
                    await self.check_expiration(session_id)
            except asyncio.CancelledError:
                break
            except Exception:
                pass

    async def _save_session(self, session: CNPSession) -> None:
        """Save session to database."""
        import json

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT OR REPLACE INTO cnp_sessions 
                (session_id, initiator_did, responder_did, task, state, current_round, max_rounds, accepted_proposal_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session.session_id,
                    session.initiator_did,
                    session.responder_did,
                    session.task,
                    session.state.value,
                    session.current_round,
                    session.max_rounds,
                    session.accepted_proposal.model_dump_json()
                    if session.accepted_proposal
                    else None,
                    session.created_at,
                    session.updated_at,
                ),
            )
            await db.commit()

    async def _save_proposal(self, session_id: str, proposal: Proposal) -> None:
        """Save proposal to database."""
        import json

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT OR REPLACE INTO proposals 
                (proposal_id, session_id, task, pricing_json, weights_json, max_rounds, timeout_seconds, created_at, expires_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    proposal.proposal_id,
                    session_id,
                    proposal.task,
                    proposal.pricing.model_dump_json()
                    if hasattr(proposal.pricing, "model_dump_json")
                    else json.dumps(proposal.pricing),
                    json.dumps(proposal.weights),
                    proposal.max_rounds,
                    proposal.timeout_seconds,
                    proposal.created_at,
                    proposal.expires_at,
                ),
            )
            await db.commit()

    def get_session(self, session_id: str) -> Optional[CNPSession]:
        """Get a session by ID."""
        return self._sessions.get(session_id)
