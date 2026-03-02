"""A2A transport wrapper — contracts as A2A payloads.

AgenLang-over-A2A Profile: wrap AgenLang contracts for transport
via the Linux Foundation A2A protocol.
"""

from typing import Any, Dict

from .contract import Contract


def contract_to_a2a_payload(contract: Contract) -> Dict[str, Any]:
    """Wrap contract as A2A-compatible payload.

    Returns:
        Dict with @type, @id, and agenlang_contract for A2A transport.
    """
    return {
        "@type": "AgenLangContract",
        "@id": contract.contract_id,
        "agenlang_version": contract.agenlang_version,
        "agenlang_contract": contract.model_dump(),
    }


def a2a_payload_to_contract(payload: Dict[str, Any]) -> Contract:
    """Extract and validate contract from A2A payload."""
    inner = payload.get("agenlang_contract", payload)
    return Contract.model_validate(inner)
