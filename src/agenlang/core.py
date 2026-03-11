"""Core module - BaseAgent abstract class with SQLite persistence."""

import asyncio
import json
import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Optional

import aiosqlite

from agenlang.identity import Identity, verify_signature, generate_nonce


class Database:
    """SQLite database for agent session persistence."""

    def __init__(self, agent_id: str):
        self.agent_id = agent_id
        self.db_path = self._get_db_path()
        self._conn: Optional[aiosqlite.Connection] = None
        self._nonce_buffer: asyncio.Queue = asyncio.Queue()
        self._buffer_size = 100

    def _get_db_path(self) -> Path:
        """Get the database path."""
        base_dir = Path.home() / ".agenlang" / "agents" / self.agent_id
        base_dir.mkdir(parents=True, exist_ok=True)
        return base_dir / "session.db"

    async def connect(self) -> None:
        """Connect to the database and create tables."""
        self._conn = await aiosqlite.connect(self.db_path)
        self._conn.row_factory = aiosqlite.Row

        await self._create_tables()
        await self._start_nonce_buffer_worker()

    async def _create_tables(self) -> None:
        """Create database tables."""
        async with self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS nonces (
                nonce TEXT PRIMARY KEY,
                message_id TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        ):
            pass

        async with self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS contracts (
                contract_id TEXT PRIMARY KEY,
                state TEXT NOT NULL,
                conversation_id TEXT,
                trace_id TEXT,
                initiator_did TEXT,
                responder_did TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        ):
            pass

        async with self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ser_records (
                execution_id TEXT PRIMARY KEY,
                contract_id TEXT,
                provider_did TEXT,
                consumer_did TEXT,
                joules REAL,
                breakdown TEXT,
                signature TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        ):
            pass

        async with self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS agent_cards (
                did TEXT PRIMARY KEY,
                card_data TEXT,
                cached_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP
            )
            """
        ):
            pass

        async with self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS message_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                receiver_did TEXT,
                message_data TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                retry_count INTEGER DEFAULT 0
            )
            """
        ):
            pass

        await self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_nonces_created ON nonces(created_at)"
        )
        await self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_contracts_state ON contracts(state)"
        )
        await self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_contracts_trace ON contracts(trace_id)"
        )
        await self._conn.commit()

    async def _start_nonce_buffer_worker(self) -> None:
        """Start async worker for buffering nonce inserts."""

        async def worker():
            buffer = []
            while True:
                try:
                    item = await asyncio.wait_for(self._nonce_buffer.get(), timeout=1.0)
                    buffer.append(item)

                    if len(buffer) >= self._buffer_size:
                        await self._flush_nonce_buffer(buffer)
                        buffer.clear()
                except asyncio.TimeoutError:
                    if buffer:
                        await self._flush_nonce_buffer(buffer)
                        buffer.clear()

        asyncio.create_task(worker())

    async def _flush_nonce_buffer(self, buffer: list[tuple]) -> None:
        """Flush buffered nonces to database."""
        if not buffer:
            return

        try:
            await self._conn.executemany(
                "INSERT OR IGNORE INTO nonces (nonce, message_id) VALUES (?, ?)",
                buffer,
            )
            await self._conn.commit()
        except Exception:
            pass

    async def add_nonce(self, nonce: str, message_id: str) -> None:
        """Add a nonce to the buffer for async insertion."""
        await self._nonce_buffer.put((nonce, message_id))

    async def is_nonce_seen(self, nonce: str) -> bool:
        """Check if a nonce has been seen."""
        async with self._conn.execute("SELECT 1 FROM nonces WHERE nonce = ?", (nonce,)) as cursor:
            row = await cursor.fetchone()
            return row is not None

    async def prune_nonces(self, ttl_hours: int = 24) -> int:
        """Delete nonces older than TTL."""
        cursor = await self._conn.execute(
            """
            DELETE FROM nonces
            WHERE created_at < datetime('now', '-' || ? || ' hours')
            """,
            (ttl_hours,),
        )
        await self._conn.commit()
        return cursor.rowcount

    async def save_contract(
        self,
        contract_id: str,
        state: str,
        conversation_id: Optional[str],
        trace_id: Optional[str],
        initiator_did: str,
        responder_did: str,
    ) -> None:
        """Save or update a contract."""
        await self._conn.execute(
            """
            INSERT OR REPLACE INTO contracts
            (contract_id, state, conversation_id, trace_id, initiator_did, responder_did, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
            """,
            (contract_id, state, conversation_id, trace_id, initiator_did, responder_did),
        )
        await self._conn.commit()

    async def get_contract(self, contract_id: str) -> Optional[dict]:
        """Get a contract by ID."""
        async with self._conn.execute(
            "SELECT * FROM contracts WHERE contract_id = ?", (contract_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def update_contract_state(self, contract_id: str, state: str) -> None:
        """Update contract state."""
        await self._conn.execute(
            """
            UPDATE contracts SET state = ?, updated_at = datetime('now')
            WHERE contract_id = ?
            """,
            (state, contract_id),
        )
        await self._conn.commit()

    async def save_ser_record(
        self,
        execution_id: str,
        contract_id: str,
        provider_did: str,
        consumer_did: str,
        joules: float,
        breakdown: dict,
        signature: str,
    ) -> None:
        """Save a Signed Execution Record."""
        await self._conn.execute(
            """
            INSERT INTO ser_records
            (execution_id, contract_id, provider_did, consumer_did, joules, breakdown, signature)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                execution_id,
                contract_id,
                provider_did,
                consumer_did,
                joules,
                json.dumps(breakdown),
                signature,
            ),
        )
        await self._conn.commit()

    async def cache_agent_card(self, did: str, card_data: dict, ttl_seconds: int = 3600) -> None:
        """Cache an agent card."""
        from datetime import datetime, timedelta

        expires_at = datetime.now() + timedelta(seconds=ttl_seconds)

        await self._conn.execute(
            """
            INSERT OR REPLACE INTO agent_cards (did, card_data, cached_at, expires_at)
            VALUES (?, ?, datetime('now'), ?)
            """,
            (did, json.dumps(card_data), expires_at.isoformat()),
        )
        await self._conn.commit()

    async def get_cached_agent_card(self, did: str) -> Optional[dict]:
        """Get a cached agent card if not expired."""
        async with self._conn.execute(
            """
            SELECT card_data FROM agent_cards
            WHERE did = ? AND expires_at > datetime('now')
            """,
            (did,),
        ) as cursor:
            row = await cursor.fetchone()
            return json.loads(row[0]) if row else None

    async def queue_message(self, receiver_did: str, message_data: dict) -> None:
        """Queue a message for retry."""
        await self._conn.execute(
            """
            INSERT INTO message_queue (receiver_did, message_data)
            VALUES (?, ?)
            """,
            (receiver_did, json.dumps(message_data)),
        )
        await self._conn.commit()

    async def get_queued_messages(self) -> list[dict]:
        """Get queued messages."""
        async with self._conn.execute("SELECT * FROM message_queue ORDER BY created_at") as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def close(self) -> None:
        """Close the database connection."""
        if self._conn:
            await self._conn.close()


class BaseAgent(ABC):
    """Abstract base class for AgenLang agents."""

    def __init__(
        self,
        agent_id: str,
        db: Optional[Database] = None,
        trusted_dids: Optional[list[str]] = None,
        nonce_ttl_hours: int = 24,
    ):
        self.agent_id = agent_id
        self.db = db or Database(agent_id)
        self.trusted_dids = trusted_dids or []
        self.nonce_ttl_hours = nonce_ttl_hours
        self._running = False
        self._identity: Optional[Identity] = None
        self._message_queue: asyncio.Queue = asyncio.Queue()
        self._prune_task: Optional[asyncio.Task] = None

    @property
    def did(self) -> Optional[str]:
        """Get the agent's DID."""
        return self._identity.did if self._identity else None

    @abstractmethod
    async def on_message(self, message: dict) -> None:
        """Handle incoming message."""
        ...

    @abstractmethod
    async def on_request(self, message: dict) -> dict:
        """Handle REQUEST performative."""
        ...

    @abstractmethod
    async def on_propose(self, message: dict) -> dict:
        """Handle PROPOSE performative."""
        ...

    @abstractmethod
    async def on_inform(self, message: dict) -> None:
        """Handle INFORM performative."""
        ...

    async def initialize(self) -> None:
        """Initialize the agent (load identity, connect DB)."""
        self._identity = Identity.load(self.agent_id)
        await self.db.connect()

    async def start(self) -> None:
        """Start the agent."""
        self._running = True
        self._prune_task = asyncio.create_task(self._prune_loop())

    async def stop(self) -> None:
        """Stop the agent."""
        self._running = False
        if self._prune_task:
            self._prune_task.cancel()
            try:
                await self._prune_task
            except asyncio.CancelledError:
                pass
        await self.db.close()

    async def health(self) -> dict:
        """Health check."""
        return {"status": "healthy", "agent_id": self.agent_id, "did": self.did}

    async def send(
        self,
        receiver_did: str,
        performative: str,
        payload: Any,
        conversation_id: Optional[str] = None,
        trace_id: Optional[str] = None,
        parent_contract_id: Optional[str] = None,
    ) -> dict:
        """Send a message to another agent."""
        if not self._identity:
            raise ValueError("Agent not initialized")

        from agenlang.schema import Message

        message = Message.create(
            sender_did=self._identity.did,
            receiver_did=receiver_did,
            performative=performative,
            payload=payload,
            signature="",
            trace_id=trace_id,
            conversation_id=conversation_id,
            parent_contract_id=parent_contract_id,
        )

        content_dict = message.model_dump()
        envelope_dict = {k: v for k, v in content_dict["envelope"].items() if k != "signature"}

        signature = self._identity.sign(envelope_dict, content_dict["content"])
        content_dict["envelope"]["signature"] = signature

        return content_dict

    async def verify_and_receive(self, message: dict) -> bool:
        """Verify message signature and add nonce."""
        envelope = message.get("envelope", {})
        content = message.get("content", {})

        sender_did = envelope.get("sender_did")
        signature = envelope.get("signature")

        if not sender_did or not signature:
            return False

        if self.trusted_dids and sender_did not in self.trusted_dids:
            return False

        envelope_for_verify = {k: v for k, v in envelope.items() if k != "signature"}

        is_valid = verify_signature(
            signature,
            envelope_for_verify,
            content.get("payload", {}) if isinstance(content, dict) else content,
            sender_did,
        )

        if not is_valid:
            return False

        nonce = envelope.get("nonce")
        message_id = envelope.get("message_id")

        if await self.db.is_nonce_seen(nonce):
            return False

        await self.db.add_nonce(nonce, message_id)

        return True

    async def dispatch_message(self, message: dict) -> None:
        """Dispatch message to appropriate handler."""
        performative = message.get("performative", "")
        content = message.get("content", {})

        if performative == "REQUEST":
            await self.on_request(message)
        elif performative == "PROPOSE":
            await self.on_propose(message)
        elif performative == "INFORM":
            await self.on_inform(message)
        else:
            await self.on_message(message)

    async def _process_messages(self) -> None:
        """Message processing loop."""
        while self._running:
            try:
                message = await asyncio.wait_for(self._message_queue.get(), timeout=1.0)

                is_valid = await self.verify_and_receive(message)
                if is_valid:
                    await self.dispatch_message(message)

            except asyncio.TimeoutError:
                continue

    async def _prune_loop(self) -> None:
        """Periodically prune old nonces."""
        while self._running:
            try:
                await asyncio.sleep(3600)
                await self.db.prune_nonces(self.nonce_ttl_hours)
            except asyncio.CancelledError:
                break
            except Exception:
                pass
