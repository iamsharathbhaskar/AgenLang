"""Tests for runtime execution."""

from pathlib import Path

import pytest

from agenlang.contract import Contract
from agenlang.keys import KeyManager
from agenlang.runtime import Runtime

EXAMPLES_DIR = Path(__file__).parent.parent / "examples"


def test_runtime_execute_e2e(tmp_path: Path) -> None:
    """End-to-end: load contract, execute, get SER."""
    km = KeyManager(key_path=tmp_path / "keys.pem")
    km.generate()  # Creates ser.key in same dir
    contract = Contract.from_file(str(EXAMPLES_DIR / "amazo-flight-booking.json"))
    runtime = Runtime(contract, key_manager=km)
    result, ser = runtime.execute()
    assert result["status"] == "success"
    assert result["steps_completed"] == 2
    assert ser["execution_id"] == contract.contract_id
    assert ser["resource_usage"]["joules_used"] > 0
    assert ser["resource_usage"]["joules_used"] == 150 + 80  # web_search + summarize


def test_runtime_joule_budget_exhausted(tmp_path: Path) -> None:
    """Joule budget exhaustion raises."""
    km = KeyManager(key_path=tmp_path / "keys.pem")
    km.generate()
    contract = Contract.from_file(str(EXAMPLES_DIR / "amazo-flight-booking.json"))
    contract.constraints.joule_budget = 10  # Too low for 2 tools
    runtime = Runtime(contract, key_manager=km)
    with pytest.raises(ValueError, match="Joule budget exhausted"):
        runtime.execute()
