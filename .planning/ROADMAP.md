# AgenLang Roadmap

**Project:** AgenLang Core Protocol  
**Generated:** 2026-03-11  
**Granularity:** Coarse  
**Phases:** 4

## Phases

- [ ] **Phase 0: Setup** - Project scaffolding, pyproject.toml, dependencies
- [ ] **Phase 1: Protocol Foundation** - Identity, Schema, Transport, Core Agent, Discovery
- [ ] **Phase 2: Exchange & Economy** - CNP Negotiation, JouleMeter, Contracts, Settlement
- [ ] **Phase 3: Bridge & CLI** - MCP Bridge, CLI tools, Polish

---

## Phase Details

### Phase 0: Setup

**Goal:** Project scaffolding with src layout, dependencies, and CLI entry point

**Depends on:** Nothing (first phase)

**Requirements:** SET-01, SET-02, SET-03, SET-04

**Success Criteria** (what must be TRUE):
1. `pyproject.toml` exists with src layout and all core dependencies
2. All dependencies install without version conflicts
3. CLI entry point `agenlang` is functional
4. Project can be imported without errors (`import agenlang`)

**Plans:** TBD

---

### Phase 1: Protocol Foundation

**Goal:** Secure agent communication with DID identity, message schema, HTTP transport, and agent discovery

**Depends on:** Phase 0

**Requirements:** ID-01, ID-02, ID-03, ID-04, ID-05, SCH-01, SCH-02, SCH-03, SCH-04, SCH-05, SCH-06, TRN-01, TRN-02, TRN-03, TRN-04, TRN-05, COR-01, COR-02, COR-03, COR-04, COR-05, COR-06, COR-07, COR-08, COR-09, CTR-01, CTR-02, DSC-01, DSC-02, DSC-03, DSC-04, DSC-05

**Success Criteria** (what must be TRUE):
1. Agent can generate Ed25519 key pair and create did:key identifier
2. Agent can sign messages using RFC 8785 canonicalized JSON
3. Agent can verify incoming message signatures
4. Agent can send/receive signed YAML messages via HTTP POST
5. Agent Card is served at /.well-known/agent-card.json
6. Plaintext HTTP is rejected at startup
7. Message deduplication works via nonce + message_id
8. BaseAgent can start, run message loop, and handle events
9. Nonce Sentry prevents replay attacks with 24h TTL pruning
10. mDNS local discovery finds agents on local network

**Plans:** TBD

---

### Phase 2: Exchange & Economy

**Goal:** Multi-round CNP negotiation with Joule-based metering and atomic settlement

**Depends on:** Phase 1

**Requirements:** NEG-01, NEG-02, NEG-03, NEG-04, NEG-05, ECO-01, ECO-02, ECO-03, ECO-04, ECO-05, ECO-06, ECO-07, ECO-08, CTR-03

**Success Criteria** (what must be TRUE):
1. CNP state machine handles CFP → PROPOSE → ACCEPT/REJECT flow
2. Multi-round PROPOSE ↔ PROPOSE haggling works with max-rounds limit
3. TTL per proposal triggers auto CANCEL on expiration
4. JouleMeter correctly calculates Joules using weighted formula
5. Token counting via tiktoken produces consistent counts
6. Signed Execution Record (SER) generated with all required fields
7. Graceful divergence threshold (±5%) validates token counts
8. Joule Garbage Collector reverts stale PENDING reservations after 30 minutes
9. Atomic settlement occurs ONLY on COMPLETED contract state

**Plans:** TBD

---

### Phase 3: Bridge & CLI

**Goal:** MCP Bridge for consuming external servers, CLI tools, production polish

**Depends on:** Phase 2

**Requirements:** BRD-01, BRD-02, BRD-03, BRD-04, BRD-05

**Success Criteria** (what must be TRUE):
1. MCP Client adapter can connect to external MCP servers
2. External MCP servers wrapped as stateless AgenLang agents
3. Wrapped agents speak signed AgenLang YAML
4. Wrapped agents participate in CNP negotiation
5. Wrapped agents meter Joules and produce SERs

**Plans:** TBD

---

## Progress Table

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 0. Setup | 0/1 | Not started | - |
| 1. Protocol Foundation | 0/1 | Not started | - |
| 2. Exchange & Economy | 0/1 | Not started | - |
| 3. Bridge & CLI | 0/1 | Not started | - |

---

## Coverage Map

```
SET-01 → Phase 0
SET-02 → Phase 0
SET-03 → Phase 0
SET-04 → Phase 3

ID-01 → Phase 1
ID-02 → Phase 1
ID-03 → Phase 1
ID-04 → Phase 1
ID-05 → Phase 1

SCH-01 → Phase 1
SCH-02 → Phase 1
SCH-03 → Phase 1
SCH-04 → Phase 1
SCH-05 → Phase 1
SCH-06 → Phase 1

TRN-01 → Phase 1
TRN-02 → Phase 1
TRN-03 → Phase 1
TRN-04 → Phase 1
TRN-05 → Phase 1

COR-01 → Phase 1
COR-02 → Phase 1
COR-03 → Phase 1
COR-04 → Phase 1
COR-05 → Phase 1
COR-06 → Phase 1
COR-07 → Phase 1
COR-08 → Phase 1
COR-09 → Phase 1

CTR-01 → Phase 1
CTR-02 → Phase 1
CTR-03 → Phase 2

DSC-01 → Phase 1
DSC-02 → Phase 1
DSC-03 → Phase 1
DSC-04 → Phase 1
DSC-05 → Phase 1

NEG-01 → Phase 2
NEG-02 → Phase 2
NEG-03 → Phase 2
NEG-04 → Phase 2
NEG-05 → Phase 2

ECO-01 → Phase 2
ECO-02 → Phase 2
ECO-03 → Phase 2
ECO-04 → Phase 2
ECO-05 → Phase 2
ECO-06 → Phase 2
ECO-07 → Phase 2
ECO-08 → Phase 2

BRD-01 → Phase 3
BRD-02 → Phase 3
BRD-03 → Phase 3
BRD-04 → Phase 3
BRD-05 → Phase 3
```

---

*Roadmap generated: 2026-03-11*
