"""A2A transport wrapper — contracts as A2A payloads.

AgenLang-over-A2A Profile: wrap AgenLang contracts for transport
via the Linux Foundation A2A protocol. Supports JSON and SSE formats.
"""

import json
from typing import Any, Dict, Optional

import structlog

from .contract import Contract

log = structlog.get_logger()


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


def dispatch(
    contract: Contract,
    action: str,
    target: str,
    args: Dict[str, Any],
    endpoint_url: Optional[str] = None,
    timeout: float = 300.0,
) -> str:
    """Dispatch a contract to a remote agent via A2A protocol.

    This is the implementation of the protocol dispatch that sends the contract
    to a remote agent's A2A endpoint and returns the response.

    Args:
        contract: The AgenLang contract to dispatch.
        action: Action type (tool, skill, subcontract, embed).
        target: Target identifier (e.g., agent ID or URL).
        args: Arguments for the action.
        endpoint_url: Override the endpoint URL. If not provided, target is used as URL.
        timeout: Request timeout in seconds.

    Returns:
        Response content from the remote agent.

    Raises:
        ValueError: If the request fails or returns an error.
    """
    import requests

    # Determine endpoint URL
    url = endpoint_url or target
    if not url.startswith(("http://", "https://")):
        # Assume localhost with target as path or default port
        url = f"http://localhost:8000/a2a"

    # Build A2A payload
    payload = contract_to_a2a_payload(contract)

    log.info("dispatching_contract", contract_id=contract.contract_id, target=target, url=url)

    try:
        response = requests.post(
            url,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=timeout,
        )
        response.raise_for_status()

        result = response.json()

        # Check for JSON-RPC error
        if "error" in result and result["error"]:
            error = result["error"]
            raise ValueError(f"A2A error {error.get('code', 'unknown')}: {error.get('message', 'unknown')}")

        # Return the output from the result
        if "result" in result and result["result"]:
            output = result["result"].get("output", "")
            log.info("dispatch_success", contract_id=contract.contract_id, output_length=len(output))
            return output

        return json.dumps(result)

    except requests.RequestException as e:
        log.error("dispatch_failed", contract_id=contract.contract_id, error=str(e))
        raise ValueError(f"Failed to dispatch contract to {url}: {e}") from e


def dispatch_sse(
    contract: Contract,
    endpoint_url: Optional[str] = None,
    timeout: float = 300.0,
) -> Dict[str, Any]:
    """Dispatch a contract via SSE streaming for async execution.

    Args:
        contract: The AgenLang contract to dispatch.
        endpoint_url: The A2A endpoint URL.
        timeout: Maximum time to wait for completion.

    Returns:
        Final result including output and SER.

    Raises:
        ValueError: If the request fails or returns an error.
    """
    import requests
    import time

    url = endpoint_url or "http://localhost:8000/a2a/stream"
    payload = contract_to_a2a_payload(contract)

    log.info("dispatching_contract_sse", contract_id=contract.contract_id, url=url)

    start_time = time.time()
    try:
        response = requests.post(
            url,
            json=payload,
            headers={"Content-Type": "application/json", "Accept": "text/event-stream"},
            stream=True,
            timeout=timeout,
        )
        response.raise_for_status()

        for line in response.iter_lines():
            if time.time() - start_time > timeout:
                raise ValueError("SSE timeout waiting for completion")

            if not line:
                continue

            line_str = line.decode("utf-8")
            if line_str.startswith("data: "):
                data = json.loads(line_str[6:])
                event_type = data.get("event", "")

                if event_type == "error":
                    raise ValueError(f"SSE error: {data.get('data', 'unknown')}")

                if event_type == "complete":
                    result_data = json.loads(data.get("data", "{}"))
                    log.info("sse_complete", contract_id=contract.contract_id)
                    return result_data

                if event_type == "heartbeat":
                    log.debug("sse_heartbeat", data=data.get("data"))

        raise ValueError("SSE stream ended without completion event")

    except requests.RequestException as e:
        log.error("dispatch_sse_failed", contract_id=contract.contract_id, error=str(e))
        raise ValueError(f"Failed to dispatch contract via SSE to {url}: {e}") from e
