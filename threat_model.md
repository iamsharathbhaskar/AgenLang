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
| T8 | **Man-in-the-Middle** — Interception of A2A/ACP/ANP messages during transit | SC-8 (Transmission Confidentiality), SC-23 (Session Authenticity) | High | Medium | HTTPS transport for all protocol adapters; ANP envelopes include DID-based signatures; A2A JSON-RPC has contract signature | Low — transport encryption + payload signing provides defense-in-depth |
| T9 | **Unauthorized Settlement** — Triggering settlement without valid execution | AU-12 (Audit Record Generation), AC-3 (Access Enforcement) | High | Low | Settlement receipt tied to SER execution_id; `HeliumBackend` requires `HELIUM_API_KEY`; SER records full audit trail | Low — requires both API key and valid execution context |
| T10 | **DID Spoofing** — Forging a DID to impersonate another agent in ANP/W3C exchanges | IA-8 (Identification and Authentication), IA-12 (Identity Proofing) | High | Low | DID:key derived from ECDSA public key (cryptographically bound); ANP envelope signatures verified against sender DID | Low — DID is mathematically tied to key pair |

## Trust Boundaries

```
+------------------+     HTTPS/TLS      +------------------+
|  Local Agent     | <================> |  Remote Agent    |
|  (AgenLang RT)   |                    |  (ACP/ANP/A2A)   |
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

## Recommendations for Future Hardening

1. **HSM/Vault integration** for key storage (addresses T5 residual risk)
2. **Certificate Authority** for capability attestation proofs (addresses T7)
3. **Global rate limiting** per agent identity (addresses T4)
4. **Mutual TLS** for protocol adapter transport (addresses T8)
5. **Formal verification** of workflow state machine via TLA+ spec (addresses T2, T3)
