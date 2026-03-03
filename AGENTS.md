# AGENTS.md

## Project Overview
AgenLang is a standardised JSON contract substrate for secure, auditable, economically fair inter-agent communication. It provides cryptographic proofs, intent anchoring, GDPR-native memory handling, and JouleWork settlement. Designed as the contract/settlement layer on top of A2A/MCP.

## Tech Stack
- Language: Python 3.12+
- Core: pydantic v2, cryptography, structlog, click
- Testing: pytest + hypothesis
- CI: GitHub Actions (ruff, black, mypy, coverage >= 95%)
- License: Apache 2.0

## Setup Commands
```bash
pip install -e ".[dev]"
# For real tools:
export TAVILY_API_KEY=...
export XAI_API_KEY=...
agenlang run examples/amazo-flight-booking.json
```

## Architecture
- `src/agenlang/models.py` — Pydantic v2 models (full schema)
- `src/agenlang/contract.py` — Contract loading, ECDSA signing/verification
- `src/agenlang/runtime.py` — Workflow dispatcher, Joule metering, SER, protocol auto-detect
- `src/agenlang/keys.py` — KeyManager (ECDSA + SER HMAC)
- `src/agenlang/memory.py` — Encrypted (AES-GCM), SQLite, and plain backends
- `src/agenlang/tools.py` — Tavily web_search + Grok summarize (env var gated)
- `src/agenlang/settlement.py` — Pluggable settlement backends (Stub, Helium)
- `src/agenlang/cli.py` — Click CLI entry point

### Protocol Adapters
- `src/agenlang/a2a.py` — A2A JSON-RPC + SSE transport wrapper
- `src/agenlang/acp.py` — ACP REST message envelopes
- `src/agenlang/mcp.py` — MCP tool registration (JSON-RPC 2.0)
- `src/agenlang/fipa.py` — FIPA ACL performative mapping
- `src/agenlang/agui.py` — AG-UI SER lifecycle event streaming
- `src/agenlang/anp.py` — ANP P2P contract exchange with DID
- `src/agenlang/w3c.py` — W3C DID:web + DID:key identity
- `src/agenlang/oasf.py` — OASF manifest generation

## Do Not (non-negotiable)
- Never use dummy tools, hardcoded joules=42, or fake settlement.
- Never ship without 95%+ test coverage and passing security tests.
- Never claim JavaScript support until the npm package exists.
- Never introduce new dependencies without explicit approval.
- All crypto must be ECDSA + proper key management; no naive HMAC-only.
