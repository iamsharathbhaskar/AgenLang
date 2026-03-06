"""PostgreSQL backend implementation for agent registry.

Provides PostgreSQL-backed storage for agent identities, capabilities,
reputation scores, and execution history with connection pooling.
"""

import json
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, AsyncGenerator, Dict, List, Optional

import structlog

from .base import (
    AgentRecord,
    ExecutionRecord,
    InteractionRecord,
    RegistryBackend,
    SearchQuery,
)

log = structlog.get_logger()

# Try to import asyncpg, provide fallback with clear error
try:
    import asyncpg
    from asyncpg import Pool
    ASYNCpg_AVAILABLE = True
except ImportError:
    ASYNCpg_AVAILABLE = False
    Pool = Any  # type: ignore


class PostgresBackend(RegistryBackend):
    """PostgreSQL-backed agent registry with connection pooling.

    Supports agent registration, discovery by capability,
    reputation scoring, and execution history.
    """

    def __init__(self, dsn: Optional[str] = None) -> None:
        """Initialize PostgreSQL backend.

        Args:
            dsn: PostgreSQL connection string.
                 Defaults to DATABASE_URL env var.
        """
        if not ASYNCpg_AVAILABLE:
            raise ImportError(
                "asyncpg is required for PostgreSQL backend. "
                "Install with: pip install asyncpg"
            )

        self._dsn = dsn or os.environ.get("DATABASE_URL")
        if not self._dsn:
            raise ValueError(
                "PostgreSQL DSN required. Set DATABASE_URL env var or pass dsn parameter."
            )

        self._pool: Optional[Pool] = None
        self._initialized = False

    async def _get_pool(self) -> Pool:
        """Get or create connection pool."""
        if self._pool is None:
            self._pool = await asyncpg.create_pool(
                self._dsn,
                min_size=2,
                max_size=10,
                command_timeout=60,
            )
        return self._pool

    @asynccontextmanager
    async def _acquire_conn(self) -> AsyncGenerator[asyncpg.Connection, None]:
        """Acquire connection from pool."""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            yield conn

    async def init_schema(self) -> None:
        """Initialize database schema."""
        async with self._acquire_conn() as conn:
            # Agents table
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS agents (
                    did_key TEXT PRIMARY KEY,
                    pubkey_pem TEXT NOT NULL,
                    endpoint_url TEXT NOT NULL,
                    name TEXT DEFAULT 'Unknown Agent',
                    description TEXT DEFAULT '',
                    capabilities JSONB NOT NULL,
                    reputation_score REAL DEFAULT 0.5,
                    joule_rate REAL DEFAULT 1.0,
                    version TEXT DEFAULT '0.1.0',
                    created_at TIMESTAMPTZ NOT NULL,
                    last_seen TIMESTAMPTZ NOT NULL,
                    is_active BOOLEAN DEFAULT TRUE
                )
            """
            )

            # Execution history table
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS executions (
                    execution_id TEXT PRIMARY KEY,
                    contract_id TEXT NOT NULL,
                    issuer_did TEXT NOT NULL,
                    receiver_did TEXT NOT NULL,
                    joules_used REAL NOT NULL,
                    status TEXT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL,
                    ser_summary JSONB
                )
            """
            )

            # Interactions table (for reputation tracking)
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS interactions (
                    interaction_id TEXT PRIMARY KEY,
                    contract_id TEXT NOT NULL,
                    issuer_did TEXT NOT NULL,
                    receiver_did TEXT NOT NULL,
                    rating REAL NOT NULL,
                    joules_used REAL NOT NULL,
                    status TEXT NOT NULL,
                    timestamp TIMESTAMPTZ NOT NULL,
                    metadata JSONB
                )
            """
            )

            # Reputation history table
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS reputation_history (
                    id SERIAL PRIMARY KEY,
                    did_key TEXT NOT NULL REFERENCES agents(did_key) ON DELETE CASCADE,
                    old_score REAL NOT NULL,
                    new_score REAL NOT NULL,
                    contract_id TEXT,
                    timestamp TIMESTAMPTZ NOT NULL
                )
            """
            )

            # Indexes for performance
            await conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_agents_capabilities
                ON agents USING GIN (capabilities)
            """
            )
            await conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_agents_reputation
                ON agents(reputation_score DESC)
            """
            )
            await conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_agents_name
                ON agents(name)
            """
            )
            await conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_executions_issuer
                ON executions(issuer_did)
            """
            )
            await conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_executions_receiver
                ON executions(receiver_did)
            """
            )
            await conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_executions_created
                ON executions(created_at DESC)
            """
            )
            await conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_interactions_receiver
                ON interactions(receiver_did)
            """
            )
            await conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_interactions_timestamp
                ON interactions(timestamp DESC)
            """
            )
            await conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_reputation_did
                ON reputation_history(did_key, timestamp DESC)
            """
            )

        self._initialized = True
        log.debug("postgres_schema_initialized")

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
        now = datetime.now(timezone.utc)

        async with self._acquire_conn() as conn:
            # UPSERT using PostgreSQL syntax
            await conn.execute(
                """
                INSERT INTO agents (
                    did_key, pubkey_pem, endpoint_url, name, description,
                    capabilities, reputation_score, joule_rate, version,
                    created_at, last_seen, is_active
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $10, TRUE)
                ON CONFLICT (did_key) DO UPDATE SET
                    pubkey_pem = EXCLUDED.pubkey_pem,
                    endpoint_url = EXCLUDED.endpoint_url,
                    name = EXCLUDED.name,
                    description = EXCLUDED.description,
                    capabilities = EXCLUDED.capabilities,
                    joule_rate = EXCLUDED.joule_rate,
                    version = EXCLUDED.version,
                    last_seen = EXCLUDED.last_seen,
                    is_active = TRUE
            """,
                did_key,
                pubkey_pem,
                endpoint_url,
                name,
                description,
                json.dumps(capabilities),
                0.5,  # Initial reputation
                joule_rate,
                version,
                now,
            )

        log.info(
            "agent_registered", did_key=did_key, name=name, endpoint=endpoint_url
        )
        agent = await self.get_agent(did_key)
        assert agent is not None
        return agent

    async def get_agent(self, did_key: str) -> Optional[AgentRecord]:
        """Get agent by DID:key."""
        async with self._acquire_conn() as conn:
            row = await conn.fetchrow(
                """
                SELECT * FROM agents
                WHERE did_key = $1 AND is_active = TRUE
            """,
                did_key,
            )

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
                created_at=row["created_at"].isoformat(),
                last_seen=row["last_seen"].isoformat(),
                is_active=row["is_active"],
            )

    async def find_agents_by_capability(
        self, capability: str, min_reputation: float = 0.0
    ) -> List[AgentRecord]:
        """Find agents with a specific capability."""
        async with self._acquire_conn() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM agents
                WHERE capabilities @> $1::jsonb
                AND reputation_score >= $2
                AND is_active = TRUE
                ORDER BY reputation_score DESC
            """,
                json.dumps([capability]),
                min_reputation,
            )

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
                    created_at=row["created_at"].isoformat(),
                    last_seen=row["last_seen"].isoformat(),
                    is_active=row["is_active"],
                )
                for row in rows
            ]

    async def list_agents(self, limit: int = 100) -> List[AgentRecord]:
        """List all registered agents."""
        async with self._acquire_conn() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM agents
                WHERE is_active = TRUE
                ORDER BY last_seen DESC
                LIMIT $1
            """,
                limit,
            )

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
                    created_at=row["created_at"].isoformat(),
                    last_seen=row["last_seen"].isoformat(),
                    is_active=row["is_active"],
                )
                for row in rows
            ]

    async def update_reputation(self, did_key: str, new_score: float) -> None:
        """Update agent reputation score."""
        clamped_score = max(0.0, min(1.0, new_score))

        async with self._acquire_conn() as conn:
            # Get old score for history
            row = await conn.fetchrow(
                "SELECT reputation_score FROM agents WHERE did_key = $1",
                did_key,
            )
            old_score = row["reputation_score"] if row else 0.5

            # Update agent
            await conn.execute(
                "UPDATE agents SET reputation_score = $1 WHERE did_key = $2",
                clamped_score,
                did_key,
            )

            # Record history
            now = datetime.now(timezone.utc)
            await conn.execute(
                """
                INSERT INTO reputation_history
                (did_key, old_score, new_score, timestamp)
                VALUES ($1, $2, $3, $4)
            """,
                did_key,
                old_score,
                clamped_score,
                now,
            )

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
        now = datetime.now(timezone.utc)

        async with self._acquire_conn() as conn:
            await conn.execute(
                """
                INSERT INTO executions (
                    execution_id, contract_id, issuer_did, receiver_did,
                    joules_used, status, created_at, ser_summary
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                ON CONFLICT (execution_id) DO NOTHING
            """,
                execution_id,
                contract_id,
                issuer_did,
                receiver_did,
                joules_used,
                status,
                now,
                json.dumps(ser_summary) if ser_summary else None,
            )

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

        async with self._acquire_conn() as conn:
            rows = await conn.fetch(
                f"""
                SELECT * FROM executions
                WHERE {field} = $1
                ORDER BY created_at DESC
                LIMIT $2
            """,
                did_key,
                limit,
            )

            return [
                ExecutionRecord(
                    execution_id=row["execution_id"],
                    contract_id=row["contract_id"],
                    issuer_did=row["issuer_did"],
                    receiver_did=row["receiver_did"],
                    joules_used=row["joules_used"],
                    status=row["status"],
                    created_at=row["created_at"].isoformat(),
                    ser_summary=row["ser_summary"],
                )
                for row in rows
            ]

    async def calculate_reputation_from_history(self, did_key: str) -> float:
        """Calculate reputation score from execution history."""
        async with self._acquire_conn() as conn:
            row = await conn.fetchrow(
                """
                SELECT
                    COUNT(*) as total,
                    COUNT(*) FILTER (WHERE status = 'success') as successful,
                    AVG(joules_used) as avg_joules
                FROM executions
                WHERE receiver_did = $1
            """,
                did_key,
            )

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
        async with self._acquire_conn() as conn:
            await conn.execute(
                "UPDATE agents SET is_active = FALSE WHERE did_key = $1",
                did_key,
            )
        log.info("agent_deactivated", did_key=did_key)

    async def get_stats(self) -> Dict[str, Any]:
        """Get registry statistics."""
        async with self._acquire_conn() as conn:
            row = await conn.fetchrow(
                """
                SELECT
                    COUNT(*) FILTER (WHERE is_active) as active_agents,
                    (SELECT COUNT(*) FROM executions) as total_executions,
                    COALESCE(
                        AVG(reputation_score) FILTER (WHERE is_active), 0
                    ) as avg_reputation,
                    COALESCE(
                        (SELECT SUM(joules_used)
                         FROM executions WHERE status = 'success'), 0
                    ) as total_joules
                FROM agents
            """
            )

            return {
                "active_agents": row["active_agents"],
                "total_executions": row["total_executions"],
                "average_reputation": round(row["avg_reputation"] or 0, 4),
                "total_joules_consumed": round(row["total_joules"] or 0, 4),
            }

    async def search_agents(self, query: SearchQuery) -> List[AgentRecord]:
        """Search agents by query criteria."""
        conditions = ["is_active = TRUE"]
        params: List[Any] = []
        param_idx = 1

        if query.capability:
            conditions.append(f"capabilities @> ${param_idx}::jsonb")
            params.append(json.dumps([query.capability]))
            param_idx += 1

        if query.min_reputation > 0:
            conditions.append(f"reputation_score >= ${param_idx}")
            params.append(query.min_reputation)
            param_idx += 1

        if query.name_pattern:
            conditions.append(f"name ILIKE ${param_idx}")
            params.append(f"%{query.name_pattern}%")
            param_idx += 1

        where_clause = " AND ".join(conditions)

        # Add limit and offset
        params.extend([query.limit, query.offset])

        async with self._acquire_conn() as conn:
            rows = await conn.fetch(
                f"""
                SELECT * FROM agents
                WHERE {where_clause}
                ORDER BY reputation_score DESC
                LIMIT ${param_idx} OFFSET ${param_idx + 1}
            """,
                *params,
            )

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
                    created_at=row["created_at"].isoformat(),
                    last_seen=row["last_seen"].isoformat(),
                    is_active=row["is_active"],
                )
                for row in rows
            ]

    async def record_interaction(self, interaction: InteractionRecord) -> None:
        """Record an interaction for reputation tracking."""
        async with self._acquire_conn() as conn:
            await conn.execute(
                """
                INSERT INTO interactions (
                    interaction_id, contract_id, issuer_did, receiver_did,
                    rating, joules_used, status, timestamp, metadata
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                ON CONFLICT (interaction_id) DO NOTHING
            """,
                interaction.interaction_id,
                interaction.contract_id,
                interaction.issuer_did,
                interaction.receiver_did,
                interaction.rating,
                interaction.joules_used,
                interaction.status,
                interaction.timestamp,
                json.dumps(interaction.metadata) if interaction.metadata else None,
            )

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
        async with self._acquire_conn() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM interactions
                WHERE receiver_did = $1
                ORDER BY timestamp DESC
                LIMIT $2
            """,
                did_key,
                limit,
            )

            return [
                InteractionRecord(
                    interaction_id=row["interaction_id"],
                    contract_id=row["contract_id"],
                    issuer_did=row["issuer_did"],
                    receiver_did=row["receiver_did"],
                    rating=row["rating"],
                    joules_used=row["joules_used"],
                    status=row["status"],
                    timestamp=row["timestamp"],
                    metadata=json.loads(row["metadata"]) if row["metadata"] else None,
                )
                for row in rows
            ]

    async def close(self) -> None:
        """Close connection pool."""
        if self._pool is not None:
            await self._pool.close()
            self._pool = None
            log.debug("postgres_pool_closed")
