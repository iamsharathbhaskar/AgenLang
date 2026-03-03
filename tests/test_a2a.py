# Copyright 2024 AgenLang Contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for A2A transport wrapper."""

from agenlang.a2a import (
    a2a_payload_to_contract,
    contract_to_a2a_payload,
    contract_to_sse_event,
    parse_sse_event,
)
from agenlang.contract import Contract

EXAMPLE_PATH = "examples/amazo-flight-booking.json"


def test_contract_to_a2a_roundtrip() -> None:
    """Wrap and unwrap contract through A2A payload."""
    contract = Contract.from_file(EXAMPLE_PATH)
    payload = contract_to_a2a_payload(contract)
    assert payload["jsonrpc"] == "2.0"
    assert payload["method"] == "agenlang/execute"
    assert payload["id"] == contract.contract_id
    assert payload["params"]["@type"] == "AgenLangContract"
    restored = a2a_payload_to_contract(payload)
    assert restored.contract_id == contract.contract_id
    assert restored.goal == contract.goal


def test_sse_roundtrip() -> None:
    """Contract through SSE event format and back."""
    contract = Contract.from_file(EXAMPLE_PATH)
    sse = contract_to_sse_event(contract)
    assert sse.startswith("event: agenlang\ndata: ")
    assert sse.endswith("\n\n")
    restored = parse_sse_event(sse)
    assert restored.contract_id == contract.contract_id


def test_parse_sse_no_data_raises() -> None:
    """parse_sse_event raises on missing data line."""
    import pytest

    with pytest.raises(ValueError, match="No data line"):
        parse_sse_event("event: agenlang\nno-data-here\n\n")
