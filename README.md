# AgenLang

**Shared contract substrate for secure, auditable, economically fair inter-agent communication**

AgenLang is a lightweight, model-agnostic standard that lets personal agents (OpenClaw/Amazo-style) and ZHC swarms safely delegate tasks to each other.

**Key features**

- 40–110 token overhead (compressed)
- ECDSA contract signing with persistent key management
- Cryptographic capability proofs (prevents supply-chain attacks)
- Intent anchoring (prevents goal hijacking)
- Built-in JouleWork settlement with reputation scoring
- AES-GCM encrypted memory with GDPR-ready handoff and purge
- Full HMAC-protected Structured Execution Record (SER) with replay
- A2A transport wrapper (JSON-RPC and SSE)
- Protocol adapters: ACP, MCP, FIPA, AG-UI, ANP, W3C DID, OASF
- Weighted probabilistic workflow execution
- NIST-aligned threat model

**Installation**

```bash
pip install agenlang
```

**Usage**

```bash
# Set API keys for real tool execution
export TAVILY_API_KEY="your-tavily-key"
export XAI_API_KEY="your-xai-key"

# Run a contract from a JSON file
agenlang run examples/amazo-flight-booking.json
```

Example output:

```
Execution successful!
Goal: Delegate flight booking from LAX to SFO under $150 to ZHC travel agent
Result: Executed goal: ...
SER (audit trail):
{
  "execution_id": "urn:agenlang:exec:...",
  "timestamps": { "start": "...", "end": "..." },
  "resource_usage": { "joules_used": 230.0, "usd_cost": 0.023 },
  "reputation_score": 0.885,
  ...
}
SER saved to urn:agenlang:exec:....ser.json
```

**Programmatic usage**

```python
from agenlang.contract import Contract
from agenlang.runtime import Runtime
from agenlang.keys import KeyManager

contract = Contract.from_file("examples/amazo-flight-booking.json")

# Sign the contract
km = KeyManager()
contract.sign(km)
assert contract.verify_signature()

# Execute
runtime = Runtime(contract, key_manager=km)
result, ser = runtime.execute()
print(result["output"])
print(runtime.to_ser_json(ser))
```

**AgenLang-over-A2A Profile**

AgenLang contracts can be wrapped for transport via the Linux Foundation A2A protocol:

```python
from agenlang.a2a import (
    contract_to_a2a_payload,
    a2a_payload_to_contract,
    contract_to_sse_event,
    parse_sse_event,
)

# JSON-RPC payload
payload = contract_to_a2a_payload(contract)
restored = a2a_payload_to_contract(payload)

# Server-Sent Events (streaming)
sse = contract_to_sse_event(contract)
restored = parse_sse_event(sse)
```

Token overhead: <80 tokens when compressed.

**Benchmarks**

| Metric | AgenLang | Raw A2A |
|--------|----------|---------|
| Token overhead (compressed) | 40–110 | 200–400 |
| Contract signing | ECDSA P-256 | N/A |
| Memory encryption | AES-256-GCM | N/A |
| SER integrity | HMAC-SHA256 | N/A |
| Reputation scoring | Built-in | N/A |

**Protocol Compatibility**

AgenLang integrates with all major agent communication protocols:

| Protocol | Adapter | Integration |
|----------|---------|-------------|
| A2A | `a2a.py` | JSON-RPC 2.0 + SSE transport |
| ACP | `acp.py` | REST message envelopes |
| MCP | `mcp.py` | Tool registration (JSON-RPC) |
| FIPA | `fipa.py` | ACL performative mapping |
| AG-UI | `agui.py` | SER lifecycle event streaming |
| ANP | `anp.py` | DID-based P2P contract exchange |
| W3C DID | `w3c.py` | DID:web + DID:key identity |
| OASF | `oasf.py` | Schema manifest generation |

Use protocol prefixes in workflow steps for auto-dispatch:

```json
{"action": "subcontract", "target": "acp:https://remote-agent.example.com/acp"}
{"action": "tool", "target": "mcp:agenlang_execute"}
{"action": "subcontract", "target": "anp:https://peer.example.com/anp"}
```

**Documentation**

- [AGENTS.md](AGENTS.md) — Project context, Do Not rules, checkpoint card
- [threat_model.md](threat_model.md) — NIST SP 800-53 threat matrix
