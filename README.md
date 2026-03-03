# AgenLang

**Shared contract substrate for secure, auditable, economically fair inter-agent communication**

AgenLang is a lightweight, model-agnostic standard that lets personal agents (OpenClaw/Amazo-style) and ZHC swarms safely delegate tasks to each other.

## Kernel Architecture

AgenLang v0.4.0 is a minimal viable kernel focused on correctness and security:

- **Contract** — JSON contract with ECDSA signing, intent anchoring, capability attestations
- **Runtime** — Deterministic sequential workflow execution with Joule metering
- **SER** — HMAC-protected Structured Execution Record with replay verification
- **A2A** — Transport wrapper for the Linux Foundation A2A protocol (JSON-RPC + SSE)
- **Signed Ledger** — Double-entry settlement ledger with per-step ECDSA signatures
- **Encrypted Memory** — AES-256-GCM memory backend with GDPR-ready handoff and purge
- **Leak Prevention** — Contracts with embedded API keys are rejected at validation time

**Key numbers:**

| Metric | Value |
|--------|-------|
| Token overhead (compressed) | 40–110 |
| Contract signing | ECDSA P-256 |
| Memory encryption | AES-256-GCM |
| SER integrity | HMAC-SHA256 |
| Reputation scoring | Built-in |

## Installation

```bash
pip install agenlang
```

## Usage

```bash
# Set API keys for real tool execution
export TAVILY_API_KEY="your-tavily-key"
export LLM_PROVIDER="openai"          # or anthropic, xai, generic
export LLM_API_KEY="your-api-key"     # falls back to XAI_API_KEY/OPENAI_API_KEY/ANTHROPIC_API_KEY

# Run a contract
agenlang run examples/amazo-flight-booking.json
```

### Programmatic

```python
from agenlang.contract import Contract
from agenlang.runtime import Runtime
from agenlang.keys import KeyManager

contract = Contract.from_file("examples/amazo-flight-booking.json")

km = KeyManager()
contract.sign(km)
assert contract.verify_signature()

runtime = Runtime(contract, key_manager=km)
result, ser = runtime.execute()
print(result["output"])
print(runtime.to_ser_json(ser))
```

## AgenLang-over-A2A Profile

AgenLang contracts can be wrapped for transport via the Linux Foundation A2A protocol:

```python
from agenlang.a2a import (
    contract_to_a2a_payload,
    a2a_payload_to_contract,
    contract_to_sse_event,
    parse_sse_event,
)

payload = contract_to_a2a_payload(contract)
restored = a2a_payload_to_contract(payload)

sse = contract_to_sse_event(contract)
restored = parse_sse_event(sse)
```

Token overhead: <80 tokens when compressed.

## Documentation

- [AGENTS.md](AGENTS.md) — Project context, Do Not rules
- [skills.md](skills.md) — Register AgenLang as a tool in LangChain/CrewAI/OpenClaw
- [threat_model.md](threat_model.md) — NIST SP 800-53 threat matrix
