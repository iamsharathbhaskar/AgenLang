# Phase 2: Exchange & Economy — Plan

**Objective:** Multi-round CNP negotiation with Joule-based metering and atomic settlement

**Dependencies:** Phase 1 (Protocol Foundation)

**Requirements covered:** NEG-01, NEG-02, NEG-03, NEG-04, NEG-05, ECO-01, ECO-02, ECO-03, ECO-04, ECO-05, ECO-06, ECO-07, ECO-08, CTR-03

---

## Plan 1: Negotiation Module (NEG-01 to NEG-05)

### Tasks
- Implement CNP state machine: IDLE → CFP_SENT → PROPOSE_RECEIVED → NEGOTIATING → ACCEPTED/REJECTED → EXECUTING → COMPLETED/CANCELLED
- Implement PROPOSE ↔ PROPOSE haggling rounds
- Implement ACCEPT-PROPOSAL and REJECT-PROPOSAL handling
- Implement TTL per proposal with auto CANCEL on expiration
- Implement max-rounds limit enforcement

### Implementation Details
- CNPSession model with current_round, max_rounds, proposals
- Proposal model with pricing, weights, timeout_seconds
- Background task to check and cancel expired proposals

---

## Plan 2: Economy Module (ECO-01 to ECO-08)

### Tasks
- Implement JouleMeter as context manager and decorator
- Implement weighted formula: Joules = (PromptTokens × W1) + (CompletionTokens × W2) + (Compute_Seconds × W3)
- Implement token counting via tiktoken
- Implement Signed Execution Record (SER) generation
- SER includes prompt_hash and completion_hash for receiver verification
- Implement Graceful Divergence threshold (±5%)
- Implement Joule Garbage Collector for stale PENDING reservations
- Implement atomic settlement on COMPLETED state only

### Implementation Details
- JouleMeter tracks prompt_tokens, completion_tokens, compute_seconds
- tiktoken for token counting (cl100k_base encoding)
- SER model with pricing, breakdown, hashes, signature
- JouleLedger for reservations and settlements
- 30-minute stale timeout for GC

---

## Success Criteria

1. ✓ CNP state machine handles CFP → PROPOSE → ACCEPT/REJECT flow
2. ✓ Multi-round PROPOSE ↔ PROPOSE haggling works with max-rounds limit
3. ✓ TTL per proposal triggers auto CANCEL on expiration
4. ✓ JouleMeter correctly calculates Joules using weighted formula
5. ✓ Token counting via tiktoken produces consistent counts
6. ✓ Signed Execution Record (SER) generated with all required fields
7. ✓ Graceful divergence threshold (±5%) validates token counts
8. ✓ Joule Garbage Collector reverts stale PENDING reservations after 30 minutes
9. ✓ Atomic settlement occurs ONLY on COMPLETED contract state
