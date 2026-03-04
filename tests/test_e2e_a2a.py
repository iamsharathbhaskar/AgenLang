# Copyright 2024 AgenLang Contributors
# SPDX-License-Identifier: Apache-2.0

"""End-to-end test: sign contract -> A2A payload -> execute -> verify SER + ledger."""

from pathlib import Path

from agenlang.a2a import a2a_payload_to_contract, contract_to_a2a_payload
from agenlang.contract import Contract
from agenlang.keys import KeyManager
from agenlang.runtime import Runtime

EXAMPLES_DIR = Path(__file__).parent.parent / "examples"


def test_e2e_sign_a2a_execute_verify(tmp_path: Path) -> None:
    """Full pipeline: sign -> A2A roundtrip -> execute -> verify SER + ledger balance."""
    km = KeyManager(key_path=tmp_path / "keys.pem")
    km.generate()

    contract = Contract.from_file(str(EXAMPLES_DIR / "amazo-flight-booking.json"))
    contract.sign(km)
    assert contract.verify_signature() is True
    assert contract.issuer.agent_id.startswith("did:key:z")

    payload = contract_to_a2a_payload(contract)
    assert payload["jsonrpc"] == "2.0"
    assert payload["method"] == "agenlang/execute"

    restored = a2a_payload_to_contract(payload)
    assert restored.contract_id == contract.contract_id
    assert restored.verify_signature() is True

    runtime = Runtime(restored, key_manager=km)
    result, ser = runtime.execute()

    assert result["status"] == "success"
    assert result["steps_completed"] == 2
    assert ser["execution_id"] == contract.contract_id

    joules_used = ser["resource_usage"]["joules_used"]
    assert joules_used > 0

    ledger_sum = sum(e["amount_joules"] for e in ser["ledger_entries"])
    assert ledger_sum == joules_used

    assert ser["settlement_receipt"]["joule_recipient"] == "zhc-travel-agent"
    assert ser["reputation_score"] >= 0.0
    assert ser["resource_usage"]["efficiency_score"] >= 0.0
    assert "timestamps" in ser
    assert "replay_ref" in ser

    assert "receiver_receipt" in ser
    assert ser["receiver_receipt"]["agent_id"] == "zhc-travel-agent"
    assert ser["receiver_receipt"]["signature"]
