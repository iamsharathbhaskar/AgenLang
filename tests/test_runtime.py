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
    assert ser["resource_usage"]["joules_used"] == 150 + 80
    assert ser["resource_usage"]["efficiency_score"] >= 0.0
    assert ser["reputation_score"] >= 0.0
    assert ser["settlement_receipt"]["joule_recipient"]


def test_runtime_joule_budget_exhausted(tmp_path: Path) -> None:
    """Joule budget exhaustion raises."""
    km = KeyManager(key_path=tmp_path / "keys.pem")
    km.generate()
    contract = Contract.from_file(str(EXAMPLES_DIR / "amazo-flight-booking.json"))
    contract.constraints.joule_budget = 10
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


def test_runtime_probabilistic_workflow(tmp_path: Path) -> None:
    """Probabilistic workflow: weighted selection, per-step decision points."""
    from unittest.mock import patch

    km = KeyManager(key_path=tmp_path / "keys.pem")
    km.generate()
    contract = Contract.from_file(str(EXAMPLES_DIR / "probabilistic.json"))
    assert contract.workflow.type == "probabilistic"
    assert len(contract.workflow.steps) == 2

    with patch(
        "agenlang.runtime.random.choices", return_value=[contract.workflow.steps[0]]
    ):
        runtime = Runtime(contract, key_manager=km)
        result, ser = runtime.execute()

    assert result["status"] == "success"
    assert result["steps_completed"] == 1
    assert ser["resource_usage"]["joules_used"] == 150.0
    assert len(ser["decision_points"]) == 2
    chosen = [dp for dp in ser["decision_points"] if dp["chosen"]]
    assert len(chosen) == 1
    assert chosen[0]["location"] == "step_0"


def test_runtime_probabilistic_empty_steps(tmp_path: Path) -> None:
    """Probabilistic workflow with no steps raises."""
    km = KeyManager(key_path=tmp_path / "keys.pem")
    km.generate()
    contract = Contract.from_file(str(EXAMPLES_DIR / "probabilistic.json"))
    contract.workflow.steps = []
    runtime = Runtime(contract, key_manager=km)
    with pytest.raises(
        ValueError, match="Probabilistic workflow requires at least one step"
    ):
        runtime.execute()


def test_runtime_unknown_workflow_type(tmp_path: Path) -> None:
    """Unknown workflow type raises."""
    km = KeyManager(key_path=tmp_path / "keys.pem")
    km.generate()
    contract = Contract.from_file(str(EXAMPLES_DIR / "amazo-flight-booking.json"))
    object.__setattr__(
        contract.workflow, "type", "unknown"
    )  # bypass Pydantic validation
    runtime = Runtime(contract, key_manager=km)
    with pytest.raises(ValueError, match="Unknown workflow type"):
        runtime.execute()


def test_runtime_parallel_workflow(tmp_path: Path) -> None:
    """Parallel workflow runs all steps with branch decision points."""
    km = KeyManager(key_path=tmp_path / "keys.pem")
    km.generate()
    contract = Contract.from_file(str(EXAMPLES_DIR / "amazo-flight-booking.json"))
    object.__setattr__(contract.workflow, "type", "parallel")
    runtime = Runtime(contract, key_manager=km)
    result, ser = runtime.execute()
    assert result["status"] == "success"
    assert result["steps_completed"] == 2
    branches = [dp for dp in ser["decision_points"] if dp["type"] == "parallel_branch"]
    assert len(branches) == 2


def test_runtime_weighted_probabilistic(tmp_path: Path) -> None:
    """Weighted probabilistic uses step weights."""
    from unittest.mock import patch

    km = KeyManager(key_path=tmp_path / "keys.pem")
    km.generate()
    contract = Contract.from_file(str(EXAMPLES_DIR / "probabilistic.json"))
    assert contract.workflow.steps[0].weight == 0.7
    assert contract.workflow.steps[1].weight == 0.3

    with patch("agenlang.runtime.random.choices") as mock_choices:
        mock_choices.return_value = [contract.workflow.steps[1]]
        runtime = Runtime(contract, key_manager=km)
        result, ser = runtime.execute()

    mock_choices.assert_called_once()
    call_kwargs = mock_choices.call_args
    assert call_kwargs.kwargs["weights"] == [0.7, 0.3]
    assert result["steps_completed"] == 1


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
    """Protocol auto-detect routes to adapter dispatch."""
    from unittest.mock import MagicMock, patch

    km = KeyManager(key_path=tmp_path / "keys.pem")
    km.generate()
    contract = Contract.from_file(str(EXAMPLES_DIR / "amazo-flight-booking.json"))
    contract.workflow.steps = [contract.workflow.steps[0]]
    contract.workflow.steps[0].target = "fipa:test-agent"

    mock_mod = MagicMock()
    mock_mod.dispatch.return_value = '{"status": "ok"}'
    with patch("importlib.import_module", return_value=mock_mod):
        runtime = Runtime(contract, key_manager=km)
        result, ser = runtime.execute()

    assert result["status"] == "success"
    mock_mod.dispatch.assert_called_once()
