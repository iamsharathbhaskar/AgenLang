"""ACP (Agent Communication Protocol) REST adapter.

Maps AgenLang contracts to ACP REST message envelopes and provides
dispatch() for runtime protocol auto-detect.
"""

import json
import uuid
from typing import Any, Dict

import requests  # type: ignore[import-untyped]
import structlog

from .contract import Contract

log = structlog.get_logger()


def contract_to_acp_message(contract: Contract) -> Dict[str, Any]:
    """Convert an AgenLang contract to an ACP REST message envelope.

    Returns:
        ACP message dict with sender, receiver, performative, content.
    """
    return {
        "id": str(uuid.uuid4()),
        "sender": contract.issuer.agent_id,
        "receiver": contract.settlement.joule_recipient,
        "performative": "request",
        "protocol": "agenlang-v1",
        "content": contract.model_dump(),
        "language": "application/agenlang+json",
        "ontology": "agenlang:contract:v1.0",
    }


def acp_message_to_contract(msg: Dict[str, Any]) -> Contract:
    """Parse an ACP message back into an AgenLang Contract.

    Args:
        msg: ACP message dict with 'content' key holding contract data.

    Returns:
        Validated Contract instance.
    """
    content = msg.get("content", msg)
    if isinstance(content, str):
        content = json.loads(content)
    return Contract.model_validate(content)


def send_acp_message(url: str, contract: Contract, timeout: int = 30) -> Dict[str, Any]:
    """POST an ACP message envelope to a remote ACP endpoint.

    Args:
        url: ACP REST endpoint URL.
        contract: AgenLang contract to send.
        timeout: HTTP timeout in seconds.

    Returns:
        Response dict from the ACP endpoint.
    """
    message = contract_to_acp_message(contract)
    resp = requests.post(
        url,
        json=message,
        headers={"Content-Type": "application/json"},
        timeout=timeout,
    )
    resp.raise_for_status()
    log.info("acp_message_sent", url=url, msg_id=message["id"])
    return resp.json()


def dispatch(
    contract: Contract,
    action: str,
    target: str,
    args: Dict[str, Any],
) -> str:
    """Runtime dispatch hook: send contract via ACP to target URL.

    Args:
        contract: The executing contract.
        action: Step action type (tool, skill, subcontract, embed).
        target: ACP endpoint URL (the part after 'acp:').
        args: Step arguments.

    Returns:
        JSON string of the ACP response.
    """
    url = target if target.startswith("http") else f"https://{target}"
    try:
        result = send_acp_message(url, contract)
        return json.dumps(result)
    except Exception as e:
        log.error("acp_dispatch_error", target=target, error=str(e))
        return json.dumps({"status": "error", "error": str(e)})
