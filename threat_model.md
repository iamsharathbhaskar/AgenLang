# AgenLang Threat Model

NIST-aligned threat matrix for AgenLang contract and settlement layer.
Mapped to NIST SP 800-53 Rev. 5 control families.

## Threat Matrix

| # | Threat | NIST Control Family | Impact | Likelihood | Current Mitigation | Residual Risk |
|---|--------|-------------------|--------|------------|-------------------|---------------|
| T1 | **Replay Attack** — Re-submission of a previously executed contract to trigger duplicate settlement | AU-10 (Non-repudiation), SC-13 (Cryptographic Protection) | High | Medium | HMAC-SHA256 on SER replay file; unique `execution_id` per run; `contract_id` URN pattern prevents reuse | Low — attacker would need SER key to forge valid HMAC |
| T2 | **Goal Hijacking** — Modifying the contract goal after user signs the intent anchor | SI-7 (Software/Information Integrity), AU-10 | Critical | Low | Intent anchor hash (`sha256`) binds user goal; ECDSA contract signature covers full payload including goal | Very Low — requires compromising both intent anchor and issuer private key |
| T3 | **Contract Tampering** — Altering workflow steps, constraints, or settlement after signing | SC-13, SI-7 | Critical | Medium | ECDSA P-256 canonical signature over full contract (excluding proof field); `verify_signature()` on load | Low — any field change invalidates signature |
| T4 | **DoS via Joule Exhaustion** — Malicious contract with excessive budget draining compute resources | SC-5 (Denial of Service Protection), AC-6 (Least Privilege) | Medium | Medium | `joule_budget` hard cap in constraints; per-step metering with budget check before each step; `max_usd` optional ceiling | Medium — budget is set by contract issuer; no global rate limiting yet |
| T5 | **Key Compromise** — Private key stolen from `~/.agenlang/keys.pem` | SC-12 (Cryptographic Key Management), IA-5 (Authenticator Management) | Critical | Low | File permissions `0o600`; configurable `AGENLANG_KEY_DIR`; key rotation support via `KeyManager.generate()` | Medium — no HSM/Vault integration; plaintext PEM on disk |
| T6 | **Memory Exfiltration** — Unauthorized access to handoff data or SER memory | SC-28 (Protection of Information at Rest), MP-5 (Media Transport) | High | Medium | AES-256-GCM encrypted memory backend (default); GDPR `purge_on_complete`; `pii_level` constraints; `data_subject` tracking | Low — encryption key derived from SER key; memory purged after execution |
| T7 | **Supply-Chain Attack (Tool Poisoning)** — Malicious tool registered in `TOOLS` registry executes arbitrary code | SA-12 (Supply Chain Protection), CM-7 (Least Functionality) | Critical | Low | Capability attestation proofs required per tool; tool registry is explicit (not auto-discovery); `capabilities` whitelist check before execution | Medium — attestation proofs are not yet verified against a CA |
| T8 | **Man-in-the-Middle** — Interception of A2A messages during transit | SC-8 (Transmission Confidentiality), SC-23 (Session Authenticity) | High | Medium | HTTPS transport for A2A adapter; A2A JSON-RPC has contract signature | Low — transport encryption + payload signing provides defense-in-depth |
| T9 | **Unauthorized Settlement** — Triggering settlement without valid execution | AU-12 (Audit Record Generation), AC-3 (Access Enforcement) | High | Low | Signed ledger entries tied to SER execution_id; per-step ECDSA signatures; SER records full audit trail | Low — requires valid KeyManager and execution context |
| T10 | **API Key Leakage** — Embedded API keys in contract JSON exposing secrets | SC-28 (Protection of Information at Rest), IA-5 (Authenticator Management) | High | Medium | Regex-based leak prevention in `Contract.from_dict()` and `Contract.model_validate()`; rejects contracts with key-like patterns | Low — validation runs before any execution |
| T11 | **Issuer Identity Spoofing** — Attacker uses a valid signature but a forged `agent_id` to impersonate another agent | IA-8 (Identification and Authentication), SC-13 (Cryptographic Protection) | Critical | Medium | `issuer.agent_id` MUST be a DID:key derived from `issuer.pubkey` via `derive_did_key()`; `verify_signature()` rejects DID/pubkey mismatch; `from_dict()` rejects signed contracts with non-DID agent_id | Low — spoofing requires the victim's private key to derive matching DID |

## Trust Boundaries

```
+------------------+     HTTPS/TLS      +------------------+
|  Local Agent     | <================> |  Remote Agent    |
|  (AgenLang RT)   |                    |  (A2A)           |
+--------+---------+                    +------------------+
         |
   +-----v------+
   | KeyManager  |  <-- Trust boundary: filesystem access
   | keys.pem    |
   | ser.key     |
   +-----+------+
         |
   +-----v------+
   | Encrypted   |  <-- Trust boundary: memory isolation
   | Memory      |
   | (AES-GCM)   |
   +-------------+
```

## Mitigation Code References

| Threat | Mitigation | File |
|--------|-----------|------|
| T1 Replay Attack | HMAC-SHA256 on SER replay data | `runtime.py` `_save_replay()` |
| T1 Replay Attack | SER key derivation | `keys.py` `get_ser_key()` |
| T2 Goal Hijacking | Intent anchor hash binding | `contract.py` `sign()` canonical payload |
| T3 Contract Tampering | ECDSA signature verification | `contract.py` `verify_signature()` |
| T4 DoS / Joule Exhaustion | Budget check per step | `runtime.py` `_run_sequence()` budget check |
| T5 Key Compromise | File permission 0o600 | `keys.py` key file creation |
| T6 Memory Exfiltration | AES-256-GCM encryption | `memory.py` `EncryptedMemoryBackend` |
| T7 Tool Poisoning | Capability attestation check | `runtime.py` `_execute_step()` capability whitelist |
| T8 Man-in-the-Middle | A2A contract signature | `a2a.py` `contract_to_a2a_payload()` |
| T9 Unauthorized Settlement | Signed ledger entries | `settlement.py` `SignedLedger.append_entry()` |
| T10 API Key Leakage | Regex leak prevention | `contract.py` `_check_for_leaked_keys()` |
| T11 Issuer Identity Spoofing | DID:key identity binding and verification | `contract.py` `verify_signature()`, `keys.py` `derive_did_key()` |
| All | Retry with backoff (network resilience) | `utils.py` `retry_with_backoff()` |

## Recommendations for Future Hardening

1. **HSM/Vault integration** for key storage (addresses T5 residual risk)
2. **Certificate Authority** for capability attestation proofs (addresses T7)
3. **Global rate limiting** per agent identity (addresses T4)
4. **Mutual TLS** for protocol adapter transport (addresses T8)
5. **Formal verification** of workflow state machine via TLA+ spec (addresses T2, T3)
