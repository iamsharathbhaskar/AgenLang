# AgenLang

Agent-to-Agent communication protocol with DID identity, signed YAML messages, CNP negotiation, and Joule-based metering.

## Features

- **DID Identity**: Ed25519 key pairs with did:key identifiers
- **Signed YAML Messages**: RFC 8785 canonicalization for cross-platform signatures
- **FIPA-ACL Performatives**: REQUEST, PROPOSE, ACCEPT-PROPOSAL, REJECT-PROPOSAL, INFORM, AGREE, REFUSE, FAILURE, CANCEL, CFP, NOT_UNDERSTOOD
- **CNP Negotiation**: Contract Net Protocol with multi-round haggling
- **Joule-based Metering**: Token-weighted computation metering with Signed Execution Records
- **HTTP/mDNS Discovery**: Agent Card-based discovery

## Installation

```bash
pip install agenlang
```

## Development Installation

```bash
pip install -e ".[dev]"
```

## Quick Start

```python
from agenlang import BaseAgent

# Create your agent
class MyAgent(BaseAgent):
    async def on_message(self, message):
        pass
    
    async def on_request(self, message):
        return {"result": "handled"}
    
    async def on_propose(self, message):
        return {"accepted": True}
    
    async def on_inform(self, message):
        pass

# Run the agent
agent = MyAgent(agent_id="my-agent", did="did:key:...", transport=http_transport)
await agent.start()
```

## CLI Usage

```bash
# Start an agent
agenlang start --config ~/.agenlang/myagent.yaml

# Discover agents
agenlang discover

# Inspect contract chain
agenlang inspect <trace_id>
```

## Requirements

- Python 3.11+
- See `pyproject.toml` for full dependencies

## License

MIT
