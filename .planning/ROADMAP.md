# AgenLang Roadmap

**Project:** AgenLang Core Protocol (Revised - A2A-Based)  
**Generated:** 2026-03-12  
**Granularity:** Coarse  
**Phases:** 5

## Phases

- [ ] **Phase 0: Cleanup** - Remove old implementation artifacts
- [ ] **Phase 1: Scaffolding** - Project setup, dependencies, A2A integration
- [ ] **Phase 2: Identity & Semantics** - DID:key, FIPA-ACL, RFC 8785 signing
- [ ] **Phase 3: Client Implementation** - Simple AgentClient class
- [ ] **Phase 4: Economy** - JouleMeter, SER, CNP negotiation

---

## Phase Details

### Phase 0: Cleanup

**Goal:** Remove old implementation artifacts that don't fit the new A2A-based architecture

**Depends on:** Nothing

**Success Criteria** (what must be TRUE):
1. Delete `src/agenlang/core.py` (old BaseAgent framework)
2. Delete `src/agenlang/transport/` (replaced by A2A SDK)
3. Clean up old test files that reference deleted code
4. Keep `identity.py`, `schema.py` (will be reused)
5. Keep `pyproject.toml` (update dependencies)

**Plans:** 1 plan

---

### Phase 1: Scaffolding

**Goal:** Set up project dependencies with A2A integration

**Depends on:** Phase 0

**Requirements:** SET-01, SET-02, SET-03

**Success Criteria** (what must be TRUE):
1. `pyproject.toml` includes `google-a2a` dependency
2. All dependencies install without version conflicts
3. Project can import `from agenlang import AgentClient` (stub)
4. A2A SDK is properly integrated

**Plans:** TBD

---

### Phase 2: Identity & Semantics

**Goal:** DID:key identity and FIPA-ACL semantics layer

**Depends on:** Phase 1

**Requirements:** ID-01, ID-02, ID-03, ID-04, ID-05, SCH-01, SCH-02, SCH-03, SCH-04, SCH-05, SCH-06

**Success Criteria** (what must be TRUE):
1. Agent can generate Ed25519 key pair and create did:key identifier
2. Agent can sign messages using RFC 8785 canonicalized JSON
3. Agent can verify incoming message signatures
4. FIPA-ACL performatives properly map to A2A messages
5. Error codes properly formatted in responses

**Plans:** TBD

---

### Phase 3: Client Implementation

**Goal:** Simple AgentClient class that wraps A2A with DID identity

**Depends on:** Phase 2

**Requirements:** CLI-01, CLI-02, CLI-03

**Success Criteria** (what must be TRUE):
1. `AgentClient.request()` sends REQUEST performative via A2A
2. `AgentClient.propose()` sends PROPOSE performative
3. `AgentClient.accept()` / `AgentClient.reject()` for negotiation
4. `AgentClient.inform()` sends INFORM performative
5. All methods properly sign messages with DID key

**Plans:** TBD

---

### Phase 4: Economy

**Goal:** Joule-based metering and CNP negotiation

**Depends on:** Phase 3

**Requirements:** ECO-01, ECO-02, ECO-03, ECO-04, ECO-05, ECO-06, ECO-07, ECO-08, NEG-01, NEG-02, NEG-03, NEG-04, NEG-05

**Success Criteria** (what must be TRUE):
1. JouleMeter correctly calculates Joules using weighted formula
2. Signed Execution Record (SER) generated with all required fields
3. CNP negotiation flow works: CFP → PROPOSE → ACCEPT/REJECT
4. Multi-round haggling with max-rounds limit
5. TTL per proposal triggers auto CANCEL

**Plans:** TBD

---

## Progress Table

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 0. Cleanup | 0/1 | Not started | - |
| 1. Scaffolding | 0/1 | Not started | - |
| 2. Identity & Semantics | 0/1 | Not started | - |
| 3. Client Implementation | 0/1 | Not started | - |
| 4. Economy | 0/1 | Not started | - |

---

## Coverage Map

```
CLEANUP-01 → Phase 0
CLEANUP-02 → Phase 0
CLEANUP-03 → Phase 0
CLEANUP-04 → Phase 0

SET-01 → Phase 1
SET-02 → Phase 1
SET-03 → Phase 1

ID-01 → Phase 2
ID-02 → Phase 2
ID-03 → Phase 2
ID-04 → Phase 2
ID-05 → Phase 2

SCH-01 → Phase 2
SCH-02 → Phase 2
SCH-03 → Phase 2
SCH-04 → Phase 2
SCH-05 → Phase 2
SCH-06 → Phase 2

CLI-01 → Phase 3
CLI-02 → Phase 3
CLI-03 → Phase 3

ECO-01 → Phase 4
ECO-02 → Phase 4
ECO-03 → Phase 4
ECO-04 → Phase 4
ECO-05 → Phase 4
ECO-06 → Phase 4
ECO-07 → Phase 4
ECO-08 → Phase 4

NEG-01 → Phase 4
NEG-02 → Phase 4
NEG-03 → Phase 4
NEG-04 → Phase 4
NEG-05 → Phase 4
```

---

*Roadmap updated: 2026-03-12 - Revised for A2A-based architecture*
