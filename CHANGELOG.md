# Changelog

## [0.4.1] — 2026-03-03

### Added
- DID:key issuer identity: `derive_did_key()` in `keys.py`; `contract.py` enforces DID:key as `issuer.agent_id` on signing and verification
- Canonical Joule formula in SPEC.md 5.6: `1 Joule = (input_tokens × 0.0001) + (output_tokens × 0.0003) + (wall_clock_seconds × 0.01)`
- `_measure_joules()` in `runtime.py` implementing the canonical formula
- E2E A2A test (`tests/test_e2e_a2a.py`): sign → A2A payload → execute → verify SER + ledger balance
- `GOVERNANCE.md`: proposal + 2-week comment period for SPEC.md changes; backward compatibility required for minor versions
- T11 (Issuer Identity Spoofing) in `threat_model.md` threat matrix

### Changed
- SPEC.md updated with Section 3.2 (Issuer Identity DID:key) and Section 5.6 (Canonical Joule Formula)
- Runtime Joule metering uses canonical formula instead of tool-registry `joule_cost`

## [0.4.0] — 2026-03-03

### Removed
- All protocol adapters except A2A: `acp.py`, `mcp.py`, `fipa.py`, `agui.py`, `anp.py`, `w3c.py`, `oasf.py`
- Solana/Helium settlement backends (`solana.py`, `HeliumBackend`)
- Probabilistic and parallel workflow types (sequence-only)
- `weight` field from WorkflowStep, `max_concurrency` from Workflow
- `__main__.py` (MCP server entry point)
- Dev dependencies: `fastapi`, `uvicorn`, `httpx`, `websockets`, `websocket-client`
- `agenlang_skills.md` (replaced by `skills.md`)

### Added
- `SignedLedger` and `LedgerEntry` in `settlement.py` — signed double-entry ledger with per-step ECDSA signatures
- Ledger entries embedded in SER under `"ledger_entries"` key
- `skills.md` — clean guide for registering AgenLang in LangChain/CrewAI/OpenClaw

### Changed
- Kernel consolidation: stripped to contract + signing + SER + A2A + simple signed ledger
- `runtime.py`: sequential-only execution, A2A-only protocol dispatch, signed ledger per step
- `settlement.py`: complete rewrite to signed double-entry ledger
- `models.py` and `schema/v1.0.json`: sequence-only workflow, no weight/max_concurrency
- README, AGENTS.md, threat_model.md updated for kernel-only architecture

## [0.3.4] — 2026-03-03

### Added
- `agenlang_skills.md` with LangChain, CrewAI, OpenClaw, MCP, and custom tool registration examples
- MCP server `/info` route, env-based `MCP_HOST`/`MCP_PORT` config, `__main__` entry, startup/shutdown logging
- WebSocket gossip in `anp.py`: `ws_exchange_contract_sync` (websocket-client), `ws_exchange_contract_async` (websockets)
- `GossipNode` auto-routes `ws://`/`wss://` to WebSocket, `http://`/`https://` to HTTP
- `LLMConfig` in `utils.py`: provider-agnostic config for OpenAI, Anthropic, xAI, and generic HTTP
- API key leak prevention: `_check_for_leaked_keys()` rejects contracts with embedded key patterns
- Multi-protocol E2E tests: ACP->AG-UI, ANP->MCP, full protocol chain
- `HELIUS_API_KEY` priority with `HELIUM_API_KEY` deprecated fallback in `solana.py`
- Dev dependencies: `websockets`, `websocket-client`

### Changed
- `_summarize_grok` renamed to `_summarize_llm`, uses `LLMConfig.from_env()` for multi-provider support
- `Contract.model_validate()` and `Contract.from_dict()` now scan for leaked API keys
- `SolanaBackend` reads `HELIUS_API_KEY` first, falls back to `HELIUM_API_KEY` with deprecation warning
- `start_mcp_server()` reads `MCP_HOST`/`MCP_PORT` env vars

## [0.3.3] — 2026-03-03

### Added
- `SolanaBackend` in `solana.py`: real Solana devnet JSON-RPC settlement (Helius-compatible), stub mode
- True concurrent parallel execution via `ThreadPoolExecutor` with thread-safe mutations
- `max_concurrency` field on Workflow model and schema (default: 5)
- FastAPI-based MCP HTTP server (`create_mcp_app`, `start_mcp_server`) with `/jsonrpc`, `/health`, `/tools`
- `GossipNode` class in `anp.py` for multi-round P2P contract broadcasting
- `retry_with_backoff` decorator in `utils.py` (exponential backoff, cumulative timeout)
- `StorageBackend` ABC in `memory.py` — all backends now subclass it
- `RedisMemoryBackend` for scalable distributed deployments
- Token-overhead test using `tiktoken` (asserts <110 token overhead)
- Adapter Examples section in README with copy-paste snippets for all protocols
- Mitigation Code References section in `threat_model.md`
- Dev dependencies: `tiktoken`, `redis`, `fastapi`, `uvicorn`, `httpx`

### Changed
- `_run_parallel` in `runtime.py` uses `ThreadPoolExecutor` instead of sequential loop
- All adapter network calls wrapped with `retry_with_backoff`
- `Memory`, `EncryptedMemoryBackend`, `SQLiteMemoryBackend` now subclass `StorageBackend`

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
