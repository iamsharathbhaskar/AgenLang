"""A2A transport wrapper — contracts as A2A payloads.

AgenLang-over-A2A Profile: wrap AgenLang contracts for transport
via the Linux Foundation A2A protocol. Supports JSON and SSE formats.
"""

import json
from typing import Any, Dict

from .contract import Contract


def contract_to_a2a_payload(contract: Contract) -> Dict[str, Any]:
    """Wrap contract as A2A-compatible JSON-RPC payload.

    Returns:
        A2A JSON-RPC 2.0 message with AgenLang contract as params.
    """
    return {
        "jsonrpc": "2.0",
        "method": "agenlang/execute",
        "id": contract.contract_id,
        "params": {
            "@type": "AgenLangContract",
            "@id": contract.contract_id,
            "agenlang_version": contract.agenlang_version,
            "contract": contract.model_dump(),
        },
    }


def a2a_payload_to_contract(payload: Dict[str, Any]) -> Contract:
    """Extract and validate contract from A2A payload."""
    params = payload.get("params", payload)
    inner = params.get("contract", params.get("agenlang_contract", params))
    return Contract.model_validate(inner)


def contract_to_sse_event(contract: Contract) -> str:
    """Format contract as Server-Sent Event for streaming A2A transport."""
    payload = contract_to_a2a_payload(contract)
    return f"event: agenlang\ndata: {json.dumps(payload)}\n\n"


def parse_sse_event(event_data: str) -> Contract:
    """Parse a Server-Sent Event back to a Contract."""
    for line in event_data.strip().split("\n"):
        if line.startswith("data: "):
            payload = json.loads(line[6:])
            return a2a_payload_to_contract(payload)
    raise ValueError("No data line found in SSE event")
