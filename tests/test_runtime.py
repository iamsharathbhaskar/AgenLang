# Copyright 2024 AgenLang Contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for runtime execution — end-to-end, error paths, dispatcher."""

from pathlib import Path

import pytest

from agenlang.contract import Contract
from agenlang.keys import KeyManager
from agenlang.runtime import Runtime

EXAMPLES_DIR = Path(__file__).parent.parent / "examples"


def test_runtime_execute_e2e(tmp_path: Path) -> None:
    """End-to-end: load contract, execute, get SER."""
    km = KeyManager(key_path=tmp_path / "keys.pem")
    km.generate()
    contract = Contract.from_file(str(EXAMPLES_DIR / "amazo-flight-booking.json"))
    runtime = Runtime(contract, key_manager=km)
    result, ser = runtime.execute()
    assert result["status"] == "success"
    assert result["steps_completed"] == 2
    assert ser["execution_id"] == contract.contract_id
    assert ser["resource_usage"]["joules_used"] > 0
    assert sum(
        e["amount_joules"] for e in ser["ledger_entries"]
    ) == ser["resource_usage"]["joules_used"]
    assert ser["resource_usage"]["efficiency_score"] >= 0.0
    assert ser["reputation_score"] >= 0.0
    assert ser["settlement_receipt"]["joule_recipient"]


def test_runtime_joule_budget_exhausted(tmp_path: Path) -> None:
    """Joule budget exhaustion raises."""
    km = KeyManager(key_path=tmp_path / "keys.pem")
    km.generate()
    contract = Contract.from_file(str(EXAMPLES_DIR / "amazo-flight-booking.json"))
    contract.constraints.joule_budget = 1e-6
    runtime = Runtime(contract, key_manager=km)
    with pytest.raises(ValueError, match="Joule budget exhausted"):
        runtime.execute()


def test_runtime_zero_budget(tmp_path: Path) -> None:
    """Zero budget raises immediately."""
    km = KeyManager(key_path=tmp_path / "keys.pem")
    km.generate()
    contract = Contract.from_file(str(EXAMPLES_DIR / "amazo-flight-booking.json"))
    contract.constraints.joule_budget = 0
    runtime = Runtime(contract, key_manager=km)
    with pytest.raises(ValueError, match="Joule budget exhausted or invalid"):
        runtime.execute()


def test_runtime_unknown_tool(tmp_path: Path) -> None:
    """Unknown tool raises ValueError."""
    km = KeyManager(key_path=tmp_path / "keys.pem")
    km.generate()
    contract = Contract.from_file(str(EXAMPLES_DIR / "amazo-flight-booking.json"))
    contract.workflow.steps[0].target = "nonexistent_tool"
    runtime = Runtime(contract, key_manager=km)
    with pytest.raises(ValueError, match="Unknown tool"):
        runtime.execute()


def test_runtime_capability_violation(tmp_path: Path) -> None:
    """Missing capability raises."""
    km = KeyManager(key_path=tmp_path / "keys.pem")
    km.generate()
    contract = Contract.from_file(str(EXAMPLES_DIR / "amazo-flight-booking.json"))
    contract.capability_attestations = []
    runtime = Runtime(contract, key_manager=km)
    with pytest.raises(ValueError, match="Capability violation"):
        runtime.execute()


def test_runtime_recursion_guard(tmp_path: Path) -> None:
    """Recursion limit raises."""
    km = KeyManager(key_path=tmp_path / "keys.pem")
    km.generate()
    contract = Contract.from_file(str(EXAMPLES_DIR / "amazo-flight-booking.json"))
    runtime = Runtime(contract, key_manager=km)
    runtime._recursion_depth = 10
    with pytest.raises(ValueError, match="Recursion limit"):
        runtime._execute_step(contract.workflow.steps[0])


def test_runtime_skill_not_implemented(tmp_path: Path) -> None:
    """Skill action raises NotImplementedError."""
    km = KeyManager(key_path=tmp_path / "keys.pem")
    km.generate()
    contract = Contract.from_file(str(EXAMPLES_DIR / "amazo-flight-booking.json"))
    contract.workflow.steps[0].action = "skill"
    runtime = Runtime(contract, key_manager=km)
    with pytest.raises(NotImplementedError, match="skill:"):
        runtime.execute()


def test_runtime_subcontract_not_implemented(tmp_path: Path) -> None:
    """Subcontract action raises NotImplementedError."""
    km = KeyManager(key_path=tmp_path / "keys.pem")
    km.generate()
    contract = Contract.from_file(str(EXAMPLES_DIR / "amazo-flight-booking.json"))
    contract.workflow.steps[0].action = "subcontract"
    runtime = Runtime(contract, key_manager=km)
    with pytest.raises(NotImplementedError, match="subcontract:"):
        runtime.execute()


def test_runtime_embed_not_implemented(tmp_path: Path) -> None:
    """Embed action raises NotImplementedError."""
    km = KeyManager(key_path=tmp_path / "keys.pem")
    km.generate()
    contract = Contract.from_file(str(EXAMPLES_DIR / "amazo-flight-booking.json"))
    contract.workflow.steps[0].action = "embed"
    runtime = Runtime(contract, key_manager=km)
    with pytest.raises(NotImplementedError, match="embed:"):
        runtime.execute()


def test_runtime_unknown_action(tmp_path: Path) -> None:
    """Unknown action logs but doesn't crash."""

    km = KeyManager(key_path=tmp_path / "keys.pem")
    km.generate()
    contract = Contract.from_file(str(EXAMPLES_DIR / "amazo-flight-booking.json"))
    step = {"action": "unknown_action", "target": "x", "args": {}}
    runtime = Runtime(contract, key_manager=km)
    runtime._execute_step(step)


def test_runtime_to_ser_json(tmp_path: Path) -> None:
    """to_ser_json produces valid JSON."""
    import json

    km = KeyManager(key_path=tmp_path / "keys.pem")
    km.generate()
    contract = Contract.from_file(str(EXAMPLES_DIR / "amazo-flight-booking.json"))
    runtime = Runtime(contract, key_manager=km)
    result, ser = runtime.execute()
    ser_json = runtime.to_ser_json(ser)
    parsed = json.loads(ser_json)
    assert parsed["execution_id"] == contract.contract_id


def test_runtime_error_handler_retry(tmp_path: Path) -> None:
    """Error handler retries steps."""
    from agenlang.models import ErrorHandler

    km = KeyManager(key_path=tmp_path / "keys.pem")
    km.generate()
    contract = Contract.from_file(str(EXAMPLES_DIR / "amazo-flight-booking.json"))
    contract.workflow.steps[0].on_error = ErrorHandler(retry=2)
    contract.workflow.steps[0].target = "nonexistent"
    runtime = Runtime(contract, key_manager=km)
    with pytest.raises(ValueError, match="Unknown tool"):
        runtime.execute()


def test_compute_reputation_zero_budget(tmp_path: Path) -> None:
    """Reputation score returns 0 for zero budget."""
    km = KeyManager(key_path=tmp_path / "keys.pem")
    km.generate()
    contract = Contract.from_file(str(EXAMPLES_DIR / "amazo-flight-booking.json"))
    runtime = Runtime(contract, key_manager=km)
    contract.constraints.joule_budget = 0
    assert runtime._compute_reputation_score(100) == 0.0


def test_compute_efficiency_zero_budget(tmp_path: Path) -> None:
    """Efficiency score returns 0 for zero budget."""
    km = KeyManager(key_path=tmp_path / "keys.pem")
    km.generate()
    contract = Contract.from_file(str(EXAMPLES_DIR / "amazo-flight-booking.json"))
    runtime = Runtime(contract, key_manager=km)
    contract.constraints.joule_budget = 0
    assert runtime._compute_efficiency(100) == 0.0


def test_runtime_no_key_manager(tmp_path: Path) -> None:
    """Runtime works without explicit KeyManager (uses default)."""
    contract = Contract.from_file(str(EXAMPLES_DIR / "amazo-flight-booking.json"))
    runtime = Runtime(contract)
    result, ser = runtime.execute()
    assert result["status"] == "success"


def test_runtime_conditional_skip(tmp_path: Path) -> None:
    """Sequence step with unresolved {{step_N_output}} is skipped."""
    km = KeyManager(key_path=tmp_path / "keys.pem")
    km.generate()
    contract = Contract.from_file(str(EXAMPLES_DIR / "amazo-flight-booking.json"))
    contract.workflow.steps[1].args = {"text": "{{step_5_output}}"}
    runtime = Runtime(contract, key_manager=km)
    result, ser = runtime.execute()
    assert result["steps_completed"] == 1
    skips = [dp for dp in ser["decision_points"] if dp["type"] == "conditional_skip"]
    assert len(skips) == 1


def test_runtime_protocol_dispatch(tmp_path: Path) -> None:
    """Protocol auto-detect routes to A2A adapter dispatch."""
    from unittest.mock import MagicMock, patch

    km = KeyManager(key_path=tmp_path / "keys.pem")
    km.generate()
    contract = Contract.from_file(str(EXAMPLES_DIR / "amazo-flight-booking.json"))
    contract.workflow.steps = [contract.workflow.steps[0]]
    contract.workflow.steps[0].target = "a2a:test-agent"

    mock_mod = MagicMock()
    mock_mod.dispatch.return_value = '{"status": "ok"}'
    with patch("importlib.import_module", return_value=mock_mod):
        runtime = Runtime(contract, key_manager=km)
        result, ser = runtime.execute()

    assert result["status"] == "success"
    mock_mod.dispatch.assert_called_once()
