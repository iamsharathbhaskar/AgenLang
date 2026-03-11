# Feature Research

**Domain:** Agent-to-Agent (A2A) Communication Protocols
**Researched:** 2026-03-11
**Confidence:** HIGH

## Feature Landscape

### Table Stakes (Users Expect These)

Features users assume exist. Missing these = product feels incomplete or insecure.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| **Agent Discovery** | Users need to find other agents dynamically; hardcoded URLs don't scale | MEDIUM | Agent Cards at `/.well-known/agent-card.json` is the emerging standard (Google A2A, AgenLang). mDNS for local discovery. |
| **Message Transport (HTTP/WebSocket)** | Basic communication backbone; JSON-RPC 2.0 is the dominant pattern | LOW | HTTP POST for request-response, WebSocket/SSE for streaming. Must be HTTPS/WSS in production. |
| **Task Lifecycle Management** | Users need to track task state (pending → running → completed/failed) | MEDIUM | States: SUBMITTED, WORKING, INPUT_REQUIRED, COMPLETED, FAILED, CANCELLED. Critical for long-running tasks. |
| **Authentication & Authorization** | Enterprises require identity verification before allowing agent communication | MEDIUM | OAuth2, API keys, or DID-based identity. 22% of teams treat agents as independent identities (Gravitee 2026 survey). |
| **TLS/HTTPS Enforcement** | Security baseline for enterprise adoption; plaintext is unacceptable | LOW | Google A2A mandates HTTPS. AgenLang enforces HTTPS/WSS at startup. |
| **Message Schema/Format** | Structured communication requires consistent data models | LOW | JSON or YAML with defined envelope structure. JSON-RPC 2.0 for Google A2A, FIPA-ACL performatives for AgenLang. |
| **Error Handling & Status Codes** | Developers need programmatic recovery from failures | LOW | Standardized error codes (e.g., ERR_CAPABILITY_MISMATCH, ERR_TASK_TIMEOUT). Must include error_code in REFUSE/FAILURE. |
| **Streaming / Push Notifications** | Long-running tasks need real-time progress updates | MEDIUM | Server-Sent Events (SSE) is the standard pattern. Essential for enterprise UX. |
| **Capability Advertisement** | Agents must declare what they can do (input/output schemas) | MEDIUM | Agent Cards contain capabilities with task identifiers, input_schema, output_schema. |

### Differentiators (Competitive Advantage)

Features that set the product apart. Not required, but valuable for market position.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| **Cryptographic DID-Based Identity** | Verifiable, portable identity without centralized PKI; enables trust without pre-shared keys | HIGH | did:key format (Ed25519) is interoperable. AgenLang's core strength. Only ~22% of A2A implementations have this (2026). |
| **Joule-Based Metering & Settlement** | Receiver-validatable micro-payments; enables agent economy without trusted third party | HIGH | Unique to AgenLang. Uses Signed Execution Records (SER) with prompt/completion hashes. x402 (Coinbase) is complementary, not competing. |
| **Contract Net Protocol (CNP) with Haggling** | Multi-round negotiation enables price/term discovery; more flexible than simple request-response | MEDIUM | FIPA-ACL: CFP → PROPOSE ↔ PROPOSE → ACCEPT/REJECT. TTL and max-rounds prevent infinite loops. |
| **Signed Execution Records (SER)** | Cryptographic proof of work done; enables dispute resolution and audit trails | HIGH | Contains: token breakdown, compute seconds, weights, prompt_hash, completion_hash, signature. |
| **Multi-Hop Traceability** | Full audit trail across agent chains (trace_id + parent_contract_id); essential for enterprise compliance | MEDIUM | Unique to AgenLang. Enables billing aggregation and dispute resolution across subcontracting chains. |
| **MCP Bridge (Consume External MCP Servers)** | Leverage existing MCP tool ecosystem; extends AgenLang capabilities without rebuilding | MEDIUM | AgenLang consumes MCP, never exposes as MCP server. Wraps MCP tools as stateless AgenLang agents. |
| **Message Signing with RFC 8785 Canonicalization** | Cross-language signature compatibility; ensures JavaScript, Python, Go all verify same | MEDIUM | Pure whitespace/ordering differences won't break signatures. Critical for interoperability. |
| **Broker Transports (NATS/Redis)** | Enterprise-grade reliability for corporate LANs; optional but valuable for high-stakes deployments | MEDIUM | Lazy-loaded optional extras. Zero impact on core library when not used. |
| **OpenTelemetry Observability** | Enterprise operational visibility; W3C Trace-Context integration for distributed tracing | MEDIUM | Optional extra. Activated only when explicitly enabled. |
| **Nonce Sentry (Replay Protection)** | Prevents message replay attacks; critical for financial/security-sensitive deployments | MEDIUM | Requires async-buffered writes to avoid bottlenecking. TTL-based pruning (24h default). |

### Anti-Features (Commonly Requested, Often Problematic)

Features that seem good but create problems.

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| **Expose AgenLang as MCP Server** | MCP is popular, seems like easy integration | Violates protocol architecture; creates confusion about primary protocol | Consume MCP servers via bridge module; don't expose as server |
| **Plaintext HTTP in Development** | Easier debugging, faster iteration | Creates security risk; habits form and leak to production | Use localhost TLS or explicit dev mode with clear warnings |
| **Blocking I/O in Message Loop** | Simpler synchronous code | Kills concurrency; blocks all other messages during I/O | asyncio-native (httpx, aiosqlite, websockets) |
| **Hardcoded Secrets in Agent Cards** | Simpler configuration | Security violation; cards are broadcast publicly | Use OS keyring or encrypted key storage |
| **Payment Without Verification** | Faster transactions | Enables fraud; receiver can't validate Joules | Require SER with verifiable hashes and weights |
| **Accept Any Payload Size** | Flexibility | Memory exhaustion attacks; 10MB+ payloads crash agents | Enforce payload limits; reject with NOT_UNDERSTOOD + ERR_PAYLOAD_TOO_LARGE |
| **Global Trust (No Whitelist)** | Simpler initial setup | Accepts messages from any DID; security risk | Optional trusted_dids filter for production |
| **Real-Time Everything** | Better UX | Massive infrastructure cost; most tasks don't need it | SSE for tasks that genuinely need it; polling for rest |

## Feature Dependencies

```
Agent Identity (DID Generation)
    └──requires──> Message Signing & Verification
                       └──requires──> RFC 8785 Canonicalization
                                              └──requires──> Schema Validation

Agent Discovery (Agent Cards)
    └──requires──> Transport Layer (HTTP/WS)
    └──enhances──> Agent Identity

Negotiation (CNP)
    └──requires──> Schema (FIPA Performatives)
    └──requires──> Transport Layer
    └──requires──> Agent Identity

Economy (Joule Metering)
    └──requires──> Negotiation (contract state)
    └──requires──> Task Lifecycle (COMPLETED state trigger)
    └──requires──> Agent Identity (for SER signing)
    └──enhances──> Multi-Hop Traceability (for billing aggregation)

MCP Bridge
    └──requires──> Transport Layer
    └──requires──> Schema
    └──enhances──> Agent Discovery (exposes MCP tools as capabilities)

Broker Transports (NATS/Redis)
    └──requires──> Transport Layer (abstract interface)
    └──conflicts──> Direct HTTP/WebSocket (mutually exclusive per message)

Observability (OpenTelemetry)
    └──enhances──> All modules (tracing context propagation)
```

### Dependency Notes

- **Agent Identity requires Message Signing:** You can't sign without an identity. RFC 8785 canonicalization must work before signatures are valid.
- **Economy requires Negotiation + Task Lifecycle:** Joules only settle on COMPLETED state (atomic settlement). CNP contract must track state.
- **MCP Bridge enhances Agent Discovery:** Wraps MCP tools as capabilities in Agent Card, making them discoverable.
- **Broker Transports conflict with Direct Transport:** A message uses either broker OR direct HTTP/WS, not both. Design for pluggable transport.
- **Observability enhances everything:** Adds overhead; make it lazy-load so core remains lightweight.

## MVP Definition

### Launch With (v0.1.0)

Minimum viable product — what's needed to validate the concept.

- [ ] **Agent Identity (did:key)** — Core to AgenLang's value proposition; enables all signing/verification
- [ ] **Message Schema (FIPA-ACL)** — Structured communication foundation; defines envelope + performatives
- [ ] **RFC 8785 Signing/Verification** — Cross-language compatibility; critical for interoperability
- [ ] **HTTP Transport** — Basic communication; POST to `/.well-known/agent-card.json` + `/agenlang`
- [ ] **Agent Card Discovery** — Dynamic capability advertisement; `/.well-known/agent-card.json` endpoint
- [ ] **BaseAgent Skeleton** — Wires identity, transport, SQLite persistence, asyncio loop together

### Add After Validation (v0.2.0)

Features to add once core is working.

- [ ] **WebSocket/SSE Transport** — Streaming for long-running tasks; enterprise UX requirement
- [ ] **Negotiation (CNP Basic)** — CFP → PROPOSE → ACCEPT/REJECT; enables task allocation
- [ ] **JouleMeter Instrumentation** — Token counting (tiktoken), compute timing, SER generation
- [ ] **Task Lifecycle State Machine** — PENDING → RUNNING → COMPLETED/FAILED/CANCELLED
- [ ] **Nonce Sentry** — Replay protection with TTL-based pruning

### Add After Validation (v0.3.0)

Features for production hardening.

- [ ] **Negotiation (CNP with Haggling)** — Multi-round PROPOSE ↔ PROPOSE; price/term discovery
- [ ] **Internal Ledger** — Double-entry Joule tracking; atomic settlement on COMPLETED
- [ ] **MCP Bridge** — Consume external MCP servers as AgenLang agents
- [ ] **Multi-Hop Traceability** — trace_id + parent_contract_id for audit chains

### Future Consideration (v1.0+)

Features to defer until product-market fit is established.

- [ ] **Broker Transports (NATS/Redis)** — Enterprise reliability; only if enterprise customers demand
- [ ] **OpenTelemetry Observability** — Production ops visibility; only if needed
- [ ] **Key Rotation** — Long-lived agent identity management; defer until key compromise scenario occurs
- [ ] **x402 Integration** — External payment protocol bridge; complementary to Joules
- [ ] **DHT/Decentralized Discovery** — Beyond mDNS; only if scale demands

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| Agent Identity (DID) | HIGH | HIGH | P1 |
| Message Schema + Signing | HIGH | MEDIUM | P1 |
| HTTP Transport | HIGH | LOW | P1 |
| Agent Card Discovery | HIGH | LOW | P1 |
| BaseAgent Skeleton | HIGH | MEDIUM | P1 |
| WebSocket/SSE | MEDIUM | MEDIUM | P2 |
| CNP Negotiation | HIGH | MEDIUM | P2 |
| JouleMeter | HIGH | HIGH | P2 |
| Task Lifecycle | HIGH | MEDIUM | P2 |
| Nonce Sentry | MEDIUM | MEDIUM | P2 |
| MCP Bridge | MEDIUM | MEDIUM | P3 |
| Broker Transports | MEDIUM | MEDIUM | P3 |
| Observability | MEDIUM | MEDIUM | P3 |
| Key Rotation | LOW | HIGH | P3 |

**Priority key:**
- P1: Must have for launch
- P2: Should have, add when possible
- P3: Nice to have, future consideration

## Competitor Feature Analysis

| Feature | Google A2A | Anthropic MCP | IBM ACP | AgenLang (Our Approach) |
|---------|------------|---------------|---------|------------------------|
| **Identity** | OAuth2/API keys | API keys | Not specified | DID:key (Ed25519) — cryptographic, portable |
| **Discovery** | Agent Cards (JSON) | Tool manifest | Not specified | Agent Cards (signed YAML) — cryptographically verifiable |
| **Message Format** | JSON-RPC 2.0 | JSON (MCP spec) | Not specified | Signed YAML with FIPA-ACL — structured negotiation |
| **Negotiation** | Task submit/response | Tool calling | Not specified | CNP with haggling — multi-round negotiation |
| **Streaming** | SSE | N/A | Not specified | SSE/WebSocket — real-time updates |
| **Payments** | None | None | None | JouleMeter + SER — unique differentiator |
| **Signing** | Not specified | None | None | RFC 8785 canonicalization — cross-language |
| **MCP Integration** | N/A | N/A | None | Bridge (consume MCP) — extends ecosystem |
| **Transport** | HTTP/WebSocket | stdio | Not specified | HTTP/WS + optional brokers |
| **Observability** | External (enterprise) | None | Not specified | Optional OpenTelemetry — lazy-load |

### Key Insights from Competitor Analysis

1. **No competitor has cryptographic identity:** DID-based identity is AgenLang's strongest differentiator. Most use API keys or OAuth2.
2. **No competitor has built-in payments:** Joule metering is unique. x402 (Coinbase) is complementary, not competing.
3. **Google A2A leads on enterprise features:** Streaming, push notifications, Agent Cards. AgenLang matches these while adding cryptographic verification.
4. **MCP is tool-focused, not agent-focused:** MCP connects agents to tools; A2A connects agents to agents. AgenLang bridges both (consumes MCP, speaks A2A).
5. **FIPA-ACL is underutilized:** Most modern protocols reinvent negotiation. AgenLang leverages 40+ years of distributed systems research.

## Sources

- Google A2A Protocol Specification (2025) — agent cards, task lifecycle, streaming
- Anthropic MCP Specification (2024-2025) — tool integration pattern
- Gravitee State of AI Agent Security 2026 Report — 919 respondents, 22% have agent identity
- Zylos Research: Agent-to-Agent Communication Protocol Standards (2026) — A2A, MCP, ACP, ANP comparison
- Contract Net Protocol (Smith, 1980) — FIPA-ACL foundation, CNP state machine
- RFC 8785 — JSON Canonicalization Scheme for cross-language signatures
- x402 Protocol (Coinbase, 2025) — HTTP 402 payment protocol for agents
- Agentokratia (2026) — Agentic commerce settlement protocol
- OpenAgents Blog: Agent Identity (2026) — DID-based cryptographic identity

---

*Feature research for: AgenLang Core Protocol (A2A Communication)*
*Researched: 2026-03-11*
