# AgenLang Core Protocol

## What This Is

AgenLang is a clean, secure, Python-first library for Agent-to-Agent (A2A) communication, negotiation, micro-settlement, and legacy API bridging using cryptographically signed YAML messages. It enables autonomous agents to discover each other, negotiate tasks via the Contract Net Protocol (CNP), execute work, and settle payments using a Joule-based metering system.

## Core Value

A universal, secure protocol for agent-to-agent communication with cryptographically verified identity (DID), trustworthy negotiation, and transparent micro-settlements — enabling a decentralized agent economy.

## Requirements

### Validated

(None yet — ship to validate)

### Active

- [ ] **Identity Module** — DID:key generation, key storage/rotation, message signing & verification using RFC 8785 canonicalization
- [ ] **Schema Module** — Pydantic v2 models for message envelope + FIPA-ACL performatives (REQUEST, PROPOSE, ACCEPT-PROPOSAL, REJECT-PROPOSAL, INFORM, AGREE, REFUSE, FAILURE, CANCEL, CFP, NOT_UNDERSTOOD)
- [ ] **Transport Module** — Abstract async transport (HTTP + WebSocket), pluggable retry/exponential backoff, message deduplication
- [ ] **Core Agent** — BaseAgent abstract class with identity, transport, SQLite persistence, asyncio message loop, event handlers
- [ ] **Negotiation Module** — Contract Net Protocol (CNP) stateling support, TTL per machine with hagg proposal, max-rounds
- [ ] **Economy Module** — JouleMeter instrumentation, Signed Execution Record (SER) generation, internal double-entry ledger
- [ ] **Bridge Module** — MCP Client adapter to consume external MCP servers as stateless AgenLang agents
- [ ] **Contracts Module** — Task lifecycle state machine (PENDING, RUNNING, COMPLETED, FAILED, CANCELLED)
- [ ] **Discovery** — Agent Card schema, HTTP-based discovery via `/.well-known/agent-card.json`, mDNS local discovery

### Out of Scope

- [NATS/Redis brokers] — Deferred to optional `agenlang[brokers]` extra
- [OpenTelemetry observability] — Deferred to optional `agenlang[observability]` extra
- [Agent-as-MCP-server] — AgenLang only consumes MCP, never exposes itself as MCP server

## Context

This is a greenfield project to build a production-ready Python library. The protocol specification is defined in AgenLang_GSD_Build_Plan.md which includes:
- Detailed module specifications (identity, schema, transport, core, negotiation, economy, bridge, contracts)
- Signed message envelope format with Ed25519 signatures over RFC 8785 canonicalized JSON
- FIPA-ACL compliant performatives for agent negotiation
- Joule-based metering with signed execution records for verifiable micro-settlements
- Agent Card discovery mechanism
- Project layout following modern Python packaging standards (src layout)

## Constraints

- **Language**: Python only — async-only (no blocking I/O)
- **Security**: Ed25519 signatures mandatory, HTTPS/WSS enforced, no plaintext transport
- **Signatures**: Must use RFC 8785 JSON Canonicalization Scheme for all signing
- **Storage**: SQLite for persistence, path configurable via `~/.agenlang/config.yaml` or env vars
- **Packaging**: Must follow `src/` layout for PyPI/conda-forge compatibility

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Use `cryptography` over `pynacl` | Better ecosystem support and broader compatibility | — Pending |
| RFC 8785 canonicalization | Ensures signatures work across languages/parsers | — Pending |
| Joule-based metering | Provides verifiable, receiver-validatable metering | — Pending |
| SQLite for persistence | Simple, zero-config, async-compatible via aiosqlite | — Pending |

---
*Last updated: 2026-03-11 after initialization*
