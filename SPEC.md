# AgenLang Specification v0.4.1

## 1. Introduction

AgenLang defines a contract format and execution model for secure, auditable, economically fair inter-agent communication. The contract serves as a universal delegation layer on top of the Linux Foundation A2A (Agent-to-Agent) protocol. Personal agents (OpenClaw/Amazo-style) and ZHC swarms use AgenLang contracts to delegate tasks with cryptographic guarantees, Joule metering, and a verifiable Structured Execution Record (SER).

Scope: contract format, signing and verification, SER structure, signed ledger, A2A integration, and security requirements. The JSON schema at `schema/v1.0.json` is the machine-readable reference; this document is the authoritative human-readable specification.

---

## 2. Contract Format

A valid AgenLang contract MUST conform to the v1.0 schema. All fields below are required unless marked optional.

### 2.1 Root Fields

- **agenlang_version** (MUST): String literal `"1.0"`.
- **contract_id** (MUST): URN of the form `urn:agenlang:exec:` followed by exactly 32 lowercase hexadecimal characters. Uniquely identifies the contract and prevents replay.
- **issuer** (MUST): Object containing `agent_id`, `pubkey`, and optionally `proof` (set after signing). When signed (`proof` present), `agent_id` MUST be a DID:key (format `did:key:z&lt;base58btc&gt;`) derived from the signing key and MUST match the public key in `pubkey`.
- **goal** (MUST): Human-readable description of the delegation intent.
- **intent_anchor** (MUST): Object with `hash` (MUST) and optional `user_signature`. Binds user intent; the hash SHOULD cover the goal and critical constraints.
- **constraints** (MUST): Object with `joule_budget` (MUST, non-negative), optional `max_usd`, `pii_level` (enum: none, minimal, gdpr_standard, hipaa), and optional `ethical` array.
- **workflow** (MUST): Object with `type` (MUST be `"sequence"`) and `steps` (MUST, non-empty array). Optional `on_error` for workflow-level error handling.
- **memory_contract** (MUST): Object with `handoff_keys` (array of strings), `ttl` (MUST match pattern `\d+[smhd]`), optional `purge_on_complete` (default true), optional `data_subject`.
- **settlement** (MUST): Object with `joule_recipient`, `rate` (non-negative), optional `micro_payment_address`.
- **capability_attestations** (MUST): Array of objects, each with `capability` and `proof`. Optional `scope` per attestation.
- **ser_config** (optional): Object with `redaction` (enum), `replay_enabled` (default true).
- **ser** (optional): Populated after execution; holds the Structured Execution Record.

### 2.2 Workflow Steps

Each step MUST have:
- **action** (MUST): One of `tool`, `skill`, `subcontract`, `embed`.
- **target** (MUST): String identifying the tool, skill, or protocol target (e.g. `web_search`, `a2a:agent-id`).
- **args** (optional): Object of key-value arguments. MAY contain `{{step_N_output}}` placeholders resolved from prior step outputs.
- **on_error** (optional): Error handler with `retry`, `fallback`, `escalate_to`, `notify_intent_anchor`.

### 2.3 Validation Rules

- Contracts MUST NOT contain embedded API key patterns (see Section 7). Validation MUST reject such contracts before any execution.
- Schema validation MUST pass before a contract is accepted for signing or execution.

---

## 3. Signing and Verification

### 3.1 Algorithm

- Signing MUST use ECDSA with P-256 (SECP256R1) and SHA-256.
- The canonical payload for signing is the contract JSON with keys sorted, compact representation (no extra whitespace), with the `issuer.proof` field excluded.
- The signature MUST be Base64-encoded and stored in `issuer.proof`.
- The public key used for verification MUST be stored in `issuer.pubkey` as PEM-encoded SubjectPublicKeyInfo.

### 3.2 Issuer Identity (DID:key)

- When signing, `issuer.agent_id` MUST be set to the DID:key derived from the KeyManager's public key via `derive_did_key()`.
- The DID:key format MUST follow the W3C did:key spec: `did:key:z` + base58btc(multicodec(0x1200) + compressed P-256 public key).
- Verification MUST confirm that `issuer.agent_id` matches the DID derived from `issuer.pubkey`; mismatch MUST cause verification to fail.

### 3.3 KeyManager Rules

- KeyManager MUST persist the private key to a configurable path (default `~/.agenlang/keys.pem`). The `AGENLANG_KEY_DIR` environment variable MAY override the base directory.
- Key files MUST be created with permissions `0o600`.
- KeyManager MUST provide: `derive_did_key() -> str`, `sign(data) -> signature`, `verify(data, signature, public_key_pem) -> bool`, `get_public_key_pem() -> bytes`, and a SER key for HMAC (derived or stored separately).
- Key rotation is supported by calling `generate()`; existing signed contracts remain verifiable with their original `issuer.pubkey`.

### 3.4 Verification

- `verify_signature()` MUST return false if `issuer.proof` is missing or invalid.
- Verification MUST use the same canonical payload construction as signing.
- `verify_signature()` MUST return false if `issuer.agent_id` is not a valid DID:key or does not match the DID derived from `issuer.pubkey`.
- Issuer cert chain validation is out of scope for v0.4.0; production implementations SHOULD validate that `issuer.pubkey` is from a trusted chain.

---

## 4. Structured Execution Record (SER)

The SER is produced after contract execution and MUST contain the following structure.

### 4.1 Required Fields

- **execution_id**: Same as `contract_id` for the executed contract.
- **timestamps**: Object with `start` and `end` in ISO 8601 format with Z suffix.
- **resource_usage**: Object with `joules_used`, `usd_cost`, `efficiency_score`.
- **decision_points**: Array of objects with `type`, `location`, `rationale`, `chosen` (for conditional skips, etc.).
- **safety_checks**: Object with `capability_violations`, `intent_anchor_verified`.
- **replay_ref**: Reference to the replay file (e.g. `{execution_id}.replay`).
- **reputation_score**: Float in [0, 1] derived from budget utilization.
- **settlement_receipt**: Object with `joule_recipient`, `rate`, `total_joules_owed`.
- **ledger_entries**: Array of signed ledger entries (see Section 5).

### 4.2 HMAC Protection

- Replay data (step outputs) MUST be persisted to a replay file.
- The replay file MUST be protected with HMAC-SHA256. The HMAC key MUST be derived from or stored alongside the KeyManager (e.g. `ser.key`).
- Verification of replay integrity MUST use the same key. Replay verification MUST fail if the HMAC does not match.

### 4.3 Replay File Format

- Content: JSON-encoded array of step results.
- Append: Raw HMAC-SHA256 digest (binary) appended to the JSON bytes.
- Verification: Recompute HMAC over the JSON portion and compare with the appended digest.

---

## 5. Ledger

The ledger implements a signed double-entry model for Joule settlement.

### 5.1 Ledger Entry Structure

Each entry MUST have:
- **entry_type**: `"debit"` or `"credit"`.
- **amount_joules**: Non-negative float.
- **recipient**: String identifying the Joule recipient.
- **timestamp**: ISO 8601 string with Z suffix.
- **signature**: Hex-encoded ECDSA signature over the canonical payload.

### 5.2 Canonical Payload for Ledger Entry

The payload signed is: `{entry_type}|{amount_joules}|{recipient}|{timestamp}`. The same ECDSA P-256 + SHA-256 algorithm as contract signing applies.

### 5.3 Append Rules

- One ledger entry MUST be appended per completed workflow step (debit for the Joule cost).
- The recipient MUST be the contract's `settlement.joule_recipient`.
- Signing MUST use the KeyManager associated with the execution.

### 5.4 Verification

- `verify_all(km)` MUST verify every entry's signature using the KeyManager's public key.
- Tampered entries (e.g. altered amount or recipient) MUST fail verification.

### 5.5 Balance Verification

- The sum of debits SHOULD equal `resource_usage.joules_used` in the SER.
- Balance verification is advisory; the authoritative record is the signed ledger itself.

### 5.6 Canonical Joule Formula

The canonical definition for Joule measurement is:

**1 Joule = (input_tokens × 0.0001) + (output_tokens × 0.0003) + (wall_clock_seconds × 0.01)**

Implementations MUST use this formula when token counts and wall-clock time are available. When token counts are unavailable, implementations MAY use a fallback (e.g. tool-registry joule_cost) but SHOULD document the fallback.

---

## 6. A2A Integration

AgenLang contracts are wrapped for transport via the Linux Foundation A2A protocol.

### 6.1 JSON-RPC Payload

- The contract MUST be wrapped as a JSON-RPC 2.0 message.
- Method: `agenlang/execute`.
- Params MUST include `@type: "AgenLangContract"`, `@id` (contract_id), `agenlang_version`, and `contract` (the full contract object).
- The `id` field of the JSON-RPC message SHOULD be the contract_id.

### 6.2 Server-Sent Events (SSE)

- For streaming transport, the contract MAY be formatted as an SSE event.
- Event type: `agenlang`.
- Data: JSON string of the same JSON-RPC payload as above.
- Parsing MUST extract the `data:` line and parse the JSON to recover the contract.

### 6.3 Extraction

- Extraction from an A2A payload MUST locate the inner contract in `params.contract` or `params.agenlang_contract` or `params` itself.
- The extracted object MUST be validated via `Contract.model_validate()` before use.

---

## 7. Security Requirements

### 7.1 No Embedded Keys

- Contracts MUST NOT contain embedded API key patterns. Implementations MUST scan for patterns (e.g. OpenAI `sk-`, Anthropic `sk-ant-`, xAI `xai-`, Tavily `tvly-`, generic secret patterns) before accepting a contract.
- Validation MUST raise an error and reject the contract if a match is found.

### 7.2 Memory Encryption and Purge

- The default memory backend MUST use AES-256-GCM encryption.
- The encryption key MUST be derived from or tied to the KeyManager SER key.
- If `memory_contract.purge_on_complete` is true, memory MUST be purged after successful execution.
- Handoff data MUST be whitelisted by `memory_contract.handoff_keys`; only those keys MAY be persisted.

### 7.3 Threat Model Summary

- **Replay**: HMAC-protected replay file; unique contract_id URN.
- **Goal hijacking**: Intent anchor hash; ECDSA signature covers full payload.
- **Contract tampering**: ECDSA verification on load; any field change invalidates signature.
- **DoS (Joule exhaustion)**: `joule_budget` hard cap; per-step budget check.
- **Key compromise**: File permissions; configurable key path; key rotation support.
- **Memory exfiltration**: AES-GCM encryption; purge on complete; PII level constraints.
- **Tool poisoning**: Capability attestation required; explicit tool registry; whitelist check.
- **Man-in-the-middle**: HTTPS for A2A; contract signature in payload.
- **Unauthorized settlement**: Signed ledger entries; SER audit trail.
- **API key leakage**: Regex-based rejection at validation.

See `threat_model.md` for the full NIST-aligned matrix and mitigation references.

---

## 8. Versioning

Changes to this specification require a proposal process. Proposals MUST be documented (e.g. in an issue or design doc), reviewed, and approved before incorporation. Breaking changes to the contract format, signing algorithm, or SER structure MUST result in a new major schema version. Patch-level updates (clarifications, non-breaking additions) MAY be applied to the current version with changelog entries.
