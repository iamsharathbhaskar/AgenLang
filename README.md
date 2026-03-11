# AgenLang

A semantics layer on top of Google's A2A protocol — adding DID identity, FIPA-ACL semantics, and Joule-based metering.

## What is AgenLang?

AgenLang provides a clean Python library for AI agents to communicate with each other. It sits on top of the A2A (Agent-to-Agent) protocol and adds:

- **DID Identity**: Cryptographic identity using `did:key` format
- **FIPA-ACL Semantics**: Well-defined message performatives (REQUEST, PROPOSE, ACCEPT-PROPOSAL, etc.)
- **Joule Metering**: Verifiable compute metering with Signed Execution Records

## Installation

```bash
pip install agenlang
```

## Quick Start

```python
from agenlang import AgentClient, Identity

# Load or create your agent identity
identity = Identity.load("my-agent")

# Create client
client = AgentClient(did=identity.did, identity=identity)

# Call another agent
result = await client.request(
    to="did:key:z6Mh...",
    action="summarize",
    payload={"text": "your text here"}
)

# Or negotiate with pricing
proposal = await client.propose(
    to="did:key:z6Mh...",
    action="process",
    payload={"data": "..."},
    pricing={"base_joules": 15, "per_1k_tokens": 2.5}
)
```

## CLI Usage

```bash
# Show your agent identity
agenlang identity

# Call another agent
agenlang call did:key:z6Mk... summarize '{"text": "hello"}'

# Discover agent capabilities
agenlang discover https://agent.example.com
```

## Key Features

| Feature | Description |
|---------|-------------|
| DID Identity | Ed25519 keys with did:key format |
| RFC 8785 Signing | Cross-platform cryptographic signatures |
| FIPA-ACL | REQUEST, PROPOSE, ACCEPT-PROPOSAL, INFORM, etc. |
| Joule Metering | Token-weighted compute tracking |
| CNP Negotiation | Multi-round haggling with TTL |

## Architecture

```
┌─────────────────────────────────────┐
│  FIPA-ACL Semantics Layer          │
│  (REQUEST, PROPOSE, ACCEPT, etc.)  │
├─────────────────────────────────────┤
│  DID Identity Layer                │
│  (Ed25519, RFC 8785 signing)       │
├─────────────────────────────────────┤
│  A2A Transport                     │
│  (HTTP, JSON-RPC, Agent Cards)     │
└─────────────────────────────────────┘
```

## Requirements

- Python 3.11+
- See `pyproject.toml` for dependencies

## License

MIT
