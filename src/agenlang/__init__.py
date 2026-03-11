"""AgenLang - A semantics layer on top of A2A protocol."""

__version__ = "0.1.0"

from agenlang.client import AgentClient, discover_agent
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

__all__ = [
    "__version__",
    "AgentClient",
    "discover_agent",
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
]
