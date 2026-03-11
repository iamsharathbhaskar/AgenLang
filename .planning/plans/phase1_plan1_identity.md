# Plan 1: Identity Module

**Phase:** 1  
**Priority:** Critical (blocks all other plans)  
**Requirements:** ID-01, ID-02, ID-03, ID-04, ID-05

---

## Description

Implements the identity layer using Ed25519 keys with did:key format and RFC 8785 canonicalized JSON signing. This is the foundational security layer - all messages depend on correct signing/verification.

---

## Requirements Covered

| Requirement | Description |
|-------------|-------------|
| ID-01 | Agent can generate Ed25519 key pair and create did:key identifier |
| ID-02 | Agent can securely store private keys in OS keyring or encrypted file |
| ID-03 | Agent can sign messages using RFC 8785 canonicalized JSON |
| ID-04 | Agent can verify incoming message signatures |
| ID-05 | DID format follows multicodec prefix 0xed01 + multibase base58btc encoding |

---

## Success Criteria

1. **Agent can generate Ed25519 key pair and create did:key identifier**
   - Generate cryptographically secure Ed25519 key pair
   - Encode public key with multicodec prefix 0xed01 + multibase base58btc
   - Resulting DID matches format: `did:key:z6Mk...`

2. **Agent can securely store private keys**
   - Private key stored in OS keyring via `keyring` package
   - Fallback to encrypted file with passphrase if keyring unavailable
   - Key path: `~/.agenlang/keys/<agent-id>.key`

3. **Agent can sign messages using RFC 8785 canonicalized JSON**
   - Parse YAML → dict → rfc8785.canonicalize() → SHA256 → Ed25519 sign
   - Signature format: base64url-encoded detached signature
   - All envelope fields except `signature` are included in signing payload

4. **Agent can verify incoming message signatures**
   - Extract sender DID → resolve to public key
   - Canonicalize envelope+content (excluding signature field)
   - Verify Ed25519 signature, reject if invalid

---

## Implementation Tasks

### Task 1.1: Key Generation & DID Creation

```
Location: src/agenlang/identity.py
```

1. Create `generate_keypair() -> Ed25519PrivateKey, Ed25519PublicKey`
   - Use `cryptography.hazmat.primitives.asymmetric.ed25519.Ed25519PrivateKey.generate()`

2. Create `create_did_key(public_key: Ed25519PublicKey) -> str`
   - Apply multicodec prefix 0xed01 to public key bytes
   - Encode with multibase base58btc encoding
   - Format: `did:key:z6Mk...`

3. Create `load_or_generate_key(agent_id: str) -> tuple[Ed25519PrivateKey, str]`
   - Check if key exists in keyring/storage
   - Generate new if not found
   - Return private key + DID

### Task 1.2: Key Storage

1. Implement `KeyStorage` class with methods:
   - `store(agent_id: str, private_key: Ed25519PrivateKey)` - save to keyring/encrypted file
   - `load(agent_id: str) -> Ed25519PrivateKey` - retrieve from storage
   - `delete(agent_id: str)` - remove key
   - `exists(agent_id: str) -> bool` - check if key exists

2. Use `keyring` package for OS keyring integration
3. Fallback: encrypt with AES-GCM using passphrase from env var `AGENT_KEY_PASSPHRASE`

### Task 1.3: RFC 8785 Signing

1. Create `canonicalize_for_signing(envelope: dict, content: dict) -> bytes`
   - Remove `signature` from envelope copy
   - Merge envelope + content into single dict
   - Apply `rfc8785.canonicalize()` for deterministic output
   - Return UTF-8 bytes

2. Create `sign_message(private_key: Ed25519PrivateKey, envelope: dict, content: dict) -> str`
   - Canonicalize payload
   - SHA256 hash of canonicalized bytes
   - Sign with Ed25519 private key
   - Return base64url-encoded signature

### Task 1.4: Signature Verification

1. Create `verify_signature(signature_b64: str, envelope: dict, content: dict, did: str) -> bool`
   - Parse DID to extract public key bytes (reverse did:key encoding)
   - Canonicalize envelope+content
   - Decode base64url signature
   - Verify with Ed25519 public key

2. Create helper `extract_public_key_from_did(did: str) -> Ed25519PublicKey`
   - Parse `did:key:z6Mk...` format
   - Strip multibase prefix, decode base58btc
   - Strip multicodec prefix 0xed01
   - Reconstruct public key

### Task 1.5: Integration Tests

1. Test key generation produces valid did:key format
2. Test signing/verification round-trip
3. Test signature rejection on tampered content
4. Test key storage round-trip (keyring + fallback)

---

## Dependencies

- `cryptography` - Ed25519 key operations
- `keyring` - OS keyring integration
- `rfc8785` - JSON canonicalization
- `base58` - multibase encoding

---

## Files to Create/Modify

- `src/agenlang/identity.py` - Main identity module
- `src/agenlang/__init__.py` - Export identity classes
- `tests/unit/test_identity.py` - Unit tests

---

## Notes

- Nonce generation for messages must use `secrets.token_hex(32)`, not `random`
- All timestamps must be ISO 8601 with millisecond precision and 'Z' suffix
