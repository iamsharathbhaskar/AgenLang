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
- `src/agenlang/runtime.py` — Workflow dispatcher, Joule metering, SER
- `src/agenlang/keys.py` — KeyManager (ECDSA + SER HMAC)
- `src/agenlang/memory.py` — Encrypted (AES-GCM), SQLite, and plain backends
- `src/agenlang/tools.py` — Tavily web_search + Grok summarize (env var gated)
- `src/agenlang/a2a.py` — A2A JSON-RPC + SSE transport wrapper
- `src/agenlang/settlement.py` — Pluggable settlement backends
- `src/agenlang/cli.py` — Click CLI entry point

## Do Not (non-negotiable)
- Never use dummy tools, hardcoded joules=42, or fake settlement.
- Never ship without 95%+ test coverage and passing security tests.
- Never claim JavaScript support until the npm package exists.
- Never introduce new dependencies without explicit approval.
- All crypto must be ECDSA + proper key management; no naive HMAC-only.
