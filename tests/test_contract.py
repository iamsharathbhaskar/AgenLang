"""Tests for contract validation and hypothesis fuzzing."""

import tempfile
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from agenlang.contract import Contract


def test_contract_from_file() -> None:
    """Contract loads from valid JSON file."""
    c = Contract.from_file("examples/amazo-flight-booking.json")
    assert c.contract_id.startswith("urn:agenlang:exec:")
    assert c.goal
    assert c.constraints.joule_budget > 0


def test_contract_invalid_schema_raises() -> None:
    """Invalid schema raises ValueError."""
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        f.write(b'{"invalid": "contract"}')
        path = f.name
    try:
        with pytest.raises(ValueError, match="Invalid AgenLang contract"):
            Contract.from_file(path)
    finally:
        Path(path).unlink()


@given(
    goal=st.text(min_size=1, max_size=200),
    joule_budget=st.floats(min_value=1, max_value=100000),
)
def test_contract_fuzz_valid(goal: str, joule_budget: float) -> None:
    """Hypothesis: valid contract shapes load."""
    import secrets

    contract_id = f"urn:agenlang:exec:{secrets.token_hex(16)}"
    data = {
        "agenlang_version": "1.0",
        "contract_id": contract_id,
        "issuer": {"agent_id": "test", "pubkey": "pk"},
        "goal": goal,
        "intent_anchor": {"hash": "sha256:test"},
        "constraints": {"joule_budget": joule_budget},
        "workflow": {
            "type": "sequence",
            "steps": [{"action": "tool", "target": "web_search", "args": {"query": "test"}}],
        },
        "memory_contract": {"handoff_keys": [], "ttl": "1h"},
        "settlement": {"joule_recipient": "r", "rate": 1.0},
        "capability_attestations": [{"capability": "net:read", "proof": "p"}],
    }
    c = Contract.model_validate(data)
    assert c.goal == goal
    assert c.constraints.joule_budget == joule_budget
