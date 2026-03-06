"""Tests for registry backends (SQLite and PostgreSQL).

These tests validate that both backends implement the RegistryBackend
interface correctly and produce consistent results.
"""

import asyncio
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agenlang.backends import (
    AgentRecord,
    ExecutionRecord,
    InteractionRecord,
    SearchQuery,
    create_backend,
)
from agenlang.backends.base import RegistryBackend
from agenlang.backends.sqlite import SQLiteBackend


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def tmp_db_path(tmp_path: Path) -> Path:
    """Provide temporary database path."""
    return tmp_path / "test_registry.db"


@pytest.fixture
def sqlite_backend(tmp_db_path: Path) -> Generator[SQLiteBackend, None, None]:
    """Create initialized SQLite backend."""
    backend = SQLiteBackend(db_path=tmp_db_path)
    asyncio.run(backend.init_schema())
    yield backend
    # Cleanup
    asyncio.run(backend.close())


@pytest.fixture
def sample_agent_data() -> dict:
    """Sample agent data for tests."""
    return {
        "did_key": "did:key:z6Mkexample",
        "pubkey_pem": "-----BEGIN PUBLIC KEY-----\ntest\n-----END PUBLIC KEY-----",
        "endpoint_url": "http://localhost:8000",
        "capabilities": ["net:read", "compute:write"],
        "name": "Test Agent",
        "description": "A test agent",
        "joule_rate": 2.5,
        "version": "1.0.0",
    }


@pytest.fixture
def mock_postgres_backend() -> MagicMock:
    """Create mock PostgreSQL backend for testing without asyncpg."""
    backend = MagicMock(spec=RegistryBackend)
    backend.init_schema = AsyncMock()
    backend.register_agent = AsyncMock(return_value=MagicMock(spec=AgentRecord))
    backend.get_agent = AsyncMock(return_value=None)
    backend.find_agents_by_capability = AsyncMock(return_value=[])
    backend.list_agents = AsyncMock(return_value=[])
    backend.update_reputation = AsyncMock()
    backend.record_execution = AsyncMock()
    backend.get_execution_history = AsyncMock(return_value=[])
    backend.calculate_reputation_from_history = AsyncMock(return_value=0.5)
    backend.deactivate_agent = AsyncMock()
    backend.get_stats = AsyncMock(return_value={
        "active_agents": 0,
        "total_executions": 0,
        "average_reputation": 0.0,
        "total_joules_consumed": 0.0,
    })
    backend.search_agents = AsyncMock(return_value=[])
    backend.record_interaction = AsyncMock()
    backend.get_history = AsyncMock(return_value=[])
    backend.close = AsyncMock()
    return backend


# ============================================================================
# SQLite Backend Tests
# ============================================================================


class TestSQLiteBackend:
    """Test suite for SQLite backend implementation."""

    @pytest.mark.asyncio
    async def test_init_schema_creates_tables(self, tmp_db_path: Path) -> None:
        """Schema initialization creates required tables."""
        backend = SQLiteBackend(db_path=tmp_db_path)
        await backend.init_schema()

        # Verify tables exist by querying them
        import sqlite3
        with sqlite3.connect(str(tmp_db_path)) as conn:
            tables = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
            table_names = {t[0] for t in tables}

        assert "agents" in table_names
        assert "executions" in table_names
        assert "interactions" in table_names
        assert "reputation_history" in table_names

    @pytest.mark.asyncio
    async def test_register_and_get_agent(
        self, sqlite_backend: SQLiteBackend, sample_agent_data: dict
    ) -> None:
        """Can register and retrieve an agent."""
        agent = await sqlite_backend.register_agent(**sample_agent_data)

        assert agent.did_key == sample_agent_data["did_key"]
        assert agent.name == sample_agent_data["name"]
        assert agent.capabilities == sample_agent_data["capabilities"]
        assert agent.reputation_score == 0.5  # Default

        # Retrieve
        retrieved = await sqlite_backend.get_agent(sample_agent_data["did_key"])
        assert retrieved is not None
        assert retrieved.name == sample_agent_data["name"]
        assert retrieved.endpoint_url == sample_agent_data["endpoint_url"]

    @pytest.mark.asyncio
    async def test_get_nonexistent_agent(self, sqlite_backend: SQLiteBackend) -> None:
        """Getting nonexistent agent returns None."""
        result = await sqlite_backend.get_agent("did:key:nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_list_agents(
        self, sqlite_backend: SQLiteBackend, sample_agent_data: dict
    ) -> None:
        """Can list registered agents."""
        for i in range(3):
            data = {**sample_agent_data, "did_key": f"did:key:z{i}", "name": f"Agent {i}"}
            await sqlite_backend.register_agent(**data)

        agents = await sqlite_backend.list_agents()
        assert len(agents) == 3

    @pytest.mark.asyncio
    async def test_find_by_capability(
        self, sqlite_backend: SQLiteBackend, sample_agent_data: dict
    ) -> None:
        """Can find agents by capability."""
        net_agent = {
            **sample_agent_data,
            "did_key": "did:key:net",
            "capabilities": ["net:read", "net:write"],
            "name": "Net Agent",
        }
        compute_agent = {
            **sample_agent_data,
            "did_key": "did:key:compute",
            "capabilities": ["compute:read"],
            "name": "Compute Agent",
        }
        await sqlite_backend.register_agent(**net_agent)
        await sqlite_backend.register_agent(**compute_agent)

        net_agents = await sqlite_backend.find_agents_by_capability("net:read")
        assert len(net_agents) == 1
        assert net_agents[0].name == "Net Agent"

        # With min reputation filter
        await sqlite_backend.update_reputation("did:key:net", 0.8)
        high_rep = await sqlite_backend.find_agents_by_capability(
            "net:read", min_reputation=0.9
        )
        assert len(high_rep) == 0

    @pytest.mark.asyncio
    async def test_update_reputation(
        self, sqlite_backend: SQLiteBackend, sample_agent_data: dict
    ) -> None:
        """Can update agent reputation."""
        await sqlite_backend.register_agent(**sample_agent_data)

        await sqlite_backend.update_reputation(sample_agent_data["did_key"], 0.95)
        agent = await sqlite_backend.get_agent(sample_agent_data["did_key"])
        assert agent is not None
        assert agent.reputation_score == 0.95

        # Test clamping
        await sqlite_backend.update_reputation(sample_agent_data["did_key"], 1.5)
        agent = await sqlite_backend.get_agent(sample_agent_data["did_key"])
        assert agent is not None
        assert agent.reputation_score == 1.0

        await sqlite_backend.update_reputation(sample_agent_data["did_key"], -0.5)
        agent = await sqlite_backend.get_agent(sample_agent_data["did_key"])
        assert agent is not None
        assert agent.reputation_score == 0.0

    @pytest.mark.asyncio
    async def test_record_execution(
        self, sqlite_backend: SQLiteBackend, sample_agent_data: dict
    ) -> None:
        """Can record contract execution."""
        await sqlite_backend.record_execution(
            execution_id="exec-001",
            contract_id="urn:agenlang:exec:abc123",
            issuer_did="did:key:issuer",
            receiver_did="did:key:receiver",
            joules_used=150.5,
            status="success",
            ser_summary={"steps": 3, "reputation": 0.8},
        )

        # Check stats updated
        stats = await sqlite_backend.get_stats()
        assert stats["total_executions"] == 1
        assert stats["total_joules_consumed"] == 150.5

        # Get history
        history = await sqlite_backend.get_execution_history(
            "did:key:receiver", as_issuer=False
        )
        assert len(history) == 1
        assert history[0].status == "success"
        assert history[0].joules_used == 150.5

    @pytest.mark.asyncio
    async def test_execution_history_filtering(
        self, sqlite_backend: SQLiteBackend
    ) -> None:
        """Execution history filters by issuer/receiver correctly."""
        await sqlite_backend.record_execution(
            execution_id="exec-001",
            contract_id="urn:test:1",
            issuer_did="did:key:alice",
            receiver_did="did:key:bob",
            joules_used=100,
            status="success",
        )

        await sqlite_backend.record_execution(
            execution_id="exec-002",
            contract_id="urn:test:2",
            issuer_did="did:key:bob",
            receiver_did="did:key:alice",
            joules_used=200,
            status="success",
        )

        # As issuer (Alice)
        alice_as_issuer = await sqlite_backend.get_execution_history(
            "did:key:alice", as_issuer=True
        )
        assert len(alice_as_issuer) == 1
        assert alice_as_issuer[0].joules_used == 100

        # As receiver (Alice)
        alice_as_receiver = await sqlite_backend.get_execution_history(
            "did:key:alice", as_issuer=False
        )
        assert len(alice_as_receiver) == 1
        assert alice_as_receiver[0].joules_used == 200

    @pytest.mark.asyncio
    async def test_calculate_reputation(
        self, sqlite_backend: SQLiteBackend
    ) -> None:
        """Reputation calculation from history works correctly."""
        # No history = default reputation
        rep = await sqlite_backend.calculate_reputation_from_history("did:key:newbie")
        assert rep == 0.5

        # Record some executions
        for i in range(10):
            await sqlite_backend.record_execution(
                execution_id=f"exec-{i}",
                contract_id=f"urn:test:{i}",
                issuer_did="did:key:client",
                receiver_did="did:key:worker",
                joules_used=50.0,
                status="success" if i < 8 else "failed",
            )

        rep = await sqlite_backend.calculate_reputation_from_history("did:key:worker")
        # 80% success rate, efficiency factor close to 1 for low joules
        assert rep > 0.7
        assert rep <= 1.0

    @pytest.mark.asyncio
    async def test_deactivate_agent(
        self, sqlite_backend: SQLiteBackend, sample_agent_data: dict
    ) -> None:
        """Can deactivate (soft delete) an agent."""
        await sqlite_backend.register_agent(**sample_agent_data)

        assert await sqlite_backend.get_agent(sample_agent_data["did_key"]) is not None

        await sqlite_backend.deactivate_agent(sample_agent_data["did_key"])

        # Should not appear in list
        agents = await sqlite_backend.list_agents()
        assert len(agents) == 0

        # Direct get returns None for inactive
        assert await sqlite_backend.get_agent(sample_agent_data["did_key"]) is None

    @pytest.mark.asyncio
    async def test_update_existing_agent(
        self, sqlite_backend: SQLiteBackend, sample_agent_data: dict
    ) -> None:
        """Registering same DID updates existing record."""
        await sqlite_backend.register_agent(
            did_key="did:key:same",
            pubkey_pem="pk1",
            endpoint_url="http://localhost:8000",
            capabilities=["net:read"],
            name="Original",
        )

        await sqlite_backend.register_agent(
            did_key="did:key:same",
            pubkey_pem="pk2",
            endpoint_url="http://localhost:9000",
            capabilities=["compute:write"],
            name="Updated",
        )

        agent = await sqlite_backend.get_agent("did:key:same")
        assert agent is not None
        assert agent.name == "Updated"
        assert agent.endpoint_url == "http://localhost:9000"
        assert agent.capabilities == ["compute:write"]

    @pytest.mark.asyncio
    async def test_search_agents(
        self, sqlite_backend: SQLiteBackend, sample_agent_data: dict
    ) -> None:
        """Can search agents with complex queries."""
        # Register test agents
        agents_data = [
            {**sample_agent_data, "did_key": "did:key:1", "name": "Alpha Agent", "capabilities": ["net:read"]},
            {**sample_agent_data, "did_key": "did:key:2", "name": "Beta Agent", "capabilities": ["compute:write"]},
            {**sample_agent_data, "did_key": "did:key:3", "name": "Gamma Agent", "capabilities": ["net:read", "compute:write"]},
        ]
        for data in agents_data:
            await sqlite_backend.register_agent(**data)

        # Search by capability
        query = SearchQuery(capability="net:read")
        results = await sqlite_backend.search_agents(query)
        assert len(results) == 2

        # Search by name pattern
        query = SearchQuery(name_pattern="Alpha")
        results = await sqlite_backend.search_agents(query)
        assert len(results) == 1
        assert results[0].name == "Alpha Agent"

        # Combined search
        query = SearchQuery(capability="compute:write", name_pattern="Gamma")
        results = await sqlite_backend.search_agents(query)
        assert len(results) == 1
        assert results[0].name == "Gamma Agent"

    @pytest.mark.asyncio
    async def test_record_and_get_interactions(
        self, sqlite_backend: SQLiteBackend
    ) -> None:
        """Can record and retrieve interactions."""
        interaction = InteractionRecord(
            interaction_id="int-001",
            contract_id="urn:test:contract",
            issuer_did="did:key:issuer",
            receiver_did="did:key:receiver",
            rating=0.95,
            joules_used=100.0,
            status="success",
            timestamp=datetime.now(timezone.utc),
            metadata={"key": "value"},
        )

        await sqlite_backend.record_interaction(interaction)

        history = await sqlite_backend.get_history("did:key:receiver")
        assert len(history) == 1
        assert history[0].interaction_id == "int-001"
        assert history[0].rating == 0.95


# ============================================================================
# Backend Factory Tests
# ============================================================================


class TestBackendFactory:
    """Test suite for backend factory functions."""

    def test_create_sqlite_backend_default(self, tmp_path: Path) -> None:
        """Factory creates SQLite backend by default."""
        backend = create_backend()
        assert isinstance(backend, SQLiteBackend)

    def test_create_sqlite_backend_from_url(self, tmp_path: Path) -> None:
        """Factory creates SQLite backend from sqlite:// URL."""
        db_path = tmp_path / "test.db"
        backend = create_backend(f"sqlite:///{db_path}")
        assert isinstance(backend, SQLiteBackend)

    def test_create_sqlite_backend_from_path(self, tmp_path: Path) -> None:
        """Factory creates SQLite backend from db_path parameter."""
        db_path = tmp_path / "test.db"
        backend = create_backend(db_path=db_path)
        assert isinstance(backend, SQLiteBackend)

    def test_create_postgres_backend_without_asyncpg(self) -> None:
        """Creating PostgreSQL backend without asyncpg raises ImportError."""
        with patch("agenlang.backends.POSTGRES_AVAILABLE", False):
            with pytest.raises(ImportError, match="asyncpg"):
                create_backend("postgresql://user:pass@localhost/db")

    def test_create_backend_invalid_scheme(self) -> None:
        """Invalid database URL scheme raises ValueError."""
        with pytest.raises(ValueError, match="Unsupported database URL scheme"):
            create_backend("mysql://user:pass@localhost/db")

    def test_create_backend_from_env(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Factory uses DATABASE_URL environment variable."""
        db_path = tmp_path / "env.db"
        monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
        backend = create_backend()
        assert isinstance(backend, SQLiteBackend)


# ============================================================================
# Abstract Base Class Tests
# ============================================================================


class TestRegistryBackendABC:
    """Test suite for RegistryBackend abstract base class."""

    def test_cannot_instantiate_abc(self) -> None:
        """Cannot instantiate abstract base class directly."""
        with pytest.raises(TypeError):
            RegistryBackend()  # type: ignore

    def test_subclass_must_implement_methods(self) -> None:
        """Subclasses must implement all abstract methods."""
        class IncompleteBackend(RegistryBackend):
            pass

        with pytest.raises(TypeError):
            IncompleteBackend()  # type: ignore


# ============================================================================
# Data Class Tests
# ============================================================================


class TestDataClasses:
    """Test suite for registry data classes."""

    def test_agent_record_to_dict(self) -> None:
        """AgentRecord can be converted to dict."""
        agent = AgentRecord(
            did_key="did:key:test",
            pubkey_pem="pk",
            endpoint_url="http://localhost:8000",
            name="Test",
            description="A test",
            capabilities=["net:read"],
            reputation_score=0.8,
            joule_rate=1.5,
            version="1.0.0",
            created_at="2024-01-01T00:00:00Z",
            last_seen="2024-01-01T00:00:00Z",
            is_active=True,
        )

        d = agent.to_dict()
        assert d["did_key"] == "did:key:test"
        assert d["name"] == "Test"
        assert d["reputation_score"] == 0.8
        assert d["capabilities"] == ["net:read"]

    def test_execution_record_creation(self) -> None:
        """ExecutionRecord can be created."""
        record = ExecutionRecord(
            execution_id="exec-001",
            contract_id="urn:test:1",
            issuer_did="did:key:issuer",
            receiver_did="did:key:receiver",
            joules_used=100.0,
            status="success",
            created_at="2024-01-01T00:00:00Z",
        )

        assert record.execution_id == "exec-001"
        assert record.status == "success"

    def test_interaction_record_creation(self) -> None:
        """InteractionRecord can be created."""
        now = datetime.now(timezone.utc)
        record = InteractionRecord(
            interaction_id="int-001",
            contract_id="urn:test:1",
            issuer_did="did:key:issuer",
            receiver_did="did:key:receiver",
            rating=0.9,
            joules_used=50.0,
            status="success",
            timestamp=now,
            metadata={"key": "value"},
        )

        assert record.interaction_id == "int-001"
        assert record.rating == 0.9

    def test_search_query_defaults(self) -> None:
        """SearchQuery has sensible defaults."""
        query = SearchQuery()
        assert query.capability is None
        assert query.min_reputation == 0.0
        assert query.name_pattern is None
        assert query.limit == 100
        assert query.offset == 0

    def test_search_query_custom(self) -> None:
        """SearchQuery accepts custom values."""
        query = SearchQuery(
            capability="net:read",
            min_reputation=0.8,
            name_pattern="Test",
            limit=50,
            offset=10,
        )
        assert query.capability == "net:read"
        assert query.min_reputation == 0.8
        assert query.name_pattern == "Test"
        assert query.limit == 50
        assert query.offset == 10


# ============================================================================
# Integration Tests (if PostgreSQL available)
# ============================================================================


@pytest.mark.skipif(
    os.environ.get("SKIP_POSTGRES_TESTS") == "1",
    reason="PostgreSQL tests disabled via SKIP_POSTGRES_TESTS"
)
@pytest.mark.asyncio
async def test_postgres_backend_if_available() -> None:
    """Test PostgreSQL backend if DATABASE_URL points to PostgreSQL.

    This test only runs if:
    1. asyncpg is installed
    2. DATABASE_URL is set to a PostgreSQL URL
    3. SKIP_POSTGRES_TESTS is not set
    """
    try:
        from agenlang.backends.postgres import PostgresBackend
    except ImportError:
        pytest.skip("asyncpg not installed")

    database_url = os.environ.get("DATABASE_URL", "")
    if not database_url.startswith("postgresql://"):
        pytest.skip("DATABASE_URL not set to PostgreSQL")

    backend = PostgresBackend(dsn=database_url)
    await backend.init_schema()

    try:
        # Basic CRUD test
        agent = await backend.register_agent(
            did_key="did:key:pgtest",
            pubkey_pem="-----BEGIN PUBLIC KEY-----\ntest\n-----END PUBLIC KEY-----",
            endpoint_url="http://localhost:8000",
            capabilities=["net:read"],
            name="PostgreSQL Test Agent",
        )

        assert agent.did_key == "did:key:pgtest"
        assert agent.name == "PostgreSQL Test Agent"

        # Retrieve
        retrieved = await backend.get_agent("did:key:pgtest")
        assert retrieved is not None
        assert retrieved.name == "PostgreSQL Test Agent"

        # Capability search with JSONB
        agents = await backend.find_agents_by_capability("net:read")
        assert len(agents) >= 1
        assert any(a.did_key == "did:key:pgtest" for a in agents)

    finally:
        # Cleanup
        await backend.deactivate_agent("did:key:pgtest")
        await backend.close()
