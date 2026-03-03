# Changelog

## [0.3.2] — 2026-03-03

### Added
- Weighted probabilistic workflow: `weight` field on WorkflowStep, `random.choices` with weights
- Multi-branch parallel execution with per-branch decision point tracking
- Conditional step execution: `{{step_N_output}}` resolved from prior outcomes
- Protocol auto-detect dispatch: `protocol:target` syntax routes through adapters
- Protocol adapters: `acp.py` (REST), `mcp.py` (tool registration), `fipa.py` (ACL), `agui.py` (event streaming), `anp.py` (DID P2P), `w3c.py` (DID:web/key), `oasf.py` (manifest)
- `HeliumBackend` with `HELIUM_API_KEY` authentication, proper headers, response parsing
- `threat_model.md` with NIST SP 800-53 aligned risk matrix (10 threat categories)
- Protocol compatibility table in README
- Tests for all 7 adapters + updated runtime/settlement tests

### Changed
- `runtime.py` refactored: `_run_sequence`, `_run_parallel`, `_run_probabilistic` dispatch methods
- `WorkflowStep` model now includes `weight: float = 1.0`
- `HeliumBackend` requires `HELIUM_API_KEY` env var for real mode (raises `ValueError` if missing)
- `schema/v1.0.json` updated with `weight` property on workflow steps

## [0.3.1] — 2026-03-03

### Added
- Probabilistic workflow execution: `random.choice` selects one step, records decision_point in SER
- `HeliumBackend` with HTTP API skeleton (stub mode via `api_url="stub:"`, real POST with try/except)
- Bandit security scan job in CI
- `examples/probabilistic.json` contract
- Tests for probabilistic runtime, HeliumBackend stub/error/success paths

### Changed
- `HeliumStubBackend` now subclasses `HeliumBackend` with `api_url="stub:"`
- `StubSettlementBackend` and `HeliumBackend` use structlog
- Runtime `execute()` dispatches on `workflow.type` (sequence, parallel, probabilistic)

### Fixed
- Bandit B311 (random) skipped for workflow choice; B101 (assert) skipped

## [0.3.0] — 2026-03-03

### Added
- Full root `ContractModel` in `models.py` with `Ser`, `DecisionPoint`, `SettlementReceipt`
- `EncryptedMemoryBackend` (AES-256-GCM) as default memory backend
- A2A transport: JSON-RPC 2.0 payload + Server-Sent Events (`contract_to_sse_event`, `parse_sse_event`)
- Reputation scoring in SER via `_compute_reputation_score`
- Efficiency scoring in SER via `_compute_efficiency`
- Hypothesis fuzzing for ECDSA sign/verify and contract tampering
- 48 tests at 95%+ coverage
- GitHub Actions CI: ruff, black, mypy, pytest with coverage gate
- Benchmarks table in README
- CHANGELOG.md

### Changed
- `KeyManager` wired end-to-end: contract signing, SER HMAC, memory encryption
- `Runtime` uses real step outputs for memory handoff (no dummy data)
- Real Joule metering from tool cost registry (no hardcoded values)
- `contract.py` `verify_signature()` uses inline crypto (no filesystem KeyManager)
- `pyproject.toml` bumped to v0.3.0, coverage threshold 95%, ruff >= 0.5
- AGENTS.md updated to public format with architecture guide
- PROTOCOL.md made internal (gitignored)
- `.egg-info` removed from tracking

### Fixed
- CI `ci.yml` typo (`setup.py` -> `setup-python`)
- `pyproject.toml` coverage config split (`[tool.coverage.run]` / `[tool.coverage.report]`)
- mypy type narrowing for `load_pem_public_key` / `load_pem_private_key`
- `requests` import typed ignore for mypy

## [0.2.0] — 2026-03-03

### Added
- ECDSA contract signing (`Contract.sign()` / `verify_signature()`)
- `KeyManager` with persistent file-based key storage
- `EncryptedMemoryBackend`, `SQLiteMemoryBackend`
- Tavily web_search + Grok summarize tools (env var gated)
- `SettlementBackend` abstraction with `StubSettlementBackend`, `HeliumStubBackend`
- A2A transport wrapper (`contract_to_a2a_payload`, `a2a_payload_to_contract`)
- structlog throughout (JSON for prod, console for dev)
- AGENTS.md, PROTOCOL.md
- Apache 2.0 LICENSE
- 5 example contracts
- TLA+ workflow safety stub

## [0.1.0] — 2026-03-03

### Added
- Initial AgenLang implementation
- Contract model with JSON schema validation
- Runtime with workflow execution
- CLI entry point (`agenlang run`)
- Memory handoff with GDPR purge
- HMAC-protected SER with replay
