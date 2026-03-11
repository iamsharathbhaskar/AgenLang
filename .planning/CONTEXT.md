# Phase 1 CONTEXT — Revised Architecture (A2A-Based)

**Status:** Complete pivot to use A2A as transport, add DID identity + FIPA-ACL semantics on top

---

## Architecture: OSI-Style Layering

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  LAYER 7 - Application Semantics                                          │
│  FIPA-ACL Performatives: REQUEST, PROPOSE, ACCEPT-PROPOSAL,               │
│  REJECT-PROPOSAL, INFORM, AGREE, REFUSE, FAILURE, CANCEL, CFP,           │
│  NOT_UNDERSTOOD                                                           │
│  → agenlang.semantics (NEW)                                               │
├─────────────────────────────────────────────────────────────────────────────┤
│  LAYER 6 - Presentation                                                    │
│  DID Identity + RFC 8785 Signing                                           │
│  → agenlang.identity (KEEP)                                                │
├─────────────────────────────────────────────────────────────────────────────┤
│  LAYER 5 - Session                                                        │
│  Conversation threading: conversation_id, reply_with, in_reply_to          │
│  Traceability: trace_id, parent_contract_id                                │
│  → agenlang.session (NEW - simplified)                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│  LAYER 4 - Transport                                                      │
│  A2A Protocol: JSON-RPC 2.0 over HTTP(S), SSE for streaming              │
│  → Use google-a2a SDK (REPLACE our transport)                              │
├─────────────────────────────────────────────────────────────────────────────┤
│  LAYER 3 - Network Discovery                                              │
│  Agent Cards at /.well-known/agent.json (A2A format + DID extension)        │
│  → agenlang.discovery (MERGE with A2A)                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│  LAYER 2 - Data Link                                                      │
│  Ed25519 key pairs, did:key format                                        │
│  → agenlang.identity (KEEP)                                                │
├─────────────────────────────────────────────────────────────────────────────┤
│  LAYER 1 - Physical                                                      │
│  Cryptographic keys                                                       │
│  → agenlang.identity (KEEP)                                               │
├─────────────────────────────────────────────────────────────────────────────┤
│  LAYER 0 - Economy (AgenLang Unique)                                     │
│  JouleMeter, Signed Execution Records                                      │
│  → agenlang.economy (KEEP - unique value)                                 │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## What A2A Already Handles (Use These!)

| A2A Component | How We Use It |
|---------------|---------------|
| JSON-RPC 2.0 over HTTP | Transport layer |
| Agent Cards | Discovery (extend with DID) |
| Task lifecycle (submitted/working/completed/failed) | Contract state (extend with CNP) |
| Streaming via SSE | Real-time responses |
| Auth via headers | Base auth (we add DID signing) |

---

## Revised Module Mapping

### KEEP (From Original Plan)
| Module | Purpose | Reason |
|--------|---------|--------|
| `identity.py` | DID:key generation, Ed25519 keys, RFC 8785 signing | A2A doesn't do DID |
| `schema.py` | FIPA-ACL performatives, message envelope | This IS our value add |
| `economy.py` | JouleMeter, SER generation | Unique to AgenLang |

### REPLACE (Use A2A Instead)
| Original | Replace With |
|----------|-------------|
| `transport/` | `google-a2a` SDK |
| `core.py` (BaseAgent) | Simple `AgentClient` class |

### MERGE (Extend A2A)
| Original | How to Merge |
|----------|--------------|
| `discovery.py` | Use A2A AgentCard format + add DID field |
| `contracts.py` | Use A2A task states + add CNP semantics |

### NEW
| Module | Purpose |
|--------|---------|
| `client.py` | Simple `AgentClient` class - not a framework |
| `semantics.py` | FIPA-ACL message construction helpers |

---

## What to KEEP From Original Plan

### Identity (Keep Exactly As-Is)
- Ed25519 key generation with `cryptography`
- DID:key format (`z6Mk...`)
- RFC 8785 canonicalization for signing
- Key storage in `~/.agenlang/keys/`

### Schema (Keep, This Is The Semantics Layer)
- All FIPA-ACL performatives: REQUEST, PROPOSE, ACCEPT-PROPOSAL, REJECT-PROPOSAL, INFORM, AGREE, REFUSE, FAILURE, CANCEL, CFP, NOT_UNDERSTOOD
- Message envelope with: message_id, sender_did, receiver_did, nonce, timestamp, trace_id, conversation_id, parent_contract_id
- Error registry: ERR_CAPABILITY_MISMATCH, ERR_INSUFFICIENT_JOULES, ERR_PAYLOAD_TOO_LARGE, ERR_TASK_TIMEOUT

### Economy (Keep, Unique Value)
- JouleMeter with weighted formula
- Signed Execution Records (SER)
- Token counting via tiktoken

### Bridge (Keep)
- MCP Client adapter to wrap MCP servers as AgenLang agents

---

## What to REPLACE

### Transport → Use A2A
```python
# OLD (DISCARD)
class HTTPTransport(Transport):
    async def send(self, url: str, message: dict): ...

# NEW (USE A2A)
from a2a_client import A2AClient

client = A2AClient(agent_url="https://agent.example.com/a2a")
await client.send_message(task={'...'})
```

### BaseAgent Framework → Simple Client
```python
# OLD (DISCARD)
class BaseAgent(ABC):
    async def on_request(self, message): ...
    async def on_propose(self, message): ...

# NEW (SIMPLE CLIENT)
from agenlang import AgentClient

client = AgentClient(did="did:key:z6Mk...")
result = await client.call(
    to="did:key:z6Mh...",
    action="summarize",
    payload={"text": "..."}
)
```

---

## Target API Design

### Simple Client (What Agents Use)
```python
from agenlang import AgentClient

client = AgentClient(
    did="did:key:z6Mk...",  # Your DID
    key_path="~/.agenlang/keys/my-key",
)

# Send a REQUEST (like a function call)
result = await client.request(
    to="did:key:z6Mh...",
    action="summarize",
    payload={"text": "long document..."}
)

# PROPOSE (start negotiation)
proposal = await client.propose(
    to="did:key:z6Mh...",
    action="process",
    payload={...},
    pricing={"base_joules": 15, "weights": {...}}
)

# ACCEPT or REJECT
await client.accept(proposal)
await client.reject(proposal, reason="ERR_INSUFFICIENT_JOULES")

# INFORM (fire-and-forget)
await client.inform(
    to="did:key:z6Mh...",
    content={"status": "completed", "result": "..."}
)
```

### Receiver (Minimal HTTP Handler)
```python
from agenlang import AgentHandler

handler = AgentHandler(did="did:key:z6Mk...", key_path="...")

# Just parses and verifies - developer passes to their LLM
message = await handler.receive()
# message = {
#   "performative": "REQUEST",
#   "sender_did": "did:key:z6Mh...",
#   "action": "summarize",
#   "payload": {"text": "..."}
# }

# Developer sends response back
await handler.respond(message_id, {"summary": "..."})
```

---

## Dependencies

### Core (Required)
- `google-a2a` - A2A protocol transport
- `cryptography` - Ed25519 keys
- `rfc8785` - JSON canonicalization
- `pydantic` - Schema validation
- `tiktoken` - Token counting (for JouleMeter)

### Optional Extras
- `agenlang[brokers]` - NATS, Redis (deferred)
- `agenlang[observability]` - OpenTelemetry (deferred)

---

## Phase 1 Revised Goals

1. **Identity Module** - DID:key generation, RFC 8785 signing (from original)
2. **Semantics Module** - FIPA-ACL performatives (from original)
3. **Client** - Simple AgentClient class (NEW - replaces BaseAgent)
4. **A2A Integration** - Use A2A SDK for transport (REPLACE transport)
5. **Discovery** - Agent Cards with DID extension (MERGE)

---

## Questions Answered

| Question | Answer |
|----------|--------|
| Auto-handle negotiation? | NO - separate methods (.propose(), .accept(), .reject()) |
| Blocking or async? | ASYNC (per original plan) |
| Framework or library? | LIBRARY - simple client, no BaseAgent |
| Keep BaseAgent? | NO - remove entirely |

---

## Files to Delete/Rewrite

### Delete
- `src/agenlang/core.py` (BaseAgent)
- `src/agenlang/transport/__init__.py` (old transport)

### Rewrite
- `src/agenlang/__init__.py` - export AgentClient instead of BaseAgent
- Create `src/agenlang/client.py` - simple AgentClient

### Keep As-Is
- `src/agenlang/identity.py`
- `src/agenlang/schema.py`

---

*Context updated: 2026-03-12 — Revised to use A2A as transport layer*
