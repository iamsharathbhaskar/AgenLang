"""SQLite backend implementation for agent registry.

Provides SQLite-backed storage for agent identities, capabilities,
reputation scores, and execution history.
"""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import structlog

from .base import (
    AgentRecord,
    ExecutionRecord,
    InteractionRecord,
    RegistryBackend,
    SearchQuery,
)

log = structlog.get_logger()


class SQLiteBackend(RegistryBackend):
    """SQLite-backed agent registry with reputation tracking.

    Supports agent registration, discovery by capability,
    reputation scoring, and execution history.
    """

    def __init__(self, db_path: Optional[Path] = None) -> None:
        """Initialize SQLite backend.

        Args:
            db_path: Path to SQLite database. Defaults to ~/.agenlang/registry.db
        """
        import os

        base = Path(
            os.environ.get("AGENLANG_KEY_DIR", str(Path.home() / ".agenlang"))
        )
        self._db_path = db_path or base / "registry.db"
        self._db_path.parent.mkdir(parents=True, exist_ok=True)

    async def init_schema(self) -> None:
        """Initialize database schema."""
        with sqlite3.connect(str(self._db_path)) as conn:
            # Agents table
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS agents (
                    did_key TEXT PRIMARY KEY,
                    pubkey_pem TEXT NOT NULL,
                    endpoint_url TEXT NOT NULL,
                    name TEXT DEFAULT 'Unknown Agent',
                    description TEXT DEFAULT '',
                    capabilities TEXT NOT NULL,  -- JSON array
                    reputation_score REAL DEFAULT 0.5,
                    joule_rate REAL DEFAULT 1.0,
                    version TEXT DEFAULT '0.1.0',
                    created_at TEXT NOT NULL,
                    last_seen TEXT NOT NULL,
                    is_active INTEGER DEFAULT 1
                )
            """
            )

            # Execution history table
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS executions (
                    execution_id TEXT PRIMARY KEY,
                    contract_id TEXT NOT NULL,
                    issuer_did TEXT NOT NULL,
                    receiver_did TEXT NOT NULL,
                    joules_used REAL NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    ser_summary TEXT
                )
            """
            )

            # Interactions table (for reputation tracking)
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS interactions (
                    interaction_id TEXT PRIMARY KEY,
                    contract_id TEXT NOT NULL,
                    issuer_did TEXT NOT NULL,
                    receiver_did TEXT NOT NULL,
                    rating REAL NOT NULL,
                    joules_used REAL NOT NULL,
                    status TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    metadata TEXT
                )
            """
            )

            # Reputation history table
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS reputation_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    did_key TEXT NOT NULL,
                    old_score REAL NOT NULL,
                    new_score REAL NOT NULL,
                    contract_id TEXT,
                    timestamp TEXT NOT NULL,
                    FOREIGN KEY (did_key) REFERENCES agents(did_key)
                )
            """
            )

            # Indexes
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_agents_capabilities ON agents(capabilities)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_agents_reputation ON agents(reputation_score)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_agents_name ON agents(name)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_executions_issuer ON executions(issuer_did)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_executions_receiver ON executions(receiver_did)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_executions_created ON executions(created_at)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_interactions_receiver ON interactions(receiver_did)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_interactions_timestamp ON interactions(timestamp)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_reputation_did ON reputation_history(did_key)"
            )

            conn.commit()
        log.debug("sqlite_schema_initialized", db_path=str(self._db_path))

    async def register_agent(
        self,
        did_key: str,
        pubkey_pem: str,
        endpoint_url: str,
        capabilities: List[str],
        name: str = "Unknown Agent",
        description: str = "",
        joule_rate: float = 1.0,
        version: str = "0.1.0",
    ) -> AgentRecord:
        """Register a new agent or update existing."""
        now = datetime.now(timezone.utc).isoformat()
        capabilities_json = json.dumps(capabilities)

        with sqlite3.connect(str(self._db_path)) as conn:
            conn.execute(
                """
                INSERT INTO agents (
                    did_key, pubkey_pem, endpoint_url, name, description,
                    capabilities, reputation_score, joule_rate, version,
                    created_at, last_seen, is_active
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
                ON CONFLICT(did_key) DO UPDATE SET
                    pubkey_pem = excluded.pubkey_pem,
                    endpoint_url = excluded.endpoint_url,
                    name = excluded.name,
                    description = excluded.description,
                    capabilities = excluded.capabilities,
                    joule_rate = excluded.joule_rate,
                    version = excluded.version,
                    last_seen = excluded.last_seen,
                    is_active = 1
            """,
                (
                    did_key,
                    pubkey_pem,
                    endpoint_url,
                    name,
                    description,
                    capabilities_json,
                    0.5,  # Initial reputation
                    joule_rate,
                    version,
                    now,
                    now,
                ),
            )
            conn.commit()

        log.info(
            "agent_registered", did_key=did_key, name=name, endpoint=endpoint_url
        )
        agent = await self.get_agent(did_key)
        assert agent is not None
        return agent

    async def get_agent(self, did_key: str) -> Optional[AgentRecord]:
        """Get agent by DID:key."""
        with sqlite3.connect(str(self._db_path)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM agents WHERE did_key = ? AND is_active = 1",
                (did_key,),
            ).fetchone()

            if row is None:
                return None

            return AgentRecord(
                did_key=row["did_key"],
                pubkey_pem=row["pubkey_pem"],
                endpoint_url=row["endpoint_url"],
                name=row["name"],
                description=row["description"],
                capabilities=json.loads(row["capabilities"]),
                reputation_score=row["reputation_score"],
                joule_rate=row["joule_rate"],
                version=row["version"],
                created_at=row["created_at"],
                last_seen=row["last_seen"],
                is_active=bool(row["is_active"]),
            )

    async def find_agents_by_capability(
        self, capability: str, min_reputation: float = 0.0
    ) -> List[AgentRecord]:
        """Find agents with a specific capability."""
        with sqlite3.connect(str(self._db_path)) as conn:
            conn.row_factory = sqlite3.Row
            pattern = f'%"{capability}"%'
            rows = conn.execute(
                """
                SELECT * FROM agents
                WHERE capabilities LIKE ?
                AND reputation_score >= ?
                AND is_active = 1
                ORDER BY reputation_score DESC
            """,
                (pattern, min_reputation),
            ).fetchall()

            return [
                AgentRecord(
                    did_key=row["did_key"],
                    pubkey_pem=row["pubkey_pem"],
                    endpoint_url=row["endpoint_url"],
                    name=row["name"],
                    description=row["description"],
                    capabilities=json.loads(row["capabilities"]),
                    reputation_score=row["reputation_score"],
                    joule_rate=row["joule_rate"],
                    version=row["version"],
                    created_at=row["created_at"],
                    last_seen=row["last_seen"],
                    is_active=bool(row["is_active"]),
                )
                for row in rows
            ]

    async def list_agents(self, limit: int = 100) -> List[AgentRecord]:
        """List all registered agents."""
        with sqlite3.connect(str(self._db_path)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT * FROM agents
                WHERE is_active = 1
                ORDER BY last_seen DESC
                LIMIT ?
            """,
                (limit,),
            ).fetchall()

            return [
                AgentRecord(
                    did_key=row["did_key"],
                    pubkey_pem=row["pubkey_pem"],
                    endpoint_url=row["endpoint_url"],
                    name=row["name"],
                    description=row["description"],
                    capabilities=json.loads(row["capabilities"]),
                    reputation_score=row["reputation_score"],
                    joule_rate=row["joule_rate"],
                    version=row["version"],
                    created_at=row["created_at"],
                    last_seen=row["last_seen"],
                    is_active=bool(row["is_active"]),
                )
                for row in rows
            ]

    async def update_reputation(self, did_key: str, new_score: float) -> None:
        """Update agent reputation score."""
        clamped_score = max(0.0, min(1.0, new_score))

        with sqlite3.connect(str(self._db_path)) as conn:
            # Get old score for history
            row = conn.execute(
                "SELECT reputation_score FROM agents WHERE did_key = ?",
                (did_key,),
            ).fetchone()
            old_score = row[0] if row else 0.5

            # Update agent
            conn.execute(
                "UPDATE agents SET reputation_score = ? WHERE did_key = ?",
                (clamped_score, did_key),
            )

            # Record history
            now = datetime.now(timezone.utc).isoformat()
            conn.execute(
                """
                INSERT INTO reputation_history
                (did_key, old_score, new_score, timestamp)
                VALUES (?, ?, ?, ?)
            """,
                (did_key, old_score, clamped_score, now),
            )
            conn.commit()

        log.info("reputation_updated", did_key=did_key, score=clamped_score)

    async def record_execution(
        self,
        execution_id: str,
        contract_id: str,
        issuer_did: str,
        receiver_did: str,
        joules_used: float,
        status: str,
        ser_summary: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Record a contract execution."""
        now = datetime.now(timezone.utc).isoformat()
        ser_json = json.dumps(ser_summary) if ser_summary else None

        with sqlite3.connect(str(self._db_path)) as conn:
            conn.execute(
                """
                INSERT INTO executions (
                    execution_id, contract_id, issuer_did, receiver_did,
                    joules_used, status, created_at, ser_summary
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    execution_id,
                    contract_id,
                    issuer_did,
                    receiver_did,
                    joules_used,
                    status,
                    now,
                    ser_json,
                ),
            )
            conn.commit()

        log.info(
            "execution_recorded",
            execution_id=execution_id,
            contract_id=contract_id,
            status=status,
            joules=joules_used,
        )

    async def get_execution_history(
        self, did_key: str, as_issuer: bool = True, limit: int = 100
    ) -> List[ExecutionRecord]:
        """Get execution history for an agent."""
        field = "issuer_did" if as_issuer else "receiver_did"
        with sqlite3.connect(str(self._db_path)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                f"""
                SELECT * FROM executions
                WHERE {field} = ?
                ORDER BY created_at DESC
                LIMIT ?
            """,
                (did_key, limit),
            ).fetchall()

            return [
                ExecutionRecord(
                    execution_id=row["execution_id"],
                    contract_id=row["contract_id"],
                    issuer_did=row["issuer_did"],
                    receiver_did=row["receiver_did"],
                    joules_used=row["joules_used"],
                    status=row["status"],
                    created_at=row["created_at"],
                    ser_summary=row["ser_summary"],
                )
                for row in rows
            ]

    async def calculate_reputation_from_history(self, did_key: str) -> float:
        """Calculate reputation score from execution history."""
        with sqlite3.connect(str(self._db_path)) as conn:
            conn.row_factory = sqlite3.Row
            # Get execution stats as receiver (executor)
            row = conn.execute(
                """
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) as successful,
                    AVG(joules_used) as avg_joules
                FROM executions
                WHERE receiver_did = ?
            """,
                (did_key,),
            ).fetchone()

            if row is None or row["total"] == 0:
                return 0.5  # Default for new agents

            total = row["total"]
            successful = row["successful"] or 0
            success_rate = successful / total

            # Efficiency factor: lower avg joules = better
            avg_joules = row["avg_joules"] or 100
            efficiency = max(0.5, 1.0 - (avg_joules / 10000))

            reputation = success_rate * efficiency
            return round(max(0.0, min(1.0, reputation)), 4)

    async def deactivate_agent(self, did_key: str) -> None:
        """Deactivate an agent (soft delete)."""
        with sqlite3.connect(str(self._db_path)) as conn:
            conn.execute(
                "UPDATE agents SET is_active = 0 WHERE did_key = ?",
                (did_key,),
            )
            conn.commit()
        log.info("agent_deactivated", did_key=did_key)

    async def get_stats(self) -> Dict[str, Any]:
        """Get registry statistics."""
        with sqlite3.connect(str(self._db_path)) as conn:
            agent_count = conn.execute(
                "SELECT COUNT(*) FROM agents WHERE is_active = 1"
            ).fetchone()[0]

            execution_count = conn.execute(
                "SELECT COUNT(*) FROM executions"
            ).fetchone()[0]

            avg_reputation = conn.execute(
                "SELECT AVG(reputation_score) FROM agents WHERE is_active = 1"
            ).fetchone()[0] or 0.0

            total_joules = conn.execute(
                "SELECT SUM(joules_used) FROM executions WHERE status = 'success'"
            ).fetchone()[0] or 0.0

            return {
                "active_agents": agent_count,
                "total_executions": execution_count,
                "average_reputation": round(avg_reputation, 4),
                "total_joules_consumed": round(total_joules, 4),
            }

    async def search_agents(self, query: SearchQuery) -> List[AgentRecord]:
        """Search agents by query criteria."""
        with sqlite3.connect(str(self._db_path)) as conn:
            conn.row_factory = sqlite3.Row

            # Build query dynamically
            conditions = ["is_active = 1"]
            params: List[Any] = []

            if query.capability:
                conditions.append("capabilities LIKE ?")
                params.append(f'%"{query.capability}"%')

            if query.min_reputation > 0:
                conditions.append("reputation_score >= ?")
                params.append(query.min_reputation)

            if query.name_pattern:
                conditions.append("name LIKE ?")
                params.append(f"%{query.name_pattern}%")

            where_clause = " AND ".join(conditions)

            # Add limit and offset
            params.extend([query.limit, query.offset])

            rows = conn.execute(
                f"""
                SELECT * FROM agents
                WHERE {where_clause}
                ORDER BY reputation_score DESC
                LIMIT ? OFFSET ?
            """,
                params,
            ).fetchall()

            return [
                AgentRecord(
                    did_key=row["did_key"],
                    pubkey_pem=row["pubkey_pem"],
                    endpoint_url=row["endpoint_url"],
                    name=row["name"],
                    description=row["description"],
                    capabilities=json.loads(row["capabilities"]),
                    reputation_score=row["reputation_score"],
                    joule_rate=row["joule_rate"],
                    version=row["version"],
                    created_at=row["created_at"],
                    last_seen=row["last_seen"],
                    is_active=bool(row["is_active"]),
                )
                for row in rows
            ]

    async def record_interaction(self, interaction: InteractionRecord) -> None:
        """Record an interaction for reputation tracking."""
        with sqlite3.connect(str(self._db_path)) as conn:
            metadata_json = (
                json.dumps(interaction.metadata) if interaction.metadata else None
            )
            conn.execute(
                """
                INSERT INTO interactions (
                    interaction_id, contract_id, issuer_did, receiver_did,
                    rating, joules_used, status, timestamp, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    interaction.interaction_id,
                    interaction.contract_id,
                    interaction.issuer_did,
                    interaction.receiver_did,
                    interaction.rating,
                    interaction.joules_used,
                    interaction.status,
                    interaction.timestamp.isoformat(),
                    metadata_json,
                ),
            )
            conn.commit()

        log.info(
            "interaction_recorded",
            interaction_id=interaction.interaction_id,
            contract_id=interaction.contract_id,
            rating=interaction.rating,
        )

    async def get_history(
        self, did_key: str, limit: int = 100
    ) -> List[InteractionRecord]:
        """Get interaction history for an agent."""
        with sqlite3.connect(str(self._db_path)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT * FROM interactions
                WHERE receiver_did = ?
                ORDER BY timestamp DESC
                LIMIT ?
            """,
                (did_key, limit),
            ).fetchall()

            return [
                InteractionRecord(
                    interaction_id=row["interaction_id"],
                    contract_id=row["contract_id"],
                    issuer_did=row["issuer_did"],
                    receiver_did=row["receiver_did"],
                    rating=row["rating"],
                    joules_used=row["joules_used"],
                    status=row["status"],
                    timestamp=datetime.fromisoformat(row["timestamp"]),
                    metadata=json.loads(row["metadata"]) if row["metadata"] else None,
                )
                for row in rows
            ]

    async def close(self) -> None:
        """Close the backend - no-op for SQLite."""
        pass
