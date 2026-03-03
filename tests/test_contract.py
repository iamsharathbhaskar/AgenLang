# Copyright 2024 AgenLang Contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for contract validation, serialization, and hypothesis fuzzing."""

import json
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


def test_contract_to_json() -> None:
    """to_json produces valid JSON roundtrip."""
    c = Contract.from_file("examples/amazo-flight-booking.json")
    j = c.to_json()
    data = json.loads(j)
    assert data["contract_id"] == c.contract_id
    assert data["goal"] == c.goal


def test_contract_from_dict() -> None:
    """from_dict validates and loads."""
    data = json.loads(Path("examples/amazo-flight-booking.json").read_text())
    c = Contract.from_dict(data)
    assert c.contract_id == data["contract_id"]


def test_contract_verify_no_proof() -> None:
    """verify_signature returns False when no proof."""
    c = Contract.from_file("examples/amazo-flight-booking.json")
    assert c.verify_signature() is False


def test_contract_verify_bad_proof() -> None:
    """verify_signature returns False for invalid base64 proof."""
    c = Contract.from_file("examples/amazo-flight-booking.json")
    c.issuer.proof = "not-valid-base64!!!"
    assert c.verify_signature() is False


def test_all_example_contracts_load() -> None:
    """All example contracts in examples/ load successfully."""
    examples_dir = Path("examples")
    for f in examples_dir.glob("*.json"):
        c = Contract.from_file(str(f))
        assert c.contract_id


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
            "steps": [
                {"action": "tool", "target": "web_search", "args": {"query": "test"}}
            ],
        },
        "memory_contract": {"handoff_keys": [], "ttl": "1h"},
        "settlement": {"joule_recipient": "r", "rate": 1.0},
        "capability_attestations": [{"capability": "net:read", "proof": "p"}],
    }
    c = Contract.model_validate(data)
    assert c.goal == goal
    assert c.constraints.joule_budget == joule_budget
