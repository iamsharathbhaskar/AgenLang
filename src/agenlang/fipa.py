"""FIPA ACL (Agent Communication Language) adapter.

Maps AgenLang contract actions to FIPA performatives and converts
contracts to/from FIPA ACL message structure.
"""

import json
from typing import Any, Dict

import structlog

from .contract import Contract

log = structlog.get_logger()

PERFORMATIVE_MAP: Dict[str, str] = {
    "tool": "request",
    "skill": "query-ref",
    "subcontract": "propose",
    "embed": "inform",
}

REVERSE_PERFORMATIVE_MAP: Dict[str, str] = {v: k for k, v in PERFORMATIVE_MAP.items()}


def step_to_performative(step: Any) -> str:
    """Map a single workflow step to its FIPA performative.

    Args:
        step: WorkflowStep model or dict with 'action' key.

    Returns:
        FIPA performative string (e.g., 'request', 'propose').
    """
    action = step.action if hasattr(step, "action") else step.get("action", "")
    return PERFORMATIVE_MAP.get(action, "request")


def contract_to_fipa_acl(contract: Contract) -> Dict[str, Any]:
    """Convert an AgenLang contract to a FIPA ACL message structure.

    Uses the first workflow step's action to determine the performative.

    Returns:
        FIPA ACL dict with sender, receiver, performative, content,
        language, ontology, protocol, and conversation-id.
    """
    first_step = contract.workflow.steps[0] if contract.workflow.steps else None
    performative = step_to_performative(first_step) if first_step else "request"

    return {
        "performative": performative,
        "sender": {"name": contract.issuer.agent_id},
        "receiver": {"name": contract.settlement.joule_recipient},
        "content": json.dumps(contract.model_dump()),
        "language": "agenlang-json",
        "encoding": "utf-8",
        "ontology": "agenlang:contract:v1.0",
        "protocol": "agenlang-fipa-bridge",
        "conversation-id": contract.contract_id,
        "reply-with": f"{contract.contract_id}:reply",
    }


def fipa_acl_to_contract(acl: Dict[str, Any]) -> Contract:
    """Parse a FIPA ACL message back into an AgenLang Contract.

    Args:
        acl: FIPA ACL dict with 'content' key holding JSON contract.

    Returns:
        Validated Contract instance.
    """
    content = acl.get("content", "")
    if isinstance(content, str):
        content = json.loads(content)
    return Contract.model_validate(content)


def dispatch(
    contract: Any,
    action: str,
    target: str,
    args: Dict[str, Any],
) -> str:
    """Runtime dispatch hook: format as FIPA ACL and log.

    For FIPA, dispatch wraps the contract as an ACL message.
    Actual network transport is delegated to the caller.

    Args:
        contract: The executing contract.
        action: Step action type.
        target: FIPA receiver agent name (part after 'fipa:').
        args: Step arguments.

    Returns:
        JSON string of the FIPA ACL message.
    """
    acl = contract_to_fipa_acl(contract)
    acl["receiver"] = {"name": target}
    acl["performative"] = PERFORMATIVE_MAP.get(action, "request")
    log.info("fipa_dispatch", target=target, performative=acl["performative"])
    return json.dumps(acl)
