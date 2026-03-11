# Project Research Summary

**Project:** AgenLang Core Protocol
**Domain:** Agent-to-Agent (A2A) Communication Protocols
**Researched:** 2026-03-11
**Confidence:** HIGH

## Executive Summary

AgenLang is a Python library for Agent-to-Agent (A2A) communication with cryptographic DID-based identity, async transport (HTTP/WebSocket), and Joule-based metering for agent commerce. The research establishes a clear path: build security-first with Ed25519 identity and RFC 8785 canonicalization before any transport, then layer on negotiation (Contract Net Protocol) and economic settlement (Signed Execution Records).

The recommended approach prioritizes cryptographic identity as the foundation—DID:key with Ed25519 provides verifiable, portable identity without centralized PKI. This is AgenLang's strongest differentiator against Google A2A (OAuth2/API keys) and Anthropic MCP (API keys only). The Joule-based metering system with SER generation is unique in the market and enables receiver-validatable micro-payments without trusted third parties.

Key risks center on security ordering (signature verification must happen BEFORE content parsing), economic atomicity (settlement only on COMPLETED state), and cascade failures in agent networks. The roadmap should follow the architectural dependency chain: identity → schema → core → negotiation → economy → bridge.

## Key Findings

### Recommended Stack

The recommended stack is Python >=3.10 with FastAPI for the async web framework. Core cryptography uses `cryptography` (>=44.0.0) for Ed25519 key operations and `rfc8785` (>=0.1.4) for deterministic JSON canonicalization—critical for cross-language signature compatibility. Pydantic v2 (>=2.12.0) handles schema validation with 6-10x performance improvements over v1.

Async transport relies on `httpx` (>=0.28.0) for unified sync/async HTTP, `websockets` (>=16.0) for streaming, and `aiosqlite` (>=0.22.0) for non-blocking SQLite operations. Token counting uses `tiktoken` (3-6x faster than alternatives). Optional extras include NATS/Redis brokers for enterprise deployments and OpenTelemetry for observability—both lazy-loaded to keep core lightweight.

**Core technologies:**
- **cryptography (>=44.0.0):** Ed25519 signing/verification—industry standard used by AWS, better ecosystem than pynacl
- **rfc8785 (>=0.1.4):** RFC 8785 JSON canonicalization—pure Python, ensures cross-language signature compatibility
- **pydantic (>=2.12.0):** Data validation with Python type hints—the standard, 6-10x faster than v1
- **httpx (>=0.28.0):** Async HTTP client/server—unified sync/async API, native FastAPI integration
- **fastapi (>=0.134.0):** Web framework—highest performance Python web framework, native async
- **aiosqlite (>=0.22.0):** Async SQLite—essential for non-blocking DB in async message loops

### Expected Features

**Must have (table stakes):**
- **Agent Discovery** — Agent Cards at `/.well-known/agent-card.json` is the emerging standard; mDNS for local discovery
- **Message Transport (HTTP/WebSocket)** — JSON-RPC 2.0 dominant pattern; HTTP POST for request-response, WebSocket/SSE for streaming
- **Task Lifecycle Management** — States: SUBMITTED → WORKING → INPUT_REQUIRED → COMPLETED/FAILED/CANCELLED
- **Authentication & Authorization** — DID-based identity with Ed25519 signatures; 22% of teams treat agents as independent identities
- **TLS/HTTPS Enforcement** — Security baseline; Google A2A mandates HTTPS; reject plaintext at startup
- **Message Schema/Format** — FIPA-ACL performatives for structured negotiation
- **Capability Advertisement** — Agent Cards declare capabilities with task identifiers and input/output schemas

**Should have (competitive):**
- **Cryptographic DID-Based Identity** — Verifiable, portable identity without centralized PKI; AgenLang's core strength; only ~22% of A2A implementations have this
- **Joule-Based Metering & Settlement** — Receiver-validatable micro-payments; unique to AgenLang; uses SER with prompt/completion hashes
- **Contract Net Protocol (CNP) with Haggling** — Multi-round negotiation enables price/term discovery; FIPA-ACL: CFP → PROPOSE ↔ PROPOSE → ACCEPT/REJECT
- **Signed Execution Records (SER)** — Cryptographic proof of work done; contains token breakdown, compute seconds, weights, hashes, signature
- **Multi-Hop Traceability** — Full audit trail across agent chains (trace_id + parent_contract_id); enables billing aggregation
- **MCP Bridge** — Consume external MCP servers as AgenLang agents; extends ecosystem without protocol confusion

**Defer (v2+):**
- **Broker Transports (NATS/Redis)** — Enterprise reliability; only if enterprise customers demand
- **OpenTelemetry Observability** — Production ops visibility; only if needed
- **Key Rotation** — Long-lived agent identity management; defer until key compromise scenario occurs
- **x402 Integration** — External payment protocol bridge; complementary to Joules

### Architecture Approach

The architecture follows a layered pattern: Application Layer (BaseAgent with handler loops) → Protocol Layer (Identity, Schema, Negotiation, Economy) → Transport Layer (HTTP/WebSocket/mDNS/Brokers) → Persistence Layer (SQLite for contracts, SERs, cards).

**Major components:**
1. **Identity Module (identity.py)** — DID:key generation, Ed25519 signing/verification, key storage; built FIRST as all other modules depend on cryptographic identity
2. **Schema Module (schema.py)** — Pydantic models for envelope + FIPA-ACL performatives; second priority as defines message contract
3. **Negotiation (negotiation.py)** — CNP state machine with haggling support; builds on contracts for task allocation
4. **Economy (economy.py)** — JouleMeter context manager, SER generation, ledger management; integrates with negotiation for atomic settlement
5. **Transport (transport/)** — Abstract interface with HTTP, WebSocket, and optional broker implementations; pluggable design
6. **Bridge (bridge.py)** — MCP client adapter; wraps MCP tools as stateless AgenLang agents

Key architectural patterns: **Signed Message Envelope** (Ed25519 over RFC 8785 canonicalized content), **Agent Card Discovery** (self-describing documents with DID, capabilities, pricing), **CNP with Haggling** (multi-round proposal negotiation), **Joule-Based Metering** (weighted token/compute formula with SER), **Async Message Loop with Nonce Sentry** (replay protection via SQLite with TTL pruning).

### Critical Pitfalls

1. **Signature Verification Race Conditions** — Verify Ed25519 signature BEFORE any Pydantic model instantiation or content parsing; implement "Lazy Payload Validation" to prevent memory exhaustion attacks
2. **Replay Attack Vulnerability** — Implement Nonce Sentry with cryptographically random nonces, SQLite storage with 24h TTL pruning, async-buffered writes to avoid bottlenecking
3. **Negotiation State Machine Deadlocks** — Enforce TTL on all proposals, implement max-round limits (5 rounds default), use explicit state transition validation
4. **Economic Settlement Failures** — Atomic settlement ONLY on COMPLETED state, double-entry ledger, integer-based Joule calculations, cryptographically signed SER
5. **Cascade Failures** — Implement circuit breakers, async timeouts with fallback, trace_id propagation, graceful refusal instead of crashes

## Implications for Roadmap

Based on research, suggested phase structure:

### Phase 1: Protocol Foundation (v0.1.0)
**Rationale:** Security-first—identity and schema are the foundation all other modules depend on. The "Iron Rule": do not build transport until JCS-signing is 100% verified.

**Delivers:**
- Agent Identity (did:key) with Ed25519 key generation and storage
- Message Schema (FIPA-ACL) with Pydantic validation
- RFC 8785 canonicalization and signing/verification pipeline
- HTTP Transport (basic POST to `/.well-known/agent-card.json` + `/agenlang`)
- Agent Card Discovery endpoint
- BaseAgent skeleton with asyncio event loop

**Addresses:** All table stakes features; MVP requirements
**Avoids:** Signature verification race conditions (verify BEFORE parsing), plaintext transport acceptance (reject HTTP at startup), blocking I/O (strict async-only policy)

### Phase 2: Exchange & Economy (v0.2.0)
**Rationale:** Core exchange and economic features require foundation to be stable. Negotiation and economy have complex state machine requirements that need proven identity/schema.

**Delivers:**
- WebSocket/SSE Transport for streaming
- CNP Negotiation ( CFP → PROPOSE → ACCEPT/REJECT basic flow)
- CNP with Haggling (multi-round PROPOSE ↔ PROPOSE)
- JouleMeter instrumentation with tiktoken
- Task Lifecycle state machine
- Nonce Sentry (replay protection)
- Internal Ledger (double-entry tracking)

**Addresses:** Differentiators—CNP negotiation, JouleMeter, SER generation
**Avoids:** Negotiation deadlocks (TTL/max-rounds), economic settlement failures (atomic on COMPLETED), double-spending (double-entry ledger + SER)

### Phase 3: Bridge & Polish (v0.3.0)
**Rationale:** MCP Bridge extends ecosystem; production hardening features complete the v1.0 story.

**Delivers:**
- MCP Bridge (consume external MCP servers as AgenLang agents)
- Multi-Hop Traceability (trace_id + parent_contract_id for audit chains)
- Broker Transports (NATS/Redis) as optional extras
- OpenTelemetry Observability (lazy-loaded)
- CLI tools and documentation

**Addresses:** MCP Bridge (differentiator), Broker transports, Observability
**Avoids:** Cascade failures (circuit breakers), graceful degradation when remote agents unavailable

### Phase Ordering Rationale

- **Identity first:** All security depends on cryptographic identity foundation—verify signatures before any content parsing
- **Schema second:** Defines message contract all agents must follow; Pydantic provides validation before processing
- **Core third:** Wires identity, schema, transport, persistence together; BaseAgent is the integration point
- **Negotiation fourth:** Builds on contracts to implement CNP with haggling support
- **Economy fifth:** Integrates with negotiation for atomic settlement on task completion (ONLY on COMPLETED state)
- **Bridge last:** Consumes MCP servers as AgenLang agents; extends without protocol confusion

The dependency chain from ARCHITECTURE.md maps directly to phase structure: Phase 0 (Protocol Skeleton) → Phase 1 (Foundation) → Phase 2 (Exchange & Economy) → Phase 3 (Bridge & Polish).

### Research Flags

Phases likely needing deeper research during planning:
- **Phase 2 (Economy):** Complex state machine integration; needs detailed API design for JouleMeter weights and SER validation
- **Phase 3 (MCP Bridge):** MCP protocol specifics; official SDK usage patterns; edge cases in tool-to-agent translation

Phases with standard patterns (skip research-phase):
- **Phase 1 (Identity/Schema):** Well-documented RFC 8785, Ed25519, Pydantic v2 patterns
- **Phase 1 (HTTP Transport):** Standard FastAPI patterns, well-documented

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | Official library documentation, version requirements verified against PyPI, alternatives thoroughly considered |
| Features | HIGH | Competitor analysis (Google A2A, Anthropic MCP, IBM ACP), industry surveys (Gravitee 2026), domain research |
| Architecture | HIGH | Standard A2A patterns, FIPA-ACL foundation, architectural anti-patterns well-documented in industry |
| Pitfalls | HIGH | Security research (arXiv 2025), OWASP classifications, production failure pattern analysis |

**Overall confidence:** HIGH

The research draws from official specifications (RFC 8785, W3C DID, FIPA-ACL), industry surveys (Gravitee 2026 with 919 respondents), and security analyses (arXiv, OWASP). All major components have clear dependencies and build order rationale.

### Gaps to Address

- **DID:key limitations:** did:key method does NOT support key rotation or deactivation—document this limitation for high-security deployments; plan for future migration to DID methods supporting rotation
- **Token counting variance:** tiktoken produces different counts across languages—need tolerance thresholds in SER validation
- **Enterprise broker requirements:** NATS/Redis broker patterns need validation against actual enterprise customer requirements before Phase 3

## Sources

### Primary (HIGH confidence)
- **cryptography library:** https://cryptography.io/en/latest/hazmat/primitives/asymmetric/ed25519.html
- **rfc8785 (PyPI):** https://pypi.org/project/rfc8785/
- **pydantic v2:** https://pypi.org/project/pydantic/
- **RFC 8785 (JSON Canonicalization):** https://datatracker.ietf.org/doc/html/rfc8785
- **DID:key Specification:** https://w3c-ccg.github.io/did-method-key/
- **FIPA Contract Net Protocol:** http://www.fipa.org/specs/fipa00029/SC00029H.pdf

### Secondary (MEDIUM confidence)
- **Google A2A Protocol:** https://a2aprotocol.ai/docs/guide/a2a-protocol-specification-python
- **Gravitee State of AI Agent Security 2026 Report:** 919 respondents, 22% have agent identity
- **Security Analysis of Agentic AI Communication Protocols (arXiv 2025):** Empirical security evaluation
- **Cascading Failures in Agentic AI: OWASP ASI08 Guide (2026):** Cascade failure patterns

### Tertiary (LOW confidence)
- **NegMAS (Negotiation Multi-Agent System):** https://negmas.readthedocs.io/ — promising but needs validation
- **Agentokratia (2026):** Agentic commerce settlement protocol—early stage, needs validation

---
*Research completed: 2026-03-11*
*Ready for roadmap: yes*
