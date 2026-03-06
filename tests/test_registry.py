# Copyright 2024 AgenLang Contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for agent registry and reputation tracking."""

from pathlib import Path

import pytest

from agenlang.registry import AgentRegistry, AgentRecord


def test_registry_initialization(tmp_path: Path) -> None:
    """Registry initializes database correctly."""
    db_path = tmp_path / "test_registry.db"
    registry = AgentRegistry(db_path=db_path)

    assert db_path.exists()
    stats = registry.get_stats()
    assert stats["active_agents"] == 0
    assert stats["total_executions"] == 0


def test_register_and_get_agent(tmp_path: Path) -> None:
    """Can register and retrieve an agent."""
    registry = AgentRegistry(db_path=tmp_path / "registry.db")

    agent = registry.register_agent(
        did_key="did:key:z123",
        pubkey_pem="-----BEGIN PUBLIC KEY-----\ntest\n-----END PUBLIC KEY-----",
        endpoint_url="http://localhost:8000",
        capabilities=["net:read", "compute:write"],
        name="Test Agent",
        description="A test agent",
        joule_rate=2.5,
    )

    assert agent.did_key == "did:key:z123"
    assert agent.name == "Test Agent"
    assert agent.capabilities == ["net:read", "compute:write"]
    assert agent.reputation_score == 0.5  # Default

    # Retrieve
    retrieved = registry.get_agent("did:key:z123")
    assert retrieved is not None
    assert retrieved.name == "Test Agent"
    assert retrieved.endpoint_url == "http://localhost:8000"


def test_get_nonexistent_agent(tmp_path: Path) -> None:
    """Getting nonexistent agent returns None."""
    registry = AgentRegistry(db_path=tmp_path / "registry.db")
    assert registry.get_agent("did:key:nonexistent") is None


def test_list_agents(tmp_path: Path) -> None:
    """Can list registered agents."""
    registry = AgentRegistry(db_path=tmp_path / "registry.db")

    for i in range(3):
        registry.register_agent(
            did_key=f"did:key:z{i}",
            pubkey_pem=f"pk{i}",
            endpoint_url=f"http://localhost:{8000 + i}",
            capabilities=["net:read"],
            name=f"Agent {i}",
        )

    agents = registry.list_agents()
    assert len(agents) == 3


def test_find_by_capability(tmp_path: Path) -> None:
    """Can find agents by capability."""
    registry = AgentRegistry(db_path=tmp_path / "registry.db")

    registry.register_agent(
        did_key="did:key:net",
        pubkey_pem="pk1",
        endpoint_url="http://localhost:8001",
        capabilities=["net:read", "net:write"],
        name="Net Agent",
    )

    registry.register_agent(
        did_key="did:key:compute",
        pubkey_pem="pk2",
        endpoint_url="http://localhost:8002",
        capabilities=["compute:read"],
        name="Compute Agent",
    )

    net_agents = registry.find_agents_by_capability("net:read")
    assert len(net_agents) == 1
    assert net_agents[0].name == "Net Agent"

    # With min reputation filter
    registry.update_reputation("did:key:net", 0.8)
    high_rep = registry.find_agents_by_capability("net:read", min_reputation=0.9)
    assert len(high_rep) == 0


def test_update_reputation(tmp_path: Path) -> None:
    """Can update agent reputation."""
    registry = AgentRegistry(db_path=tmp_path / "registry.db")

    registry.register_agent(
        did_key="did:key:test",
        pubkey_pem="pk",
        endpoint_url="http://localhost:8000",
        capabilities=["net:read"],
    )

    registry.update_reputation("did:key:test", 0.95)
    agent = registry.get_agent("did:key:test")
    assert agent.reputation_score == 0.95

    # Test clamping
    registry.update_reputation("did:key:test", 1.5)
    agent = registry.get_agent("did:key:test")
    assert agent.reputation_score == 1.0

    registry.update_reputation("did:key:test", -0.5)
    agent = registry.get_agent("did:key:test")
    assert agent.reputation_score == 0.0


def test_record_execution(tmp_path: Path) -> None:
    """Can record contract execution."""
    registry = AgentRegistry(db_path=tmp_path / "registry.db")

    registry.record_execution(
        execution_id="exec-001",
        contract_id="urn:agenlang:exec:abc123",
        issuer_did="did:key:issuer",
        receiver_did="did:key:receiver",
        joules_used=150.5,
        status="success",
        ser_summary={"steps": 3, "reputation": 0.8},
    )

    # Check stats updated
    stats = registry.get_stats()
    assert stats["total_executions"] == 1
    assert stats["total_joules_consumed"] == 150.5

    # Get history
    history = registry.get_execution_history("did:key:receiver", as_issuer=False)
    assert len(history) == 1
    assert history[0].status == "success"
    assert history[0].joules_used == 150.5


def test_execution_history_filtering(tmp_path: Path) -> None:
    """Execution history filters by issuer/receiver correctly."""
    registry = AgentRegistry(db_path=tmp_path / "registry.db")

    registry.record_execution(
        execution_id="exec-001",
        contract_id="urn:test:1",
        issuer_did="did:key:alice",
        receiver_did="did:key:bob",
        joules_used=100,
        status="success",
    )

    registry.record_execution(
        execution_id="exec-002",
        contract_id="urn:test:2",
        issuer_did="did:key:bob",
        receiver_did="did:key:alice",
        joules_used=200,
        status="success",
    )

    # As issuer (Alice)
    alice_as_issuer = registry.get_execution_history("did:key:alice", as_issuer=True)
    assert len(alice_as_issuer) == 1
    assert alice_as_issuer[0].joules_used == 100

    # As receiver (Alice)
    alice_as_receiver = registry.get_execution_history("did:key:alice", as_issuer=False)
    assert len(alice_as_receiver) == 1
    assert alice_as_receiver[0].joules_used == 200


def test_calculate_reputation(tmp_path: Path) -> None:
    """Reputation calculation from history works correctly."""
    registry = AgentRegistry(db_path=tmp_path / "registry.db")

    # No history = default reputation
    rep = registry.calculate_reputation_from_history("did:key:newbie")
    assert rep == 0.5

    # Record some executions
    for i in range(10):
        registry.record_execution(
            execution_id=f"exec-{i}",
            contract_id=f"urn:test:{i}",
            issuer_did="did:key:client",
            receiver_did="did:key:worker",
            joules_used=50.0,
            status="success" if i < 8 else "failed",
        )

    rep = registry.calculate_reputation_from_history("did:key:worker")
    # 80% success rate, efficiency factor close to 1 for low joules
    assert rep > 0.7  # Should be high
    assert rep <= 1.0


def test_deactivate_agent(tmp_path: Path) -> None:
    """Can deactivate (soft delete) an agent."""
    registry = AgentRegistry(db_path=tmp_path / "registry.db")

    registry.register_agent(
        did_key="did:key:todelete",
        pubkey_pem="pk",
        endpoint_url="http://localhost:8000",
        capabilities=["net:read"],
    )

    assert registry.get_agent("did:key:todelete") is not None

    registry.deactivate_agent("did:key:todelete")

    # Should not appear in list
    agents = registry.list_agents()
    assert len(agents) == 0

    # Direct get returns None for inactive
    assert registry.get_agent("did:key:todelete") is None


def test_update_existing_agent(tmp_path: Path) -> None:
    """Registering same DID updates existing record."""
    registry = AgentRegistry(db_path=tmp_path / "registry.db")

    registry.register_agent(
        did_key="did:key:same",
        pubkey_pem="pk1",
        endpoint_url="http://localhost:8000",
        capabilities=["net:read"],
        name="Original",
    )

    registry.register_agent(
        did_key="did:key:same",
        pubkey_pem="pk2",
        endpoint_url="http://localhost:9000",
        capabilities=["compute:write"],
        name="Updated",
    )

    agent = registry.get_agent("did:key:same")
    assert agent.name == "Updated"
    assert agent.endpoint_url == "http://localhost:9000"
    assert agent.capabilities == ["compute:write"]


def test_agent_record_to_dict(tmp_path: Path) -> None:
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
