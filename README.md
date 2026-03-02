# AgenLang

**Shared contract substrate for secure, auditable, economically fair inter-agent communication**

AgenLang is a lightweight, model-agnostic standard that lets personal agents (OpenClaw/Amazo-style) and ZHC swarms safely delegate tasks to each other.

**Key features**

- 40–110 token overhead (compressed)
- Cryptographic capability proofs (prevents supply-chain attacks)
- Intent anchoring (prevents goal hijacking)
- Built-in JouleWork settlement
- GDPR-ready memory handoff and purge
- Full HMAC-protected Structured Execution Record (SER) with replay

**Installation**

```bash
pip install agenlang
```

**Usage**

```bash
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
  "resource_usage": { "joules_used": ..., "usd_cost": ... },
  ...
}
SER saved to urn:agenlang:exec:....ser.json
```

**Programmatic usage**

```python
from agenlang.contract import Contract
from agenlang.runtime import Runtime

contract = Contract.from_file("examples/amazo-flight-booking.json")
runtime = Runtime(contract)
result, ser = runtime.execute()
print(result["output"])
print(runtime.to_ser_json(ser))
```

**AgenLang-over-A2A Profile**

AgenLang contracts can be wrapped for transport via the Linux Foundation A2A protocol:

```python
from agenlang.a2a import contract_to_a2a_payload, a2a_payload_to_contract

payload = contract_to_a2a_payload(contract)
# Send payload over A2A transport...
contract = a2a_payload_to_contract(received_payload)
```

Token overhead: &lt;80 tokens when compressed.

**Documentation**

- [AGENTS.md](AGENTS.md) — Project context, Do Not rules, checkpoint card
- [PROTOCOL.md](PROTOCOL.md) — Phased development protocol (Phases 0–5)
