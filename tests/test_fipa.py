"""Tests for FIPA ACL adapter."""

import json
from pathlib import Path

from agenlang.contract import Contract
from agenlang.fipa import (
    PERFORMATIVE_MAP,
    contract_to_fipa_acl,
    dispatch,
    fipa_acl_to_contract,
    step_to_performative,
)

EXAMPLES_DIR = Path(__file__).parent.parent / "examples"


def _load_contract() -> Contract:
    return Contract.from_file(str(EXAMPLES_DIR / "amazo-flight-booking.json"))


def test_step_to_performative() -> None:
    """Each action maps to a FIPA performative."""
    contract = _load_contract()
    perf = step_to_performative(contract.workflow.steps[0])
    assert perf == "request"


def test_performative_map_coverage() -> None:
    """All action types are mapped."""
    assert "tool" in PERFORMATIVE_MAP
    assert "skill" in PERFORMATIVE_MAP
    assert "subcontract" in PERFORMATIVE_MAP
    assert "embed" in PERFORMATIVE_MAP


def test_contract_to_fipa_acl() -> None:
    """FIPA ACL has required fields."""
    contract = _load_contract()
    acl = contract_to_fipa_acl(contract)
    assert acl["performative"] == "request"
    assert acl["sender"]["name"] == contract.issuer.agent_id
    assert acl["language"] == "agenlang-json"
    assert acl["ontology"] == "agenlang:contract:v1.0"
    assert acl["conversation-id"] == contract.contract_id


def test_fipa_roundtrip() -> None:
    """Contract survives FIPA ACL roundtrip."""
    contract = _load_contract()
    acl = contract_to_fipa_acl(contract)
    restored = fipa_acl_to_contract(acl)
    assert restored.contract_id == contract.contract_id
    assert restored.goal == contract.goal


def test_dispatch_returns_acl_json() -> None:
    """dispatch returns FIPA ACL JSON with updated receiver."""
    contract = _load_contract()
    result = dispatch(contract, "tool", "agent-x", {})
    parsed = json.loads(result)
    assert parsed["receiver"]["name"] == "agent-x"
    assert parsed["performative"] == "request"
