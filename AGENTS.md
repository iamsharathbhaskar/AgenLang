# AgenLang — Agent Development Guide

## Project Context

- **Language**: Python 3.12+
- **Package**: agenlang (`src/agenlang/`)
- **Goal**: Turn the current prototype into a production-ready, A2A-compatible, cryptographically sound contract and settlement layer that exceeds existing protocols.

## Tech Stack

- Python: pydantic v2, jsonschema, cryptography, click, structlog, pytest, hypothesis
- CI: GitHub Actions
- License: Apache 2.0

## Audience

- AI agent developers
- Security auditors
- Standards bodies (Linux Foundation A2A WG, NIST)

## Do Not (non-negotiable)

- Never use dummy tools, hardcoded joules=42, or fake settlement.
- Never ship without 95%+ test coverage and passing security tests.
- Never claim JavaScript support until the npm package exists.
- Never introduce new dependencies without explicit approval.
- All crypto must be ECDSA + proper key management; no naive HMAC-only.
- All changes must be minimal and focused — one task, one concern.

## Checkpoint Card

Before merging any change, answer:

1. **Is this change cryptographically sound?**
2. **Does it advance standards compliance?**

PROTOCOL.md is internal and not committed to the repository.
