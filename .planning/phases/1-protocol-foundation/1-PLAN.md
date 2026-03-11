# Phase 1: Protocol Foundation — Plan

**Objective:** Secure agent communication with DID identity, message schema, HTTP transport, and agent discovery

**Dependencies:** Phase 0 (Setup)

**Requirements covered:** ID-01, ID-02, ID-03, ID-04, ID-05, SCH-01, SCH-02, SCH-03, SCH-04, SCH-05, SCH-06, TRN-01, TRN-02, TRN-03, TRN-04, TRN-05, COR-01, COR-02, COR-03, COR-04, COR-05, COR-06, COR-07, COR-08, COR-09, CTR-01, CTR-02, DSC-01, DSC-02, DSC-03, DSC-04, DSC-05

---

## Plan 1: Identity Module (ID-01 to ID-05)

### Tasks
- Implement Ed25519 key pair generation
- Implement did:key creation (multicodec 0xed01 + multibase base58btc)
- Implement key storage with OS keyring or encrypted file fallback
- Implement RFC 8785 canonicalization for signing
- Implement message signing and verification

### Implementation Details
- Use `cryptography` library for Ed25519 operations
- Use `rfc8785` for JSON canonicalization
- Use `keyring` for secure key storage
- DID format: `did:key:z6Mk...`

---

## Plan 2: Schema Module (SCH-01 to SCH-06)

### Tasks
- Implement full MessageEnvelope Pydantic model
- Implement all FIPA-ACL performatives
- Implement ProtocolMeta for version negotiation
- Implement payload_encoding and media_type fields
- Implement Base64 payload size limit (10MB)
- Implement ErrorCode enum registry

### Implementation Details
- Envelope fields: protocol_version, message_id, sender_did, receiver_did, nonce, timestamp, expires_at, trace_id, parent_contract_id, conversation_id, reply_with, in_reply_to, signature
- Performatives: REQUEST, PROPOSE, ACCEPT-PROPOSAL, REJECT-PROPOSAL, INFORM, AGREE, REFUSE, FAILURE, CANCEL, CFP, NOT_UNDERSTOOD

---

## Plan 3: Transport Module (TRN-01 to TRN-05)

### Tasks
- Implement HTTP POST endpoint at /agenlang
- Implement /.well-known/agent-card.json static endpoint
- Enforce HTTPS - reject plaintext HTTP at startup
- Implement retry with exponential backoff
- Implement message deduplication via nonce + message_id

### Implementation Details
- Use FastAPI for HTTP server
- Use httpx for HTTP client
- Store received nonces in SQLite for deduplication

---

## Plan 4: Core Agent (COR-01 to COR-09)

### Tasks
- Implement BaseAgent abstract class
- Implement SQLite persistence at ~/.agenlang/agents/<agent-id>/session.db
- Implement asyncio message receive/send loop
- Implement lifecycle methods: start, stop, health
- Implement event handlers: on_message, on_request, on_propose, on_inform
- Implement Nonce Sentry for replay attack prevention
- Implement 24-hour TTL nonce pruning
- Implement async-buffered nonce writer
- Implement optional trusted_dids filter

---

## Plan 5: Contracts & Discovery (CTR-01, CTR-02, DSC-01 to DSC-05)

### Tasks
- Implement Contract state machine (PENDING, RUNNING, COMPLETED, FAILED, CANCELLED)
- Implement Contract metadata storage
- Implement Agent Card schema
- Implement HTTP-based discovery via /.well-known/agent-card.json
- Implement mDNS/Zeroconf local discovery
- Implement Agent Card caching with TTL
- Implement cryptographically signed Agent Cards

---

1. Agent can generate Ed25519## Success Criteria

 key pair and create did:key identifier
2. Agent can sign messages using RFC 8785 canonicalized JSON
3. Agent can verify incoming message signatures
4. Agent can send/receive signed YAML messages via HTTP POST
5. Agent Card is served at /.well-known/agent-card.json
6. Plaintext HTTP is rejected at startup
7. Message deduplication works via nonce + message_id
8. BaseAgent can start, run message loop, and handle events
9. Nonce Sentry prevents replay attacks with 24h TTL pruning
10. mDNS local discovery finds agents on local network
