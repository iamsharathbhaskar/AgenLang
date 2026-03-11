# Requirements: AgenLang Core Protocol (Revised)

**Defined:** 2026-03-12
**Core Value:** A semantics layer on top of A2A protocol — adding DID identity and Joule-based metering to Google's A2A

## v1 Requirements

### Cleanup

- [ ] **CLEANUP-01**: Delete `src/agenlang/core.py` (old BaseAgent framework)
- [ ] **CLEANUP-02**: Delete `src/agenlang/transport/` directory (replaced by A2A SDK)
- [ ] **CLEANUP-03**: Remove old test files referencing deleted code
- [ ] **CLEANUP-04**: Update `pyproject.toml` with new dependencies (google-a2a)

### Project Setup

- [ ] **SET-01**: pyproject.toml with src layout and google-a2a dependency
- [ ] **SET-02**: All dependencies install without version conflicts
- [ ] **SET-03**: Project can be imported (`import agenlang`)

### Identity

- [ ] **ID-01**: Agent can generate Ed25519 key pair and create did:key identifier
- [ ] **ID-02**: Agent can securely store private keys in OS keyring or encrypted file
- [ ] **ID-03**: Agent can sign messages using RFC 8785 canonicalized JSON
- [ ] **ID-04**: Agent can verify incoming message signatures
- [ ] **ID-05**: DID format follows multicodec prefix 0xed01 + multibase base58btc encoding

### Semantics (FIPA-ACL)

- [ ] **SCH-01**: Message envelope includes: message_id, sender_did, receiver_did, nonce, timestamp, trace_id, conversation_id, parent_contract_id
- [ ] **SCH-02**: Support all FIPA-ACL performatives: REQUEST, PROPOSE, ACCEPT-PROPOSAL, REJECT-PROPOSAL, INFORM, AGREE, REFUSE, FAILURE, CANCEL, CFP, NOT_UNDERSTOOD
- [ ] **SCH-03**: NOT_UNDERSTOOD includes protocol_meta with min_version and max_version
- [ ] **SCH-04**: Content supports payload_encoding and media_type fields for binary data
- [ ] **SCH-05**: Base64 payloads limited to 10 MB
- [ ] **SCH-06**: Error registry: ERR_CAPABILITY_MISMATCH, ERR_INSUFFICIENT_JOULES, ERR_PAYLOAD_TOO_LARGE, ERR_TASK_TIMEOUT, ERR_JOULE_VALIDATION_FAILED

### Client

- [ ] **CLI-01**: AgentClient class with .request(), .propose(), .accept(), .reject(), .inform() methods
- [ ] **CLI-02**: All client methods properly sign messages with DID key
- [ ] **CLI-03**: Client wraps A2A SDK for transport

### Economy

- [ ] **ECO-01**: JouleMeter as context manager and decorator
- [ ] **ECO-02**: Weighted formula: Joules = (PromptTokens × W1) + (CompletionTokens × W2) + (Compute_Seconds × W3)
- [ ] **ECO-03**: Token counting via tiktoken
- [ ] **ECO-04**: Signed Execution Record (SER) generation with cryptographic signature
- [ ] **ECO-05**: SER includes prompt_hash and completion_hash for receiver verification
- [ ] **ECO-06**: Graceful Divergence threshold (±5%) for token count validation
- [ ] **ECO-07**: Joule Garbage Collector reverts stale PENDING reservations after 30 minutes
- [ ] **ECO-08**: Atomic settlement only on COMPLETED contract state

### Negotiation

- [ ] **NEG-01**: Contract Net Protocol (CNP) state machine
- [ ] **NEG-02**: PROPOSE ↔ PROPOSE haggling rounds
- [ ] **NEG-03**: ACCEPT-PROPOSAL and REJECT-PROPOSAL handling
- [ ] **NEG-04**: TTL per proposal with auto CANCEL on expiration
- [ ] **NEG-05**: Max rounds limit enforcement

## v2 Requirements

- **A2A-STREAMING**: WebSocket and SSE support via A2A SDK
- **DISCOVERY-EXT**: Extended Agent Cards with DID and pricing fields
- **BRIDGE**: MCP Client adapter

## Out of Scope

| Feature | Reason |
|---------|--------|
| Custom HTTP transport | Using A2A SDK instead |
| BaseAgent framework | Simple client library approach |
| NATS/Redis brokers | Optional extras only |
| OpenTelemetry | Deferred to v2 |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| CLEANUP-01 | Phase 0 | Pending |
| CLEANUP-02 | Phase 0 | Pending |
| CLEANUP-03 | Phase 0 | Pending |
| CLEANUP-04 | Phase 0 | Pending |
| SET-01 | Phase 1 | Pending |
| SET-02 | Phase 1 | Pending |
| SET-03 | Phase 1 | Pending |
| ID-01 | Phase 2 | Pending |
| ID-02 | Phase 2 | Pending |
| ID-03 | Phase 2 | Pending |
| ID-04 | Phase 2 | Pending |
| ID-05 | Phase 2 | Pending |
| SCH-01 | Phase 2 | Pending |
| SCH-02 | Phase 2 | Pending |
| SCH-03 | Phase 2 | Pending |
| SCH-04 | Phase 2 | Pending |
| SCH-05 | Phase 2 | Pending |
| SCH-06 | Phase 2 | Pending |
| CLI-01 | Phase 3 | Pending |
| CLI-02 | Phase 3 | Pending |
| CLI-03 | Phase 3 | Pending |
| ECO-01 | Phase 4 | Pending |
| ECO-02 | Phase 4 | Pending |
| ECO-03 | Phase 4 | Pending |
| ECO-04 | Phase 4 | Pending |
| ECO-05 | Phase 4 | Pending |
| ECO-06 | Phase 4 | Pending |
| ECO-07 | Phase 4 | Pending |
| ECO-08 | Phase 4 | Pending |
| NEG-01 | Phase 4 | Pending |
| NEG-02 | Phase 4 | Pending |
| NEG-03 | Phase 4 | Pending |
| NEG-04 | Phase 4 | Pending |
| NEG-05 | Phase 4 | Pending |

**Coverage:**
- v31 total
- Mapped to phases1 requirements: : 31
- Unmapped: 0 ✓

---
*Requirements defined: 2026-03-12*
*Last updated: 2026-03-12 after architecture pivot*
