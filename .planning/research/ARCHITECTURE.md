# Architecture Research

**Domain:** Agent-to-Agent (A2A) Communication Protocols
**Researched:** 2026-03-11
**Confidence:** HIGH

## Standard Architecture

### System Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        Application Layer                                 │
├─────────────────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐   │
│  │  Agent A    │  │  Agent B    │  │  Agent C    │  │  Agent N    │   │
│  │             │  │             │  │             │  │             │   │
│  │ ┌─────────┐ │  │ ┌─────────┐ │  │ ┌─────────┐ │  │ ┌─────────┐ │   │
│  │ │Handler  │ │  │ │Handler  │ │  │ │Handler  │ │  │ │Handler  │ │   │
│  │ │  Loop   │ │  │ │  Loop   │ │  │ │  Loop   │ │  │ │  Loop   │ │   │
│  │ └────┬────┘ │  │ └────┬────┘ │  │ └────┬────┘ │  │ └────┬────┘ │   │
│  │      │      │  │      │      │  │      │      │  │      │      │   │
│  │ ┌────┴────┐ │  │ ┌────┴────┐ │  │ ┌────┴────┐ │  │ ┌────┴────┐ │   │
│  │ │ State   │ │  │ │ State   │ │  │ │ State   │ │  │ │ State   │ │   │
│  │ │Machine  │ │  │ │Machine  │ │  │ │Machine  │ │  │ │Machine  │ │   │
│  │ └─────────┘ │  │ └─────────┘ │  │ └─────────┘ │  │ └─────────┘ │   │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘   │
│         │                │                │                │          │
├─────────┴────────────────┴────────────────┴────────────────┴──────────┤
│                        Protocol Layer                                     │
├─────────────────────────────────────────────────────────────────────────┤
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────────┐ │
│  │   Identity      │  │     Schema      │  │    Negotiation          │ │
│  │   (DID:key)    │  │  (FIPA-ACL)     │  │    (CNP State Machine)  │ │
│  └────────┬────────┘  └────────┬────────┘  └────────────┬────────────┘ │
│           │                   │                         │               │
│  ┌────────┴───────────────────┴─────────────────────────┴─────────────┐ │
│  │                    Message Envelope                               │ │
│  │  (Signing/Verification, Canonicalization, Traceability)          │ │
│  └────────────────────────────┬───────────────────────────────────────┘ │
│                               │                                          │
│  ┌────────────────────────────┴───────────────────────────────────────┐ │
│  │                    Economy Module                                   │ │
│  │  (JouleMeter, SER Generation, Ledger)                              │ │
│  └────────────────────────────────────────────────────────────────────┘ │
├─────────────────────────────────────────────────────────────────────────┤
│                      Transport Layer                                     │
├─────────────────────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌─────────────┐  │
│  │    HTTP      │  │  WebSocket   │  │    mDNS     │  │  Brokers   │  │
│  │  (REST)      │  │   (SSE)      │  │ (Discovery) │  │(NATS/Redis)│  │
│  └──────┬───────┘  └──────┬───────┘  └──────────────┘  └─────────────┘  │
│         │                 │                                              │
├─────────┴─────────────────┴──────────────────────────────────────────────┤
│                      Persistence Layer                                   │
├─────────────────────────────────────────────────────────────────────────┤
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────────┐  │
│  │    Contracts     │  │   SER Records    │  │   Agent Cards       │  │
│  │    (SQLite)      │  │    (SQLite)      │  │    (Cache)          │  │
│  └──────────────────┘  └──────────────────┘  └──────────────────────┘  │
│  ┌──────────────────┐  ┌──────────────────┐                           │
│  │  Message Queue   │  │   Key Storage    │                           │
│  │    (SQLite)     │  │   (Encrypted)    │                           │
│  └──────────────────┘  └──────────────────┘                           │
└─────────────────────────────────────────────────────────────────────────┘
```

### Component Responsibilities

| Component | Responsibility | Typical Implementation |
|-----------|----------------|------------------------|
| **Agent (BaseAgent)** | Autonomous entity that sends/receives messages, manages lifecycle | Abstract base class with event handlers |
| **Identity Module** | DID:key generation, key storage, message signing/verification | `cryptography` library with Ed25519 |
| **Schema Module** | Message envelope validation, FIPA-ACL performatives | Pydantic v2 models |
| **Transport** | Message transmission over HTTP/WebSocket/mDNS | Async httpx, websockets, zeroconf |
| **Negotiation** | Contract Net Protocol state machine, proposal handling | State machine with TTL/rounds |
| **Economy** | Joule metering, SER generation, ledger management | Context managers, decorators |
| **Contracts** | Task lifecycle state management | Enum-based state machine |
| **Discovery** | Agent Card publication and retrieval | HTTP + mDNS |
| **Persistence** | SQLite for contracts, SERs, cards, message queue | aiosqlite async operations |

## Recommended Project Structure

```
src/agenlang/
├── __init__.py              # Public API exports
├── identity.py              # DID:key generation, signing, verification
├── schema.py               # Pydantic models for envelope + FIPA-ACL
├── contracts.py            # Task lifecycle state machine
├── core.py                 # BaseAgent abstract class
├── negotiation.py          # CNP state machine with haggling
├── economy.py              # JouleMeter, SER generation
├── bridge.py               # MCP client adapter
├── discovery.py            # Agent Card discovery
│
├── transport/
│   ├── __init__.py
│   ├── base.py            # Abstract transport interface
│   ├── http.py            # HTTP POST transport
│   ├── websocket.py       # WebSocket + SSE transport
│   └── brokers/           # Optional NATS/Redis (lazy-loaded)
│
└── observability/          # Optional OpenTelemetry (lazy-loaded)
```

### Structure Rationale

- **`identity.py`:** Must be built first — all other modules depend on cryptographic identity. No transport until JCS-signing is verified.
- **`schema.py`:** Second priority — defines the message contract all agents must follow. Pydantic provides validation before processing.
- **`contracts.py`:** Third — defines the task states that negotiation and economy modules depend on.
- **`core.py`:** Fourth — wires identity, schema, transport, persistence together. The BaseAgent is the integration point.
- **`negotiation.py`:** Fifth — builds on contracts to implement CNP with haggling support.
- **`economy.py`:** Sixth — integrates with negotiation for atomic settlement on task completion.
- **`bridge.py`:** Final — consumes MCP servers as AgenLang agents.
- **`transport/`:** Can be built in parallel with core after schema is stable. HTTP first, then WebSocket, then brokers.
- **`discovery.py`:** Depends on identity (for signing cards) and transport.

## Architectural Patterns

### Pattern 1: Signed Message Envelope

**What:** Every message carries a detached Ed25519 signature over canonicalized content (RFC 8785). The envelope contains sender/receiver DIDs, nonce, timestamp, traceability fields.

**When to use:** When agents need non-repudiation, replay protection, and multi-hop traceability.

**Trade-offs:**
- Pros: Cryptographic trust without centralized CA, cross-language compatibility, audit trail
- Cons: Computational overhead for signing/verification, complexity in key management

**Example:**
```python
# Signing pipeline (from AgenLang spec)
signing_payload = {
    "envelope": {k: v for k, v in envelope.items() if k != "signature"},
    "content": content_dict  # parsed Pydantic model → dict
}
canonical_bytes = rfc8785.canonicalize(signing_payload)  # sorted keys
digest = hashlib.sha256(canonical_bytes).digest()
signature = ed25519_private_key.sign(digest)
```

### Pattern 2: Agent Card Discovery

**What:** Each agent publishes a self-describing document (Agent Card) with DID, capabilities, pricing, and transport endpoints. Other agents discover via HTTP or mDNS.

**When to use:** For dynamic agent ecosystems where capabilities may change.

**Trade-offs:**
- Pros: Decentralized discovery, no registry bottleneck, capability-based routing
- Cons: Cache invalidation challenges, potential for stale cards

**Example:**
```python
# Agent Card structure (from spec)
agent_card = {
    "did": "did:key:z6MkpTHR8VNsBxYaaWhcM8z5VAbmzU3NaXPt9gRy2Kz5",
    "name": "Document Summarizer v1",
    "capabilities": [{"task": "summarize", "input_schema": {...}}],
    "pricing": {"base_joules": 15.0, "weights": {...}},
    "transports": [{"type": "http", "url": "https://agent.example.com/agenlang"}],
    "signature": "Ed25519-base64url-signature"
}
```

### Pattern 3: Contract Net Protocol (CNP) with Haggling

**What:** Initiator broadcasts task → Participants respond with proposals → Initiator selects → Negotiation continues with PROPOSE/REJECT-PROPOSAL rounds until ACCEPT-PROPOSAL or timeout.

**When to use:** For task allocation where price/capabilities need negotiation.

**Trade-offs:**
- Pros: Optimal task allocation, competitive pricing, fault tolerance through multiple bidders
- Cons: Latency from multiple rounds, complexity in state management

**Example:**
```python
# CNP state machine states
class ContractState(Enum):
    INITIATED = "initiated"      # Task announced
    PROPOSED = "proposed"        # Proposals received
    ACCEPTED = "accepted"        # Proposal accepted
    RUNNING = "running"          # Task executing
    COMPLETED = "completed"      # Success
    FAILED = "failed"           # Error
    CANCELLED = "cancelled"      # Timeout/rejection
```

### Pattern 4: Joule-Based Metering with SER

**What:** Compute resource usage as "Joules" using weighted formula: (PromptTokens × W1) + (CompletionTokens × W2) + (ComputeSeconds × W3). Produce Signed Execution Record for verification.

**When to use:** For metered agent services where consumers need verifiable billing.

**Trade-offs:**
- Pros: Receiver-verifiable, cryptographic proof, prevents billing fraud
- Cons: Tokenizer variance requires tolerance thresholds, complexity in weight management

**Example:**
```python
# JouleMeter as context manager
with JouleMeter(agent_card.pricing.weights) as meter:
    result = agent.execute_task(task)
    ser = meter.generate_ser(result, prompt_hash, completion_hash)
    # SER contains all data for independent verification
```

### Pattern 5: Async Message Loop with Nonce Sentry

**What:** BaseAgent runs asyncio event loop processing incoming messages. All nonces stored in SQLite with TTL (24h default) to prevent replay attacks.

**When to use:** For production agents handling high message volume.

**Trade-offs:**
- Pros: Replay protection, async throughput, periodic cleanup prevents DB growth
- Cons: Requires async throughout (no blocking calls), clock sync needed

## Data Flow

### Outbound Message Flow

```
[Application Code]
    ↓
[BaseAgent.send_message()]
    ↓
[Identity.sign()] → RFC 8785 canonicalize → Ed25519 sign
    ↓
[Schema.validate()] → Pydantic model validation
    ↓
[Transport.send()] → HTTP POST / WebSocket / Broker
    ↓
[Persistence.queue_message()] → SQLite (for retry on failure)
```

### Inbound Message Flow

```
[Transport.receive()] → HTTP POST / WebSocket
    ↓
[Schema.validate()] → Pydantic envelope validation
    ↓
[Identity.verify()] → Extract sender DID → Verify signature
    ↓
[Nonce Sentry.check()] → Verify nonce not in last 24h → Store nonce
    ↓
[Trusted DIDs Filter] → Optional allow-list check
    ↓
[Router.dispatch()] → Route to on_request / on_propose / on_inform handler
    ↓
[Negotiation/Economy] → Process per protocol
    ↓
[Persistence.save_contract()] → SQLite
```

### Negotiation Flow

```
[Initiator] --CFP--> [Participant A, B, C]
                      ↓
              [Each responds with PROPOSE or REFUSE]
                      ↓
[Initiator] <--PROPOSE-- [Best Participant]
                      ↓
              [Haggling: PROPOSE ↔ PROPOSE ↔ ...]
                      ↓
              [ACCEPT-PROPOSAL or REJECT-PROPOSAL]
                      ↓
[Contract State: RUNNING] → Task Execution → COMPLETED/FAILED
                      ↓
[Economy.settle()] → Joule transfer via SER
```

## Scaling Considerations

| Scale | Architecture Adjustments |
|-------|--------------------------|
| 0-10 agents | Single SQLite file per agent, direct HTTP transport, in-memory nonce cache |
| 10-100 agents | Add connection pooling, implement mDNS for local discovery, batch nonce cleanup |
| 100-1000 agents | Introduce Redis/NATS broker for reliability, implement agent card caching with TTL |
| 1000+ agents | Consider DHT for discovery, sharded databases, message deduplication at transport layer |

### Scaling Priorities

1. **First bottleneck: Database writes.** High-volume message loops hitting SQLite. Fix: Async-buffered writes via `asyncio.Queue` + `aiosqlite.executemany`.

2. **Second bottleneck: Signature verification.** Every message requires cryptographic ops. Fix: Cache verified DIDs, batch verifications during high load.

3. **Third bottleneck: Discovery.** mDNS doesn't scale beyond local network. Fix: Implement DHT or centralized registry for wide-area discovery.

## Anti-Patterns

### Anti-Pattern 1: Blocking I/O in Message Loop

**What people do:** Using `requests`, `time.sleep()`, synchronous database drivers in agent event handlers.

**Why it's wrong:** Blocks entire asyncio event loop, destroying throughput. Other messages queue behind blocking calls.

**Do this instead:** Use `httpx` (async), `asyncio.sleep()`, `aiosqlite`. All network/disk I/O must be non-blocking.

### Anti-Pattern 2: Skipping Signature Verification

**What people do:** Accepting messages without verifying Ed25519 signatures to save CPU cycles.

**Why it's wrong:** Enables message spoofing, replay attacks, man-in-the-middle attacks. Breaks trust model entirely.

**Do this instead:** Always verify signatures. Implement "Lazy Payload Validation": verify envelope signature before deserializing large payloads to prevent memory exhaustion.

### Anti-Pattern 3: Non-Atomic Settlement

**What people do:** Transferring Joules before task reaches COMPLETED state.

**Why it's wrong:** Task may fail after payment, creating "payment for nothing" scenarios. Double-spend possible.

**Do this instead:** Only trigger settlement in COMPLETED state. Use FAILED/CANCELLED to rollback pending reservations.

### Anti-Pattern 4: Storing Private Keys in Agent Cards

**What people do:** Including private keys or secrets in the published Agent Card for "convenience."

**Why it's wrong:** Agent Cards are publicly discoverable. Private key exposure enables impersonation and message forging.

**Do this instead:** Keys stored encrypted in `.agenlang/keys/`. Agent Card contains only public DID.

### Anti-Pattern 5: No Nonce Expiration

**What people do:** Storing nonces forever to prevent all replay attacks.

**Why it's wrong:** Database grows unbounded. Memory pressure eventually crashes agent.

**Do this instead:** Implement automatic nonce pruning (24h TTL default). Balance security window vs. storage growth.

## Integration Points

### External Services

| Service | Integration Pattern | Notes |
|---------|---------------------|-------|
| **MCP Servers** | Bridge module wraps MCP as stateless AgenLang agents | Consumes, never exposes as MCP |
| **Stripe** | Future extension via economy module | For real-world micropayments |
| **Crypto** | Future extension via economy module | For decentralized settlement |
| **OpenTelemetry** | Optional observability extra | Lazy-loaded, zero impact when disabled |

### Internal Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| Identity ↔ Schema | Direct import | Identity returns signatures, Schema validates structure |
| Schema ↔ Core | Event handlers | Core dispatches to on_request, on_propose, etc. |
| Core ↔ Transport | Abstract interface | Pluggable HTTP/WebSocket/broker |
| Negotiation ↔ Economy | Contract state | Economy settles only on COMPLETED |
| Discovery ↔ Transport | Card caching | Discovered cards stored with TTL |

## Build Order Dependencies

```
Phase 0: Protocol Skeleton
├── identity.py (DID:key generation, signing, RFC 8785 canonicalization)
├── schema.py (Message envelope, FIPA-ACL performatives)
└── core.py (BaseAgent skeleton with SQLite init)

Phase 1: Foundation
├── identity.py (Complete key storage/rotation)
├── schema.py (Full validation)
├── core.py (Complete with event handlers)
└── persistence.py (CRUD for contracts, SERs, cards)

Phase 2: Exchange & Economy
├── negotiation.py (CNP state machine, haggling)
├── economy.py (JouleMeter, SER generation)
└── core.py (Integrate negotiation + economy hooks)

Phase 3: Bridge & Polish
├── bridge.py (MCP client adapter)
├── discovery.py (HTTP + mDNS)
└── CLI tools
```

### Critical Dependency: Identity Before Transport

The "Iron Rule" from the spec: **Do not build the transport until JCS-signing is 100% verified.** All subsequent security depends on this foundation. Build identity module first, test exhaustively, then proceed to transport.

## Sources

- **A2A Protocol Specification:** https://a2aprotocol.ai/docs/guide/a2a-protocol-specification-python
- **Python A2A Implementation:** https://python-a2a.readthedocs.io/
- **FIPA Contract Net Protocol:** http://www.fipa.org/specs/fipa00029/SC00029H.pdf
- **NegMAS (Negotiation Multi-Agent System):** https://negmas.readthedocs.io/
- **Google A2A Protocol:** https://cloud.google.com/discover/what-is-a-multi-agent-system
- **RFC 8785 (JSON Canonicalization):** https://datatracker.ietf.org/doc/html/rfc8785
- **DID:key Specification:** https://w3c-ccg.github.io/did-method-key/

---

*Architecture research for: Agent-to-Agent (A2A) Communication Protocols*
*Researched: 2026-03-11*
