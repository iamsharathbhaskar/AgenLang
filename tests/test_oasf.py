"""Tests for OASF (Open Agent Schema Framework) adapter."""

from pathlib import Path

from agenlang.contract import Contract
from agenlang.oasf import (
    contract_to_oasf_task,
    generate_oasf_manifest,
    oasf_manifest_to_agent_card,
)

EXAMPLES_DIR = Path(__file__).parent.parent / "examples"


def test_generate_oasf_manifest_bundled() -> None:
    """OASF manifest from bundled schema has required fields."""
    manifest = generate_oasf_manifest()
    assert manifest["schema"] == "oasf/1.0"
    assert manifest["name"] == "agenlang"
    assert "capabilities" in manifest
    assert len(manifest["capabilities"]) > 0
    assert any(c["name"] == "tool" for c in manifest["capabilities"])
    assert "inputs" in manifest
    assert "outputs" in manifest


def test_generate_oasf_manifest_from_file() -> None:
    """OASF manifest from explicit schema path."""
    schema_path = str(
        Path(__file__).parent.parent / "src" / "agenlang" / "schema" / "v1.0.json"
    )
    manifest = generate_oasf_manifest(schema_path)
    assert manifest["name"] == "agenlang"
    assert manifest["title"] == "AgenLang Contract v1.0"


def test_contract_to_oasf_task() -> None:
    """Contract maps to OASF task descriptor."""
    contract = Contract.from_file(str(EXAMPLES_DIR / "amazo-flight-booking.json"))
    task = contract_to_oasf_task(contract)
    assert task["schema"] == "oasf/task/1.0"
    assert task["id"] == contract.contract_id
    assert task["description"] == contract.goal
    assert task["agent"] == contract.issuer.agent_id
    assert task["workflow"]["type"] == "sequence"
    assert task["workflow"]["step_count"] == 2


def test_oasf_manifest_to_agent_card() -> None:
    """Agent card has A2A-compatible structure."""
    card = oasf_manifest_to_agent_card()
    assert card["name"] == "agenlang"
    assert "skills" in card
    assert len(card["skills"]) > 0
    assert card["capabilities"]["streaming"] is True
    assert "application/json" in card["defaultInputModes"]


def test_oasf_manifest_to_agent_card_custom() -> None:
    """Agent card from custom manifest."""
    manifest = {
        "name": "custom",
        "description": "Custom agent",
        "capabilities": [{"name": "search", "description": "Search"}],
    }
    card = oasf_manifest_to_agent_card(manifest)
    assert card["name"] == "custom"
    assert len(card["skills"]) == 1
    assert card["skills"][0]["id"] == "search"
