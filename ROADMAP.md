# AgenLang Roadmap to Real-World Readiness

## Current State Assessment

### What's Working (v0.4.2)
- Core contract format with JSON schema validation
- ECDSA P-256 signing/verification with DID:key identity
- Sequential workflow execution with Joule metering
- Basic tool registry (web_search, summarize)
- AES-256-GCM encrypted memory backend
- Signed double-entry ledger for settlement tracking
- A2A transport wrappers (JSON-RPC + SSE)
- API key leak prevention
- 87/90 tests passing (95%+ coverage target)

### Critical Gaps for Production

| Priority | Gap | Impact | Effort |
|----------|-----|--------|--------|
| P0 | No A2A server implementation | Cannot receive contracts from other agents | High |
| P0 | Subcontract/skill/embed actions not implemented | Cannot delegate to other agents | Medium |
| P0 | Protocol dispatch is stubbed | A2A protocol messages go nowhere | Medium |
| P1 | No agent discovery/registry | Agents can't find each other | High |
| P1 | No reputation persistence | Scores computed but lost after execution | Low |
| P1 | No rate limiting | DoS vulnerability (T4) | Medium |
| P1 | Capability attestations not verified | Tool poisoning risk (T7) | Medium |
| P2 | No containerization/deployment | Hard to deploy in production | Medium |
| P2 | Limited observability | No metrics, tracing, health checks | Medium |
| P2 | No contract templates/generator | Developer friction | Low |
| P2 | Settlement is ledger-only | No actual payment integration | High |

---

## Implementation Roadmap

### Phase 1: Core Infrastructure (Weeks 1-2) ✅ COMPLETE
**Goal**: Agents can actually send and receive contracts

**Status**: All core infrastructure implemented and tested

- [x] **A2A Server Implementation**
  - FastAPI-based A2A server with JSON-RPC endpoint
  - SSE streaming support for async responses
  - Health check and discovery endpoints

- [x] **Protocol Dispatch Implementation**
  - Real A2A dispatch function that sends HTTP requests
  - Retry logic with exponential backoff
  - Timeout handling and response validation

- [x] **Subcontract Execution**
  - Subcontract action implementation
  - Recursive contract execution with depth limits
  - Cross-contract Joule budget tracking
  - Nested SER aggregation

- [x] **Skill Action Implementation**
  - Protocol-based skill dispatch via `a2a:` prefix

- [x] **CLI Extensions**
  - `agenlang server` - Start A2A server
  - `agenlang identity` - Show agent DID:key
  - `agenlang send` - Send contracts to other agents

**Deliverable**: `agenlang server` command that can receive and execute contracts ✅

---

### Phase 2: Agent Discovery & Registry (Weeks 3-4) ✅ COMPLETE
**Goal**: Agents can find and trust each other

**Status**: Full registry implementation with reputation tracking

- [x] **Agent Registry Service**
  - SQLite-backed registry (`src/agenlang/registry.py`)
  - Agent registration with DID:key
  - Capability advertisement and search
  - Reputation score persistence
  - Execution history tracking

- [x] **CLI Registry Commands**
  - `agenlang registry register` - Register an agent
  - `agenlang registry list` - List registered agents
  - `agenlang registry find` - Find by capability
  - `agenlang registry show` - Show agent details
  - `agenlang registry stats` - Registry statistics
  - `agenlang registry history` - Execution history
  - `agenlang registry update-reputation` - Update reputation

- [x] **Server Integration**
  - Auto-self-registration on server start
  - Execution recording in registry
  - Automatic reputation calculation
  - Registry API endpoints (`/registry/agents`, `/registry/find`, `/registry/stats`)

- [x] **Reputation System**
  - Success rate tracking
  - Efficiency-based scoring
  - Automatic updates post-execution

**Deliverable**: Agents can discover peers and verify identities ✅

---

### Phase 3: Production Hardening (Weeks 5-6) ✅ COMPLETE
**Goal**: Production-ready security and observability

**Status**: Full production hardening implemented with rate limiting, circuit breakers, observability, security middleware, and configurable storage backends

- [x] **Rate Limiting & Resource Controls**
  - Per-agent rate limiting (token bucket algorithm)
  - Global rate limiting across all requests
  - Per-IP rate limiting for DDoS mitigation
  - Per-contract rate limiting for fine-grained control
  - Multi-strategy rate limiter combining all strategies
  - Circuit breakers for external services (closed/open/half-open state machine)
  - Configurable retry logic and timeout handling

- [x] **Observability Stack**
  - Metrics collection (Joules consumed, contracts executed, errors, latencies)
  - Distributed tracing with span tracking for contract execution
  - Structured logging with correlation IDs
  - Health check endpoint with component status
  - `/metrics` endpoint for Prometheus-compatible scraping
  - `/traces` endpoint for trace inspection
  - `/circuit-breakers` endpoint for breaker status monitoring

- [x] **Security Hardening**
  - TLS support in server configuration (cert/key file paths)
  - Input validation middleware (JSON schema, size limits)
  - Security headers middleware (X-Content-Type-Options, X-Frame-Options, etc.)
  - CORS configuration support
  - Path traversal prevention
  - Request size limits to prevent memory exhaustion

- [x] **Memory & Storage Improvements**
  - Redis backend configurable via `AGENLANG_MEMORY_BACKEND` env var
  - Encrypted storage as default backend
  - Configurable memory backend selection at runtime

**Deliverable**: Production deployment with monitoring and security controls ✅

---

### Phase 4: Developer Experience (Weeks 7-8)
**Goal**: Easy to adopt and integrate

1. **Docker & Deployment**
   - Dockerfile and docker-compose.yml
   - Helm chart for Kubernetes
   - Configuration management (environment, config files)
   - Migration guides

2. **SDK & Bindings**
   - JavaScript/TypeScript client SDK
   - Python client SDK improvements
   - LangChain/LlamaIndex integration helpers

3. **Documentation**
   - API reference (auto-generated from OpenAPI)
   - Tutorial: Building your first agent
   - Tutorial: Multi-agent workflow
   - Deployment guide
   - Security best practices

4. **Example Applications**
   - Personal assistant (Amazo-style) demo
   - ZHC swarm example
   - Multi-hop delegation example
   - Integration with popular frameworks

**Deliverable**: Complete developer experience with examples and tutorials

---

## Technical Architecture Additions

### A2A Server Architecture
```
+------------------+         +------------------+
|   AgenLang Agent | <-----> |   A2A Server     |
|   (HTTP Client)  |   HTTPS |   (FastAPI)      |
+------------------+         +--------+---------+
                                      |
                            +---------v---------+
                            | Contract Queue    |
                            | (Redis/SQLite)    |
                            +---------+---------+
                                      |
                            +---------v---------+
                            | Runtime Executor  |
                            | (Worker Pool)     |
                            +---------+---------+
                                      |
                            +---------v---------+
                            | SER Storage       |
                            | (Encrypted)       |
                            +-------------------+
```

### Agent Registry Schema
```sql
CREATE TABLE agents (
    did_key TEXT PRIMARY KEY,  -- did:key:z...
    pubkey_pem TEXT NOT NULL,
    endpoint_url TEXT,         -- A2A server URL
    capabilities JSON,         -- ["net:read", "compute:write"]
    reputation_score REAL,     -- 0.0 to 1.0
    joule_rate REAL,           -- Cost per Joule
    created_at TIMESTAMP,
    last_seen TIMESTAMP
);

CREATE TABLE contracts_executed (
    execution_id TEXT PRIMARY KEY,
    issuer_did TEXT,
    receiver_did TEXT,
    joules_used REAL,
    status TEXT,               -- success, failed, timeout
    created_at TIMESTAMP
);
```

---

## Success Criteria

### Minimum Viable Production (MVP)
- [ ] A2A server can receive and execute contracts
- [ ] Agents can discover each other via registry
- [ ] Subcontract delegation works end-to-end
- [ ] Basic rate limiting prevents abuse
- [ ] Docker deployment works
- [ ] 95%+ test coverage maintained

### Full Production Readiness
- [ ] Mutual TLS for all transport
- [ ] Complete observability (metrics, tracing, logging)
- [ ] Reputation system with persistent scores
- [ ] Capability attestation verification
- [ ] JavaScript SDK
- [ ] Comprehensive documentation
- [ ] Security audit complete

---

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| Scope creep | Strict phase gates; MVP first |
| Security vulnerabilities | Threat model review per phase; security tests |
| Performance issues | Load testing in Phase 3; benchmarks |
| Adoption friction | Developer experience focus in Phase 4; examples |

---

## Notes

- Maintain backward compatibility with v1.0 contract schema
- All changes follow GOVERNANCE.md process
- Security is non-negotiable (per AGENTS.md Do Not rules)
- Target: Python 3.12+, type hints throughout
