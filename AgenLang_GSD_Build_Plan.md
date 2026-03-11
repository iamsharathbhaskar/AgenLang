# Project: AgenLang Core Protocol (v0.1.0)
**Objective:** Build a clean, secure, Python-first library for Agent-to-Agent (A2A) communication, negotiation, micro-settlement, and legacy API bridging using cryptographically signed YAML messages.

## 1. Core Modules & Technical Specs

- **agenlang.identity**  
  did:key generation & management using `cryptography` (preferred over pynacl for better ecosystem support).  
  Generate Decentralized Identifiers (DIDs) in `did:key:...` format (deterministic multicodec + multibase encoding for cross-protocol compatibility). 
  Secure private key storage in `.agenlang/keys/` (encrypted with OS keyring or simple passphrase fallback).
    - Explicit `did:key` format: Ed25519 public key → multicodec prefix `0xed01` + multibase `base58btc` encoding (result starts with `z6Mk...`).  
    Use `cryptography.hazmat.primitives.asymmetric.ed25519` for generation, signing, and verification to ensure cross-ecosystem compatibility.  
  Implement message signing and verification using RFC 8785 (JSON Canonicalization Scheme). All YAML payloads must be converted to canonical JSON before hashing to ensure cryptographic signatures remain valid across different programming languages, parsers, and white-space formatting.

- **agenlang.schema**  
  Pydantic v2 models for the full message envelope + FIPA-ACL compliant content.  
  Required performatives: `REQUEST`, `PROPOSE`, `ACCEPT-PROPOSAL`, `REJECT-PROPOSAL`, `INFORM`, `AGREE`, `REFUSE`, `FAILURE`, `CANCEL`, `CFP`, `NOT_UNDERSTOOD`.  
  Support for threading: `conversation_id`, `reply_with`, `in_reply_to`.  
  Content language / ontology: minimal — `"AgenLang-v1"` with JSON-compatible payloads.  
  Includes a simple Standardized Error Registry (Enum) for programmatic recovery (e.g. `ERR_CAPABILITY_MISMATCH`, `ERR_INSUFFICIENT_JOULES`, `ERR_PAYLOAD_TOO_LARGE`, `ERR_TASK_TIMEOUT`).
  Any `REFUSE` or `FAILURE` performative MUST strictly include an `error_code` from this registry within its payload to clearly define the rejection reason programmatically, avoiding ambiguous string parsing.  
  Task lifecycle states moved to the new core `agenlang.contracts` module.
  Extend the `NOT_UNDERSTOOD` performative to include a mandatory `protocol_meta` block. When a version mismatch occurs, the agent must respond with `NOT_UNDERSTOOD` and a payload specifying its supported `min_version` and `max_version`. For binary data support, add a `payload_encoding` field (defaulting to `identity` for text) and a `media_type` field (standard MIME type) to the message content schema, allowing agents to transmit non-textual artifacts like PDFs or images as Base64-encoded strings.
  To prevent memory-exhaustion attacks, all Base64 payloads MUST be limited to 10 MB (configurable via agent settings); larger payloads trigger immediate `NOT_UNDERSTOOD` with `ERR_PAYLOAD_TOO_LARGE`.
  Implement 'Lazy Payload Validation': the `BaseAgent` must verify the envelope signature before attempting to fully deserialize or decode large binary/Base64 content to prevent memory-exhaustion attacks during the parsing phase.
  The `protocol_meta` block (when present in a `NOT_UNDERSTOOD` response) MUST contain `min_version` and `max_version` as strings in semver format (e.g. "0.1.0").
 Use the `rfc8785` library (pure-Python RFC 8785 JSON Canonicalization Scheme) for all message signing/verification. Never canonicalize raw YAML strings — always parse YAML first with `yaml.safe_load`, build the dict structure, then apply `rfc8785.canonicalize()`.

  Exact signing/verification pipeline (identical in every implementation):
  ```python
  signing_payload = {
      "envelope": {k: v for k, v in envelope.items() if k != "signature"},
      "content": content_dict   # already parsed & validated Pydantic model → dict
  }
  canonical_bytes = rfc8785.canonicalize(signing_payload)  # sorted keys, minimal whitespace, UTF-8
  digest = hashlib.sha256(canonical_bytes).digest()
  signature = ed25519_private_key.sign(digest)              # or verify equivalent
  ```

- **agenlang.transport**   
  Abstract async transport interface (initial implementation: HTTP + WebSockets/SSE).  
  Pluggable design with built-in retry, exponential backoff, and message deduplication (via nonce + message_id).  
  Enterprise brokers (NATS/Redis) live in the optional `agenlang.transport.brokers` extension.
    All incoming AgenLang messages are sent via **POST** to the exact base URL advertised in the Agent Card's `transports[].url` field (example: `https://agent.example.com/agenlang`). The Phase 0 stub server implements this single POST route + the static `/.well-known/agent-card.json` route.
  All HTTP transports MUST use HTTPS and all WebSocket transports MUST use WSS. Plaintext endpoints are rejected at startup with a clear `ConfigurationError` (enforced in the transport base class and documented in the transport README).

- **agenlang.core**  
  `BaseAgent` abstract base class that wires everything together:  
  - identity + key management  
  - transport layer  
  - SQLite persistence (`agenlang.session.db`)  
  - asyncio message receive/send loop  
  - lifecycle methods (start / stop / health)  
  - event handlers: `on_message`, `on_request`, `on_propose`, `on_inform`, etc.
  - Implement a 'Nonce Sentry' logic within the `BaseAgent` that checks all incoming message nonces against the `session.db`. To prevent infinite database growth, implement an automatic pruning routine that deletes nonces older than 24 hours (or a configurable TTL), effectively enforcing a 'validity window' for signed messages. To prevent synchronous database writes from bottlenecking high-volume message loops, the Nonce Sentry MUST use an async-buffered writer (e.g., batching inserts via `asyncio.Queue` and `aiosqlite.executemany`) rather than awaiting individual row inserts per message.
  - Include an optional `trusted_dids` filter within the `session.db`; when enabled, the `BaseAgent` will silently drop or `REFUSE` any incoming messages from DIDs not present in the allow-list to provide a baseline security layer.
    - The optional `trusted_dids` filter is loaded from `~/.agenlang/config.yaml` (or env var `AGENT_TRUSTED_DIDS`) at startup and persisted in `session.db` for fast lookup; the list can be updated via the future admin CLI (not required for v0.1.0).

- **agenlang.negotiation**  
  Contract Net Protocol (CNP) state machine with haggling support.  
  Supports `PROPOSE` ↔ `PROPOSE` / `ACCEPT-PROPOSAL` / `REJECT-PROPOSAL` rounds.  
  Built-in TTL (Time-To-Live) per proposal + max-rounds; auto-fires `CANCEL` events on expiration to prevent "hanging" resource locks.

- **agenlang.economy**  
  `JouleMeter` instrumentation class (context manager + decorator).  
  Standardized Weighted Formula: `Joules = (PromptTokens × W1) + (CompletionTokens × W2) + (Compute_Seconds × W3)`
  - `Prompt/Completion Tokens`: Weighted via `tiktoken` to prevent input-flooding DDoS attacks.
  - `Compute_Seconds`: Wall-clock execution time for precise hardware metering.
  - Weight Authority: The weights `W1`, `W2`, and `W3` are defined by the Provider in their signed Agent Card. The Consumer must use these weights to validate the total Joules in the SER. If weights are missing from the Card, the library defaults to `W1`=1.0, `W2`=3.0, `W3`=10.0 
  Produces cryptographically signed **Signed Execution Record (SER)**.  
  Basic internal double-entry ledger + extension points for settlement (Stripe bridge, crypto micropayments).
  Produces cryptographically signed Signed Execution Record (SER) containing verifiable token hashes and breakdown so the receiver can independently re-compute and validate Joules.
  To ensure deterministic Joule validation across different environments, the `JouleMeter` and resulting SER must record the specific tokenizer version (e.g., `tiktoken` version or encoding name) used for the calculation.
    - Implement a configurable "Graceful Divergence" threshold for token count validation across tokenizer versions/environments (default ±5%, env var `JOULE_DIVERGENCE_TOLERANCE=0.05`).  
    Purpose: Tolerate minor environment differences while still detecting meaningful tampering or miscalculation. Document clearly that exceeding this threshold should trigger `REFUSE` with `ERR_JOULE_VALIDATION_FAILED` or equivalent.
  - Implement a Joule Garbage Collector background task that monitors the `session.db` for 'PENDING' reservations; it must automatically revert any Joule locks for tasks that have remained stale (no state update) beyond a configurable TTL (default 30 minutes) to prevent 'zombie' tasks from permanently exhausting the agent's compute budget.

```yaml
# Add these four fields to every Signed Execution Record (SER), the values are just examples
ser:
  pricing:
    base_joules: 15.0
    per_1k_tokens: 2.5
    weights: 
      w1_prompt: 1.0
      w2_completion: 3.0
      w3_compute_sec: 10.0
  breakdown:
    prompt_tokens: 12450
    completion_tokens: 850
    compute_seconds: 1.23
    tokenizer: "cl100k_base"
  prompt_hash: "sha256:9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08"  # hash of exact prompt bytes
  completion_hash: "sha256:..." 
  execution_id: "exec_01J8K9M2P3Q4R5S6T7U8V9W0X"  # for audit
  signature: "..."
```


- **agenlang.bridge**  
  MCP **Client** adapter using the official `mcp` package.  
  Consumes external MCP servers (e.g. Stripe, GitHub, Postgres, or any REST API wrapped as MCP) and wraps them as stateless AgenLang agents.  
  The wrapped agent speaks signed AgenLang YAML, participates in CNP negotiation, meters Joules, and produces SERs.  
  AgenLang agents **never** expose themselves as MCP servers — AgenLang remains the primary protocol.

- **agenlang.contracts** 
  Dedicated module for the Task Lifecycle State Machine (states: PENDING, RUNNING, COMPLETED, FAILED, CANCELLED) and contract metadata.  
  Used by `negotiation` and `economy` to ensure atomic settlement only on COMPLETED state.

- **Optional Extensions** (installed via extras: `agenlang[brokers,observability]`)  
  - `agenlang.transport.brokers`: BrokerTransport implementations (NATS, Redis) for high-reliability corporate LANs. Lazy-loaded; zero impact on core.  
  - `agenlang.observability`: Full W3C Trace-Context + OpenTelemetry integration. Only activated when explicitly enabled in agent config.

## 2. Structural Guardrails (The Intent Anchor)

- **Signed Message Envelope**  
  Every message MUST use a strict outer envelope structure with detached Ed25519 signature over canonicalized content.  
  This provides replay protection, non-repudiation, and clean multi-hop traceability.
  The `nonce` field MUST be generated using a cryptographically secure random number generator (e.g., using `secrets.token_hex(32)` in Python). The standard `random` module is strictly forbidden for nonce generation to prevent predictable sequence attacks in high-security environments.

```yaml
# Example signed message envelope (YAML)
envelope:
  protocol_version: "0.1.0"
  message_id: "msg_01J8K9M2P3Q4R5S6T7U8V9W0X"
  sender_did: "did:key:z6MkpTHR8VNsBxYaaWhcM8z5VAbmzU3NaXPt9gRy2Kz5"
  receiver_did: "did:key:z6Mks2Z6gK2v3u4f5g6h7i8j9k0l1m2n3o4p5q6r7s8t"
  nonce: "a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6"   # 32-byte hex that is cryptographically random
  timestamp: "2025-10-15T14:30:22.123Z"
  expires_at: "2025-10-15T14:45:22.123Z"
  trace_id: "trace_01J8K9M2P3Q4R5S6T7U8V9W0X"
  parent_contract_id: null                     # or "ctr_01J8K9M2P..."
  conversation_id: "conv_01J8K9M2P3Q4R5S6T7U8V9W0Y"
  reply_with: null
  in_reply_to: null
  signature: "base64url-encoded-Ed25519-detached-signature-of-canonicalized-envelope+content"
content:
  performative: "PROPOSE"
  content:
    task: "summarize the attached document"
    proposal_id: "prop_01J8K9M2P3Q4R5S6T7U8V9W0Z"
      pricing:
    base_joules: 15.0
    per_1k_tokens: 2.5
    weights:          # Mandatory for Joule validation
      w1_prompt: 1.0
      w2_completion: 3.0
      w3_compute_sec: 10.0
    max_rounds: 5
    timeout_seconds: 300
    # task-specific payload follows...
```

- **Timestamp & Clock Rules**  
  All `timestamp` and `expires_at` fields **MUST** be valid ISO 8601 strings in UTC with 'Z' suffix and millisecond precision (example: `"2025-10-15T14:30:22.123Z"`).  
  Enforced in the Pydantic schema using `datetime` with strict timezone validation.  
  All agents MUST use a monotonic clock source; clock skew > 30 seconds triggers `NOT_UNDERSTOOD`.
  At startup, the `BaseAgent` must perform a sanity check of the system clock and log a high-priority 'System Clock Warning' if clock skew is detected, alerting administrators that security verification (signature timestamps) may fail.

- **Multi-Hop Traceability**  
  Every message envelope **MUST** include two mandatory traceability fields:  
  - `trace_id`: A globally unique identifier (e.g., UUIDv7 or prefixed random string) that remains identical across the entire request chain, even through multiple hops and sub-contracts. This allows reconstructing the full provenance of any execution or settlement.  
  - `parent_contract_id`: The contract ID of the **immediate parent** contract that delegated this task (format: `"ctr_"` prefix + UUID or similar). Set to `null` for root-level (topmost) requests.  
  Purpose: Enables complete audit trails, transparent sub-contracting chains, billing aggregation across hops, and automated dispute resolution or debugging.

- **State Persistence**  
  All agents **MUST** maintain a single local SQLite database located at:  
  `~/.agenlang/agents/<agent-id>/session.db` (or configurable path via environment / settings)  
  This database is used to persistently store:  
  - Active contract states (full CNP lifecycle tracking: initiated → proposed → accepted → executing → settled → completed/failed/cancelled)  
  - Joule usage logs and cryptographically signed **Signed Execution Records (SERs)** for every completed task  
  - Cached Agent Card discovery results (with per-entry TTL / expiration timestamps)  
  - Pending outbound messages and retry queues (for offline or unreliable transports)  
  Schema should include tables for: `contracts`, `ser_records`, `agent_cards`, `message_queue`, and appropriate indexes on `trace_id`, `conversation_id`, `contract_id`.

- **Agent Card & Discovery**  
  Every agent **MUST** maintain and periodically publish a cryptographically signed **Agent Card** — a self-describing YAML/JSON document that advertises its identity and capabilities.  
  Required Agent Card fields:  
  - `did`: The agent's Decentralized Identifier (`did:key:...`)
  - `name`: Human-readable short name (e.g., "Document Summarizer v1.2")  
  - `description`: Longer human-readable description of purpose and behavior  
  - `capabilities`: Array of supported tasks, each with:  
    - `task`: Unique task identifier (e.g., "summarize", "translate", "search")  
    - `input_schema`: JSON Schema (Draft 2020-12 subset) describing accepted input  
    - `output_schema`: JSON Schema describing returned output  
    - `pricing`: Pricing hints (estimates only — final price negotiated):
        - `base_joules`: Fixed cost per invocation
        - `per_1k_tokens`: Optional marginal cost per 1000 tokens
        - `weights`: **Mandatory** when Joule metering is used — the exact coefficients the Provider expects Consumers to apply when validating SERs
            - `w1_prompt`: float (default 1.0 if missing)
            - `w2_completion`: float (default 3.0 if missing)
            - `w3_compute_sec`: float (default 10.0 if missing)
        - `currency`: "joules" (default) or future extensions
  - `transports`: Array of supported communication endpoints, e.g.:  
    - `{ "type": "http", "url": "https://agent.example.com/agenlang" }`  
    - `{ "type": "websocket", "url": "wss://agent.example.com/ws" }`  
  - `mcp_tools`: Optional array of MCP-compatible tool manifests (for Anthropic-style agent compatibility)  
  - `updated_at`: ISO 8601 timestamp of last update  
  - `signature`: Detached Ed25519 signature over the canonicalized card content  

  **Discovery mechanism** (initial v0.1.0 implementation):  
  - Primary: HTTP-based discovery via the `/.well-known/agent-card.json` standard for global reach.  
  - Secondary: mDNS / Zeroconf broadcast for local-network peer discovery (`_agenlang._tcp.local`).  
  - Fallback: Configurable sync to a decentralized DHT node or shared registry.

  Agents cache discovered cards locally (with TTL) and refresh them proactively or on-demand.

## 3. GSD Execution Roadmap

1. **Phase 0 (Protocol & Skeleton)**  
   - Define and lock in the message envelope schema + canonicalization rules for signing.  
     Canonicalization: YAML → `rfc8785` (RFC 8785 compliant, battle-tested) → sorted JSON (keys alphabetical, no whitespace) → UTF-8 bytes. The helper will live in `agenlang/schema.py`.
   - Create Agent Card schema (Pydantic model) + signing/verification helpers  
   - Implement minimal `BaseAgent` skeleton with:  
        - identity loading  
        - basic HTTP/WebSocket transport stub that:
          - serves the signed Agent Card at `/.well-known/agent-card.json` (static GET route)
          - accepts incoming signed YAML messages via POST to the base URL (e.g. `/agenlang`)
          - announces via mDNS
          (do not over-engineer — a minimal async server with two routes is sufficient; no full-featured API needed in Phase 0) 
        - SQLite session.db initialization (tables for contracts, SERs, agent_cards, message_queue)  
   - Set up `pyproject.toml` with core dependencies + optional extras:  
        - pydantic, pydantic-settings  
        - cryptography  
        - keyring       # OS keyring encryption for private keys (with passphrase fallback)
        - aiosqlite, pyyaml (safe_load), httpx, fastapi (for transport), websockets  
        - zeroconf (for mDNS discovery)
        - uuid (standard lib)  
        - tiktoken (for token counting)
        - structlog for better logging
        - mcp 
        - rfc8785  # RFC 8785 JSON Canonicalization Scheme (JCS) — pure-Python, battle-tested
        - [project.optional-dependencies]
            brokers = ["nats-py", "redis"]
            observability = ["opentelemetry-api", "opentelemetry-sdk"] 
   - Build a basic multi-agent test harness using asyncio + pytest-asyncio

2. **Phase 1 (Foundation)**  
   - Complete `agenlang.identity`: DID generation, key storage/rotation, signing & verification  
   - Build `agenlang.schema`: Full Pydantic models for envelope + all FIPA performatives + content payloads  
   - Implement SQLite persistence basics (CRUD for contracts, SERs, discovery cache)

3. **Phase 2 (Exchange & Economy)**  
   - Develop `agenlang.negotiation`: CNP state machine with haggling loop, timeouts, max rounds  
   - Implement `agenlang.economy`: JouleMeter (context manager + decorator), SER generation & signing  
   - Integrate negotiation + economy hooks into `BaseAgent` event handlers  
   - Develop the internal ledger to atomically trigger settlement only upon a Task reaching the COMPLETED state, ensuring that 'Joule' transfers are cryptographically tied to the successful resolution of a contract rather than the mere receipt of a message.

4. **Phase 3 (Bridge & Polish)**  
   - Build `agenlang.bridge`: MCP adapter + example wrappers (e.g., Stripe for payments, GitHub for repo access)  
   - Implement discovery + optional extensions (BrokerTransport and Observability) 
   - Create CLI tools:  
     - `agenlang agent start` (launch agent with config)  
     - `agenlang discover` (list local agents)  
     - `agenlang inspect <trace_id>` (show contract chain)  
   - Add developer guardrails: per-DID rate limiting, negotiation timeouts, structured logging  
   - Write comprehensive examples + integration tests (multi-agent CNP negotiation flows)

```yaml
# Example Agent Card (signed YAML fragment):
agent_card:
  did: "did:key:z6MkpTHR8VNsBxYaaWhcM8z5VAbmzU3NaXPt9gRy2Kz5"
  name: "Document Summarizer v1"
  description: "Fast summarization with transparent joule pricing"
  capabilities:
    - task: "summarize"
      input_schema:
        type: object
        properties:
          text: { type: string }
          max_length: { type: integer, default: 200 }
      output_schema:
        type: object
        properties:
          summary: { type: string }
  pricing:
    base_joules: 15.0
    per_1k_tokens: 2.5
    weights:          # Mandatory for Joule validation
      w1_prompt: 1.0
      w2_completion: 3.0
      w3_compute_sec: 10.0
  transports:
    - type: http
      url: "https://summarizer.example.com/agenlang"
    - type: websocket
      url: "wss://summarizer.example.com/ws"
  mcp_tools: []
  updated_at: "2025-10-15T12:00:00Z"
  signature: "Ed25519-base64url..."
```
## 4. DO NOT Rules (Non-Negotiable Guardrails)

The following practices are explicitly forbidden in AgenLang to maintain interoperability, security, and ecosystem compatibility:

- DO NOT invent custom transport formats or use XML — all messages MUST be signed YAML using the envelope defined in Section 2.  
- DO NOT expose AgenLang agents as MCP servers — only consume MCP servers via the bridge module.  
- DO NOT put private keys or secrets in any broadcasted Agent Card or discovery payload.  
- DO NOT use wall-clock `Compute_Seconds` alone for Joule metering without the receiver-verifiable `prompt_hash`/`completion_hash` fields.  
- DO NOT implement blocking I/O in the message loop — everything MUST be async (asyncio).  
- DO NOT hard-code SQLite paths or keys — always respect `~/.agenlang/config.yaml` or environment variables.  
- DO NOT ship NATS/Redis dependencies in the core package — they MUST remain optional extras only.  
- DO NOT deviate from RFC 8785 canonicalization for signatures — even a single whitespace difference invalidates the signature.
- DO NOT allow plaintext HTTP or WS transports — HTTPS/WSS enforcement is mandatory at startup.
- DO NOT accept Base64 payloads larger than the configured limit (default 10 MB) — reject with `NOT_UNDERSTOOD` and `ERR_PAYLOAD_TOO_LARGE`.

## 5. Project Layout & Packaging Standards (Follows Official Python Packaging Guide)

The library MUST follow the modern, community-standard `src/` layout (hatchling/setuptools compatible) so it is immediately acceptable on PyPI, conda-forge, and in corporate environments.

agenlang/
├── pyproject.toml          # core + optional extras
├── README.md
├── LICENSE
├── docs/
│   └── agent-card-example.md
├── src/
│   └── agenlang/
│       ├── init.py
│       ├── identity.py
│       ├── schema.py
│       ├── transport/
│       │   ├── init.py
│       │   └── base.py
│       │   └── brokers/     # optional, only when [brokers] installed
│       ├── core.py          # BaseAgent
│       ├── contracts.py     # new module
│       ├── negotiation.py
│       ├── economy.py
│       ├── bridge.py
│       ├── observability/   # optional extra
│       └── discovery.py
├── tests/
│   ├── unit/
│   └── integration/         # multi-agent CNP tests
├── examples/
│   ├── simple_agent.py
│   └── mcp_bridge_demo.py
└── .agenlang/               # runtime dir (git-ignored)
├── keys/
├── agents/<agent-id>/
            └── session.db (per-agent)


- Use `hatchling` or `setuptools` as build backend (both supported).  
- Entry point for CLI: `agenlang = agenlang.cli:main`  
- All public API exposed via `src/agenlang/__init__.py` (e.g. `from agenlang import BaseAgent`).  
- This layout is the exact same pattern used by FastAPI, pydantic, httpx, and every top-tier library — zero ecosystem friction.

## 6. The AgenLang "Iron Rules" (Non-Negotiable)
To maintain the integrity of the protocol as a universal standard, the implementation must adhere to these seven rules:
    1. Build the Identity first (identity.py and schema.py), do not build the transport until the JCS-signing is 100% verified.
    2. Strict Async-Only: The library MUST NOT use `time.sleep` or blocking I/O (like `requests`). All network and disk operations must use `asyncio`, `httpx`, and `aiosqlite`.
    3. No Plaintext over Wire: The library must refuse to send or receive messages over unencrypted channels (HTTP). Security by default is the only way to ensure corporate adoption.
    4. The Signature is Law: Any message where the JCS-canonicalized hash does not match the DID signature must be immediately dropped and logged as a security event. No "partial trust" or "grace periods."
    5. Schema & Identity Rigidity: Agents MUST NOT respond to messages that do not validate against the Pydantic schema or originate from a DID blocked by a local whitelist. The `BaseAgent` MUST verify signatures prior to processing large payloads to mitigate resource exhaustion.
    6. Joule Atomicity: No internal ledger updates may occur until a `Task` reaches a terminal state (`COMPLETED` or `FAILED`). This prevents "double-spending" or "payment-for-nothing" scenarios in the economic simulation.
    7. No Persistent Zombies: The system MUST NOT allow a 'PENDING' economic state to exist indefinitely. Every Joule reservation must be bound by a mandatory timeout; once expired, the budget is reclaimed and the associated Task is transitioned to `FAILED` with the error `ERR_TASK_TIMEOUT`.