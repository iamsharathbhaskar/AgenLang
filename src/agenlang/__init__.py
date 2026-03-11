"""AgenLang Core Protocol - Agent-to-Agent communication with DID identity."""

__version__ = "0.1.0"

from agenlang.core import BaseAgent, Database
from agenlang.identity import (
    Identity,
    generate_did_key,
    parse_did_key,
    verify_signature,
    generate_nonce,
)
from agenlang.schema import (
    Performative,
    ErrorCode,
    MessageEnvelope,
    MessageContent,
    Message,
    AgentCard,
    ProtocolMeta,
)
from agenlang.transport import Transport, HTTPTransport, WebSocketTransport

__all__ = [
    "__version__",
    "BaseAgent",
    "Database",
    "Identity",
    "generate_did_key",
    "parse_did_key",
    "verify_signature",
    "generate_nonce",
    "Performative",
    "ErrorCode",
    "MessageEnvelope",
    "MessageContent",
    "Message",
    "AgentCard",
    "ProtocolMeta",
    "Transport",
    "HTTPTransport",
    "WebSocketTransport",
]


async def get_agent_card_data(agent_id: str) -> dict:
    """Get the agent card data for serving."""
    from agenlang.identity import Identity

    identity = Identity.load(agent_id)

    card_data = {
        "did": identity.did,
        "name": f"Agent {agent_id}",
        "description": "AgenLang agent",
        "capabilities": [],
        "transports": [],
        "updated_at": "2026-03-11T00:00:00Z",
        "signature": "",
    }

    return card_data
