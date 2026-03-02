# Better Coder Protocol v0.1.1-AgenLang

Modified protocol for AgenLang production readiness. Phases 0–5 only.

## Phases (recursive)

| Phase | Scope |
|-------|-------|
| **Phase 0** | Context: AGENTS.md, PROTOCOL.md |
| **Phase 1** | Hygiene: license, README, examples, logging, docstrings; approved deps in pyproject.toml |
| **Phase 2** | Type safety and validation: Pydantic models, schema path |
| **Phase 3** | Crypto and security: ECDSA, KeyManager, SER verification, EncryptedMemoryBackend |
| **Phase 4** | Runtime completeness: ToolRegistry, real tools (Tavily + Grok stub), workflow dispatcher, Joule metering, SettlementBackend, SQLite |
| **Phase 5** | Quality and CI + Differentiation: pytest, hypothesis, 90%+ coverage, GitHub Actions, schema features, TLA+ stub, A2A transport, JouleWork/reputation, version 0.2.0 |

## AGENTS.md + Checkpoint Card

- Link to [AGENTS.md](AGENTS.md) from README and onboarding.
- Require security questions on every change: "Is this change cryptographically sound? Does it advance standards compliance?"

## Testing and Security

- 90%+ test coverage before ship.
- Security tests: tampering detection, replay rejection, key rotation.
- No dummy crypto; all signing/verification must use ECDSA and proper key management.

## MCP Fallback Rule

When integrating tools, prefer MCP/A2A adapters. Document fallback behavior when real APIs are unavailable.

## Cuts

- No scope creep.
- No new dependencies without approval.
- No JavaScript claim until npm package exists.
