"""Tests for ACP (Agent Communication Protocol) adapter."""

import json
from pathlib import Path
from unittest.mock import patch

from agenlang.acp import (
    acp_message_to_contract,
    contract_to_acp_message,
    dispatch,
    send_acp_message,
)
from agenlang.contract import Contract

EXAMPLES_DIR = Path(__file__).parent.parent / "examples"


def _load_contract() -> Contract:
    return Contract.from_file(str(EXAMPLES_DIR / "amazo-flight-booking.json"))


def test_contract_to_acp_message() -> None:
    """ACP message has required envelope fields."""
    contract = _load_contract()
    msg = contract_to_acp_message(contract)
    assert msg["sender"] == contract.issuer.agent_id
    assert msg["receiver"] == contract.settlement.joule_recipient
    assert msg["performative"] == "request"
    assert msg["protocol"] == "agenlang-v1"
    assert "content" in msg
    assert msg["content"]["contract_id"] == contract.contract_id


def test_acp_roundtrip() -> None:
    """Contract survives ACP message roundtrip."""
    contract = _load_contract()
    msg = contract_to_acp_message(contract)
    restored = acp_message_to_contract(msg)
    assert restored.contract_id == contract.contract_id
    assert restored.goal == contract.goal


def test_acp_message_from_string_content() -> None:
    """ACP message with JSON-string content is parsed."""
    contract = _load_contract()
    msg = contract_to_acp_message(contract)
    msg["content"] = json.dumps(msg["content"])
    restored = acp_message_to_contract(msg)
    assert restored.contract_id == contract.contract_id


def test_send_acp_message_success() -> None:
    """send_acp_message POSTs to endpoint."""
    contract = _load_contract()
    with patch("agenlang.acp.requests.post") as mock_post:
        mock_post.return_value.raise_for_status = lambda: None
        mock_post.return_value.json.return_value = {"status": "received"}
        result = send_acp_message("https://example.com/acp", contract)
    assert result["status"] == "received"
    mock_post.assert_called_once()


def test_dispatch_error_handling() -> None:
    """dispatch returns error JSON on failure."""
    contract = _load_contract()
    with patch("agenlang.acp.requests.post", side_effect=Exception("timeout")):
        result = dispatch(contract, "subcontract", "example.com/acp", {})
    parsed = json.loads(result)
    assert parsed["status"] == "error"
