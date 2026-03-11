# Requirements: AgenLang Core Protocol

**Defined:** 2026-03-11
**Core Value:** A universal, secure protocol for agent-to-agent communication with cryptographically verified identity (DID), trustworthy negotiation, and transparent micro-settlements — enabling a decentralized agent economy.

## v1 Requirements

### Identity

- [ ] **ID-01**: Agent can generate Ed25519 key pair and create did:key identifier
- [ ] **ID-02**: Agent can securely store private keys in OS keyring or encrypted file
- [ ] **ID-03**: Agent can sign messages using RFC 8785 canonicalized JSON
- [ ] **ID-04**: Agent can verify incoming message signatures
- [ ] **ID-05**: DID format follows multicodec prefix 0xed01 + multibase base58btc encoding

### Schema

- [ ] **SCH-01**: Message envelope includes: protocol_version, message_id, sender_did, receiver_did, nonce, timestamp, expires_at, trace_id, parent_contract_id, conversation_id, reply_with, in_reply_to, signature
- [ ] **SCH-02**: Support all FIPA-ACL performatives: REQUEST, PROPOSE, ACCEPT-PROPOSAL, REJECT-PROPOSAL, INFORM, AGREE, REFUSE, FAILURE, CANCEL, CFP, NOT_UNDERSTOOD
- [ ] **SCH-03**: NOT_UNDERSTOOD includes protocol_meta with min_version and max_version for version negotiation
- [ ] **SCH-04**: Content supports payload_encoding and media_type fields for binary data
- [ ] **SCH-05**: Base64 payloads limited to 10 MB with NOT_UNDERSTOOD response on overflow
- [ ] **SCH-06**: Error registry enum includes: ERR_CAPABILITY_MISMATCH, ERR_INSUFFICIENT_JOULES, ERR_PAYLOAD_TOO_LARGE, ERR_TASK_TIMEOUT, ERR_JOULE_VALIDATION_FAILED

### Transport

- [ ] **TRN-01**: HTTP POST endpoint receives signed YAML messages at /agenlang
- [ ] **TRN-02**: Static /.well-known/agent-card.json serves signed Agent Card
- [ ] **TRN-03**: Reject plaintext HTTP at startup with ConfigurationError
- [ ] **TRN-04**: Implement retry with exponential backoff
- [ ] **TRN-05**: Message deduplication via nonce + message_id

### Core Agent

- [ ] **COR-01**: BaseAgent abstract class with identity, transport, SQLite persistence
- [ ] **COR-02**: SQLite database at ~/.agenlang/agents/<agent-id>/session.db
- [ ] **COR-03**: Asyncio message receive/send loop
- [ ] **COR-04**: Lifecycle methods: start, stop, health
- [ ] **COR-05**: Event handlers: on_message, on_request, on_propose, on_inform
- [ ] **COR-06**: Nonce Sentry checks incoming nonces against session.db
- [ ] **COR-07**: Automatic nonce pruning older than 24 hours (configurable TTL)
- [ ] **COR-08**: Async-buffered nonce writer using asyncio.Queue
- [ ] **COR-09**: Optional trusted_dids filter loaded from config

### Negotiation

- [ ] **NEG-01**: Contract Net Protocol (CNP) state machine
- [ ] **NEG-02**: PROPOSE ↔ PROPOSE haggling rounds
- [ ] **NEG-03**: ACCEPT-PROPOSAL and REJECT-PROPOSAL handling
- [ ] **NEG-04**: TTL per proposal with auto CANCEL on expiration
- [ ] **NEG-05**: Max rounds limit enforcement

### Economy

- [ ] **ECO-01**: JouleMeter as context manager and decorator
- [ ] **ECO-02**: Weighted formula: Joules = (PromptTokens × W1) + (CompletionTokens × W2) + (Compute_Seconds × W3)
- [ ] **ECO-03**: Token counting via tiktoken
- [ ] **ECO-04**: Signed Execution Record (SER) generation with cryptographic signature
- [ ] **ECO-05**: SER includes prompt_hash and completion_hash for receiver verification
- [ ] **ECO-06**: Graceful Divergence threshold (default ±5%) for token count validation
- [ ] **ECO-07**: Joule Garbage Collector reverts stale PENDING reservations after 30 minutes
- [ ] **ECO-08**: Atomic settlement only on COMPLETED contract state

### Bridge

- [ ] **BRD-01**: MCP Client adapter using official mcp package
- [ ] **BRD-02**: Wrap external MCP servers as stateless AgenLang agents
- [ ] **BRD-03**: Wrapped agents speak signed AgenLang YAML
- [ ] **BRD-04**: Wrapped agents participate in CNP negotiation
- [ ] **BRD-05**: Wrapped agents meter Joules and produce SERs

### Contracts

- [ ] **CTR-01**: Task lifecycle states: PENDING, RUNNING, COMPLETED, FAILED, CANCELLED
- [ ] **CTR-02**: Contract metadata storage
- [ ] **CTR-03**: Atomic settlement triggered on COMPLETED state only

### Discovery

- [ ] **DSC-01**: Agent Card schema with did, name, description, capabilities, transports
- [ ] **DSC-02**: HTTP-based discovery via /.well-known/agent-card.json
- [ ] **DSC-03**: mDNS/Zeroconf local network discovery
- [ ] **DSC-04**: Agent Card caching with TTL
- [ ] **DSC-05**: Cryptographically signed Agent Cards

### Project Setup

- [ ] **SET-01**: pyproject.toml with src layout
- [ ] **SET-02**: Core dependencies: pydantic, cryptography, rfc8785, aiosqlite, pyyaml, httpx, fastapi, websockets, zeroconf, tiktoken, structlog, mcp
- [ ] **SET-03**: Optional extras: brokers (nats-py, redis), observability (opentelemetry)
- [ ] **SET-04**: CLI entry point: agenlang CLI with agent start, discover, inspect commands

## v2 Requirements

### Transport

- **TRN-06**: WebSocket and SSE support for streaming
- **TRN-07**: NATS broker transport
- **TRN-08**: Redis broker transport

### Observability

- **OBS-01**: W3C Trace-Context integration
- **OBS-02**: OpenTelemetry integration

### Advanced Features

- **ADV-01**: DHT-based discovery for scalable peer lookup
- **ADV-02**: DID rotation support
- **ADV-03**: x402 fiat stablecoin payment integration

## Out of Scope

| Feature | Reason |
|---------|--------|
| Agent-as-MCP-server | AgenLang is the primary protocol; only consumes MCP |
| Plaintext HTTP/WSS | Security by default is mandatory for enterprise adoption |
| Blocking I/O | Async-only architecture required for scalability |
| NATS/Redis in core | Optional extras only to keep core lightweight |
| gRPC transport | HTTP/WebSocket sufficient for v1 |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| SET-01 | Phase 0 | Pending |
| SET-02 | Phase 0 | Pending |
| SET-03 | Phase 0 | Pending |
| SET-04 | Phase 3 | Pending |
| ID-01 | Phase 1 | Pending |
| ID-02 | Phase 1 | Pending |
| ID-03 | Phase 1 | Pending |
| ID-04 | Phase 1 | Pending |
| ID-05 | Phase 1 | Pending |
| SCH-01 | Phase 1 | Pending |
| SCH-02 | Phase 1 | Pending |
| SCH-03 | Phase 1 | Pending |
| SCH-04 | Phase 1 | Pending |
| SCH-05 | Phase 1 | Pending |
| SCH-06 | Phase 1 | Pending |
| TRN-01 | Phase 1 | Pending |
| TRN-02 | Phase 1 | Pending |
| TRN-03 | Phase 1 | Pending |
| TRN-04 | Phase 1 | Pending |
| TRN-05 | Phase 1 | Pending |
| COR-01 | Phase 1 | Pending |
| COR-02 | Phase 1 | Pending |
| COR-03 | Phase 1 | Pending |
| COR-04 | Phase 1 | Pending |
| COR-05 | Phase 1 | Pending |
| COR-06 | Phase 1 | Pending |
| COR-07 | Phase 1 | Pending |
| COR-08 | Phase 1 | Pending |
| COR-09 | Phase 1 | Pending |
| CTR-01 | Phase 1 | Pending |
| CTR-02 | Phase 1 | Pending |
| CTR-03 | Phase 2 | Pending |
| DSC-01 | Phase 1 | Pending |
| DSC-02 | Phase 1 | Pending |
| DSC-03 | Phase 1 | Pending |
| DSC-04 | Phase 1 | Pending |
| DSC-05 | Phase 1 | Pending |
| NEG-01 | Phase 2 | Pending |
| NEG-02 | Phase 2 | Pending |
| NEG-03 | Phase 2 | Pending |
| NEG 2 | Pending-04 | Phase |
| NEG-05 | Phase 2 | Pending |
| ECO-01 | Phase 2 | Pending |
| ECO-02 | Phase 2 | Pending |
| ECO-03 | Phase 2 | Pending |
| ECO-04 | Phase 2 | Pending |
| ECO-05 | Phase 2 | Pending |
| ECO-06 | Phase 2 | Pending |
| ECO-07 | Phase 2 | Pending |
| ECO-08 | Phase 2 | Pending |
| BRD-01 | Phase 3 | Pending |
| BRD-02 | Phase 3 | Pending |
| BRD-03 | Phase 3 | Pending |
| BRD-04 | Phase 3 | Pending |
| BRD-05 | Phase 3 | Pending |

**Coverage:**
- v1 requirements: 55 total
- Mapped to phases: 55
- Unmapped: 0 ✓

---
*Requirements defined: 2026-03-11*
*Last updated: 2026-03-11 after initial definition*
