"""Agent Registry — discovery, reputation, and capability tracking.

Provides unified interface for agent registration, discovery,
reputation scoring, and execution history.

Backends:
    - SQLite: Default local file-based storage (backward compatible)
    - PostgreSQL: Production deployment with connection pooling

Configuration:
    Set DATABASE_URL environment variable:
    - sqlite:///path/to/registry.db (default)
    - postgresql://user:pass@host/db
"""

from pathlib import Path
from typing import Any, Dict, List, Optional

import structlog

from agenlang.backends import (
    AgentRecord,
    ExecutionRecord,
    InteractionRecord,
    RegistryBackend,
    SearchQuery,
    create_backend,
)

log = structlog.get_logger()


class AgentRegistry:
    """Agent registry with pluggable storage backends.

    Supports agent registration, discovery by capability,
    reputation scoring, and execution history.

    Examples:
        >>> # Default SQLite backend
        >>> registry = AgentRegistry()
        >>>
        >>> # Explicit SQLite path
        >>> registry = AgentRegistry(db_path=Path("/tmp/registry.db"))
        >>>
        >>> # PostgreSQL via DATABASE_URL
        >>> import os
        >>> os.environ["DATABASE_URL"] = "postgresql://user:pass@localhost/db"
        >>> registry = AgentRegistry()
    """

    def __init__(
        self,
        db_path: Optional[Path] = None,
        database_url: Optional[str] = None,
        backend: Optional[RegistryBackend] = None,
        auto_init: bool = True,
    ) -> None:
        """Initialize registry.

        Args:
            db_path: Path to SQLite database (backward compatibility).
                Ignored if backend or database_url is provided.
            database_url: Database connection string.
                - sqlite:///path/to/db.db for SQLite
                - postgresql://user:pass@host/db for PostgreSQL
            backend: Pre-configured backend instance (takes precedence).
            auto_init: If True (default), automatically initialize schema.
                Set to False for async contexts where you'll call init() manually.
        """
        if backend is not None:
            self._backend = backend
        elif database_url is not None:
            self._backend = create_backend(database_url=database_url)
        elif db_path is not None:
            self._backend = create_backend(db_path=db_path)
        else:
            self._backend = create_backend()

        log.debug(
            "registry_initialized",
            backend_type=type(self._backend).__name__,
        )

        # Auto-initialize schema for backward compatibility
        if auto_init:
            self._sync_init_schema()

    def _sync_init_schema(self) -> None:
        """Synchronously initialize schema."""
        import asyncio

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    pool.submit(asyncio.run, self._backend.init_schema()).result()
            else:
                loop.run_until_complete(self._backend.init_schema())
        except RuntimeError:
            asyncio.run(self._backend.init_schema())

    async def init(self) -> None:
        """Initialize the registry schema (async).

        Only needed if auto_init=False was passed to __init__.
        """
        await self._backend.init_schema()
        log.debug("registry_schema_initialized")

    def register_agent(
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
        """Register a new agent or update existing (sync wrapper).

        Args:
            did_key: Agent DID:key identifier
            pubkey_pem: PEM-encoded public key
            endpoint_url: A2A endpoint URL
            capabilities: List of capability strings
            name: Human-readable name
            description: Agent description
            joule_rate: Cost per Joule for services
            version: Agent software version

        Returns:
            AgentRecord of registered agent
        """
        import asyncio

        # Run async method in sync context
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # We're in an async context, create task
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future = pool.submit(
                        asyncio.run,
                        self._backend.register_agent(
                            did_key=did_key,
                            pubkey_pem=pubkey_pem,
                            endpoint_url=endpoint_url,
                            capabilities=capabilities,
                            name=name,
                            description=description,
                            joule_rate=joule_rate,
                            version=version,
                        ),
                    )
                    return future.result()
            else:
                return loop.run_until_complete(
                    self._backend.register_agent(
                        did_key=did_key,
                        pubkey_pem=pubkey_pem,
                        endpoint_url=endpoint_url,
                        capabilities=capabilities,
                        name=name,
                        description=description,
                        joule_rate=joule_rate,
                        version=version,
                    )
                )
        except RuntimeError:
            # No event loop, create new one
            return asyncio.run(
                self._backend.register_agent(
                    did_key=did_key,
                    pubkey_pem=pubkey_pem,
                    endpoint_url=endpoint_url,
                    capabilities=capabilities,
                    name=name,
                    description=description,
                    joule_rate=joule_rate,
                    version=version,
                )
            )

    def get_agent(self, did_key: str) -> Optional[AgentRecord]:
        """Get agent by DID:key (sync wrapper).

        Args:
            did_key: Agent identifier

        Returns:
            AgentRecord if found, None otherwise
        """
        import asyncio

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future = pool.submit(
                        asyncio.run,
                        self._backend.get_agent(did_key),
                    )
                    return future.result()
            else:
                return loop.run_until_complete(self._backend.get_agent(did_key))
        except RuntimeError:
            return asyncio.run(self._backend.get_agent(did_key))

    def find_agents_by_capability(
        self, capability: str, min_reputation: float = 0.0
    ) -> List[AgentRecord]:
        """Find agents with a specific capability (sync wrapper).

        Args:
            capability: Capability to search for (e.g., "net:read")
            min_reputation: Minimum reputation score (0.0-1.0)

        Returns:
            List of matching agents, sorted by reputation
        """
        import asyncio

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future = pool.submit(
                        asyncio.run,
                        self._backend.find_agents_by_capability(
                            capability, min_reputation
                        ),
                    )
                    return future.result()
            else:
                return loop.run_until_complete(
                    self._backend.find_agents_by_capability(capability, min_reputation)
                )
        except RuntimeError:
            return asyncio.run(
                self._backend.find_agents_by_capability(capability, min_reputation)
            )

    def list_agents(self, limit: int = 100) -> List[AgentRecord]:
        """List all registered agents (sync wrapper).

        Args:
            limit: Maximum number to return

        Returns:
            List of agents
        """
        import asyncio

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future = pool.submit(
                        asyncio.run,
                        self._backend.list_agents(limit),
                    )
                    return future.result()
            else:
                return loop.run_until_complete(self._backend.list_agents(limit))
        except RuntimeError:
            return asyncio.run(self._backend.list_agents(limit))

    def update_reputation(self, did_key: str, new_score: float) -> None:
        """Update agent reputation score (sync wrapper).

        Args:
            did_key: Agent identifier
            new_score: New reputation score (0.0-1.0, clamped)
        """
        import asyncio

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future = pool.submit(
                        asyncio.run,
                        self._backend.update_reputation(did_key, new_score),
                    )
                    return future.result()
            else:
                return loop.run_until_complete(
                    self._backend.update_reputation(did_key, new_score)
                )
        except RuntimeError:
            return asyncio.run(
                self._backend.update_reputation(did_key, new_score)
            )

    def record_execution(
        self,
        execution_id: str,
        contract_id: str,
        issuer_did: str,
        receiver_did: str,
        joules_used: float,
        status: str,
        ser_summary: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Record a contract execution (sync wrapper).

        Args:
            execution_id: Unique execution identifier
            contract_id: Contract URN
            issuer_did: Issuer agent DID
            receiver_did: Receiver/executor agent DID
            joules_used: Joules consumed
            status: Execution status (success, failed, timeout)
            ser_summary: Optional SER summary for analytics
        """
        import asyncio

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future = pool.submit(
                        asyncio.run,
                        self._backend.record_execution(
                            execution_id=execution_id,
                            contract_id=contract_id,
                            issuer_did=issuer_did,
                            receiver_did=receiver_did,
                            joules_used=joules_used,
                            status=status,
                            ser_summary=ser_summary,
                        ),
                    )
                    return future.result()
            else:
                return loop.run_until_complete(
                    self._backend.record_execution(
                        execution_id=execution_id,
                        contract_id=contract_id,
                        issuer_did=issuer_did,
                        receiver_did=receiver_did,
                        joules_used=joules_used,
                        status=status,
                        ser_summary=ser_summary,
                    )
                )
        except RuntimeError:
            return asyncio.run(
                self._backend.record_execution(
                    execution_id=execution_id,
                    contract_id=contract_id,
                    issuer_did=issuer_did,
                    receiver_did=receiver_did,
                    joules_used=joules_used,
                    status=status,
                    ser_summary=ser_summary,
                )
            )

    def get_execution_history(
        self, did_key: str, as_issuer: bool = True, limit: int = 100
    ) -> List[ExecutionRecord]:
        """Get execution history for an agent (sync wrapper).

        Args:
            did_key: Agent DID
            as_issuer: If True, get contracts issued by agent; else received
            limit: Maximum records

        Returns:
            List of execution records
        """
        import asyncio

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future = pool.submit(
                        asyncio.run,
                        self._backend.get_execution_history(did_key, as_issuer, limit),
                    )
                    return future.result()
            else:
                return loop.run_until_complete(
                    self._backend.get_execution_history(did_key, as_issuer, limit)
                )
        except RuntimeError:
            return asyncio.run(
                self._backend.get_execution_history(did_key, as_issuer, limit)
            )

    def calculate_reputation_from_history(self, did_key: str) -> float:
        """Calculate reputation score from execution history (sync wrapper).

        Args:
            did_key: Agent DID

        Returns:
            Reputation score (0.0-1.0)
        """
        import asyncio

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future = pool.submit(
                        asyncio.run,
                        self._backend.calculate_reputation_from_history(did_key),
                    )
                    return future.result()
            else:
                return loop.run_until_complete(
                    self._backend.calculate_reputation_from_history(did_key)
                )
        except RuntimeError:
            return asyncio.run(
                self._backend.calculate_reputation_from_history(did_key)
            )

    def deactivate_agent(self, did_key: str) -> None:
        """Deactivate an agent (soft delete) (sync wrapper).

        Args:
            did_key: Agent to deactivate
        """
        import asyncio

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future = pool.submit(
                        asyncio.run,
                        self._backend.deactivate_agent(did_key),
                    )
                    return future.result()
            else:
                return loop.run_until_complete(
                    self._backend.deactivate_agent(did_key)
                )
        except RuntimeError:
            return asyncio.run(self._backend.deactivate_agent(did_key))

    def get_stats(self) -> Dict[str, Any]:
        """Get registry statistics (sync wrapper).

        Returns:
            Dict with counts and averages
        """
        import asyncio

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future = pool.submit(
                        asyncio.run,
                        self._backend.get_stats(),
                    )
                    return future.result()
            else:
                return loop.run_until_complete(self._backend.get_stats())
        except RuntimeError:
            return asyncio.run(self._backend.get_stats())

    def search_agents(
        self,
        capability: Optional[str] = None,
        min_reputation: float = 0.0,
        name_pattern: Optional[str] = None,
        limit: int = 100,
    ) -> List[AgentRecord]:
        """Search agents by criteria (sync wrapper).

        Args:
            capability: Filter by capability
            min_reputation: Minimum reputation score
            name_pattern: Name substring match
            limit: Maximum results

        Returns:
            List of matching agents
        """
        import asyncio

        query = SearchQuery(
            capability=capability,
            min_reputation=min_reputation,
            name_pattern=name_pattern,
            limit=limit,
        )

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future = pool.submit(
                        asyncio.run,
                        self._backend.search_agents(query),
                    )
                    return future.result()
            else:
                return loop.run_until_complete(self._backend.search_agents(query))
        except RuntimeError:
            return asyncio.run(self._backend.search_agents(query))

    def record_interaction(self, interaction: InteractionRecord) -> None:
        """Record an interaction for reputation tracking (sync wrapper).

        Args:
            interaction: InteractionRecord to store
        """
        import asyncio

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future = pool.submit(
                        asyncio.run,
                        self._backend.record_interaction(interaction),
                    )
                    return future.result()
            else:
                return loop.run_until_complete(
                    self._backend.record_interaction(interaction)
                )
        except RuntimeError:
            return asyncio.run(self._backend.record_interaction(interaction))

    def get_history(self, did_key: str, limit: int = 100) -> List[InteractionRecord]:
        """Get interaction history for an agent (sync wrapper).

        Args:
            did_key: Agent DID
            limit: Maximum records to return

        Returns:
            List of interaction records
        """
        import asyncio

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future = pool.submit(
                        asyncio.run,
                        self._backend.get_history(did_key, limit),
                    )
                    return future.result()
            else:
                return loop.run_until_complete(
                    self._backend.get_history(did_key, limit)
                )
        except RuntimeError:
            return asyncio.run(self._backend.get_history(did_key, limit))

    async def close(self) -> None:
        """Close the registry and cleanup resources."""
        await self._backend.close()
        log.debug("registry_closed")

    # Backward compatibility: expose dataclasses at module level
    AgentRecord = AgentRecord
    ExecutionRecord = ExecutionRecord
