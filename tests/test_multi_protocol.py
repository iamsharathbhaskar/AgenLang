# Copyright 2024 AgenLang Contributors
# SPDX-License-Identifier: Apache-2.0

"""Multi-protocol E2E tests: ACP->AG-UI, ANP->MCP, full chain."""

import json
from pathlib import Path
from typing import Any, Dict
from unittest.mock import patch

from agenlang.acp import acp_message_to_contract, contract_to_acp_message
from agenlang.agui import (
    EVENT_RUN_FINISHED,
    EVENT_RUN_STARTED,
    ser_to_agui_events,
    stream_ser_events,
)
from agenlang.anp import create_anp_envelope, verify_anp_envelope
from agenlang.contract import Contract
from agenlang.keys import KeyManager
from agenlang.mcp import handle_mcp_call
from agenlang.runtime import Runtime

EXAMPLES_DIR = Path(__file__).parent.parent / "examples"


def _load_contract() -> Contract:
    return Contract.from_file(str(EXAMPLES_DIR / "amazo-flight-booking.json"))


def _make_ser(execution_id: str = "test-exec-001") -> Dict[str, Any]:
    return {
        "execution_id": execution_id,
        "contract_id": "urn:agenlang:exec:test",
        "status": "completed",
        "timestamps": {"start": "2026-03-03T00:00:00Z", "end": "2026-03-03T00:01:00Z"},
        "decision_points": [
            {
                "type": "tool_call",
                "location": "step_0",
                "chosen": True,
                "rationale": "web_search",
            },
            {
                "type": "tool_call",
                "location": "step_1",
                "chosen": True,
                "rationale": "summarize",
            },
        ],
        "resource_usage": {"joules_used": 230.0, "steps_completed": 2},
        "reputation_score": 0.95,
    }


def test_acp_to_agui_flow() -> None:
    """ACP contract -> runtime execute -> SER -> AG-UI events."""
    contract = _load_contract()

    acp_msg = contract_to_acp_message(contract)
    assert acp_msg["protocol"] == "agenlang-v1"
    assert acp_msg["sender"] == contract.issuer.agent_id

    parsed = acp_message_to_contract(acp_msg)
    assert parsed.contract_id == contract.contract_id

    ser = _make_ser()
    events = ser_to_agui_events(ser)
    event_types = [e["type"] for e in events]
    assert EVENT_RUN_STARTED in event_types
    assert EVENT_RUN_FINISHED in event_types

    sse_lines = list(stream_ser_events(ser))
    assert any("RunStarted" in line for line in sse_lines)
    assert any("RunFinished" in line for line in sse_lines)


def test_anp_to_mcp_roundtrip(tmp_path: Path) -> None:
    """ANP envelope -> verify -> MCP handle_mcp_call."""
    km = KeyManager(key_path=tmp_path / "keys.pem")
    km.generate()
    contract = _load_contract()

    envelope = create_anp_envelope(contract, km)
    assert envelope["protocol"] == "anp"
    assert envelope["sender_did"].startswith("did:key:z")
    assert verify_anp_envelope(envelope, km)

    with (
        patch("agenlang.tools._web_search_tavily") as mock_ws,
        patch("agenlang.tools._summarize_llm") as mock_sum,
    ):
        mock_ws.return_value = "Flight results..."
        mock_sum.return_value = "Summary of flights"
        result = handle_mcp_call({"contract": envelope["payload"]})
    assert result["isError"] is False
    content_text = result["content"][0]["text"]
    parsed = json.loads(content_text)
    assert parsed["result"]["status"] == "success"


def test_full_protocol_chain(tmp_path: Path) -> None:
    """Contract -> ACP message -> parse back -> runtime -> SER -> AG-UI -> SSE."""
    km = KeyManager(key_path=tmp_path / "keys.pem")
    km.generate()
    contract = _load_contract()
    contract.sign(km)
    assert contract.verify_signature()

    acp_msg = contract_to_acp_message(contract)
    assert "content" in acp_msg

    parsed_contract = acp_message_to_contract(acp_msg)
    assert parsed_contract.contract_id == contract.contract_id

    with (
        patch("agenlang.tools._web_search_tavily") as mock_ws,
        patch("agenlang.tools._summarize_llm") as mock_sum,
    ):
        mock_ws.return_value = "Flight search results"
        mock_sum.return_value = "Summary of flight options"
        runtime = Runtime(parsed_contract, key_manager=km)
        result, ser = runtime.execute()

    assert result["status"] == "success"
    assert ser["resource_usage"]["joules_used"] > 0

    events = ser_to_agui_events(ser)
    event_types = [e["type"] for e in events]
    assert EVENT_RUN_STARTED in event_types
    assert EVENT_RUN_FINISHED in event_types

    sse_output = list(stream_ser_events(ser))
    for line in sse_output:
        assert line.startswith("event: ")
        assert "data: " in line
        assert line.endswith("\n\n")
