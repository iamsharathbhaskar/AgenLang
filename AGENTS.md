# AGENTS.md

## Project Overview
AgenLang is a standardised JSON contract substrate for secure, auditable, economically fair inter-agent communication. It provides cryptographic proofs, intent anchoring, GDPR-native memory handling, and JouleWork settlement. Designed as the contract/settlement layer on top of A2A.

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
export LLM_PROVIDER=xai          # or openai, anthropic, generic
export LLM_API_KEY=...           # falls back to XAI_API_KEY/OPENAI_API_KEY/ANTHROPIC_API_KEY
agenlang run examples/amazo-flight-booking.json
```

## Architecture
- `src/agenlang/models.py` — Pydantic v2 models (full schema, sequence-only workflow)
- `src/agenlang/contract.py` — Contract loading, ECDSA signing/verification, leak prevention
- `src/agenlang/runtime.py` — Sequential workflow dispatcher, Joule metering, SER
- `src/agenlang/keys.py` — KeyManager (ECDSA + SER HMAC)
- `src/agenlang/memory.py` — StorageBackend ABC, Encrypted (AES-GCM), SQLite, Redis, and plain backends
- `src/agenlang/tools.py` — Tavily web_search + LLM summarize (multi-provider via LLMConfig)
- `src/agenlang/settlement.py` — Signed double-entry ledger (LedgerEntry + SignedLedger)
- `src/agenlang/a2a.py` — A2A JSON-RPC + SSE transport wrapper
- `src/agenlang/utils.py` — Shared utilities (retry_with_backoff, LLMConfig)
- `src/agenlang/cli.py` — Click CLI entry point
- `skills.md` — How to register AgenLang as a skill/tool in LangChain/CrewAI/OpenClaw

## Do Not (non-negotiable)
- Never use dummy tools, hardcoded joules=42, or fake settlement.
- Never ship without 95%+ test coverage and passing security tests.
- Never claim JavaScript support until the npm package exists.
- Never introduce new dependencies without explicit approval.
- All crypto must be ECDSA + proper key management; no naive HMAC-only.
