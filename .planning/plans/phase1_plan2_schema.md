# Plan 2: Schema Module

**Phase:** 1  
**Priority:** Critical (depends on Identity)  
**Requirements:** SCH-01, SCH-02, SCH-03, SCH-04, SCH-05, SCH-06

---

## Description

Implements the message envelope schema with all FIPA-ACL performatives, version negotiation, binary data support, payload limits, and the error registry. This defines the wire format for all agent communication.

---

## Requirements Covered

| Requirement | Description |
|-------------|-------------|
| SCH-01 | Message envelope includes: protocol_version, message_id, sender_did, receiver_did, nonce, timestamp, expires_at, trace_id, parent_contract_id, conversation_id, reply_with, in_reply_to, signature |
| SCH-02 | Support all FIPA-ACL performatives: REQUEST, PROPOSE, ACCEPT-PROPOSAL, REJECT-PROPOSAL, INFORM, AGREE, REFUSE, FAILURE, CANCEL, CFP, NOT_UNDERSTOOD |
| SCH-03 | NOT_UNDERSTOOD includes protocol_meta with min_version and max_version for version negotiation |
| SCH-04 | Content supports payload_encoding and media_type fields for binary data |
| SCH-05 | Base64 payloads limited to 10 MB with NOT_UNDERSTOOD response on overflow |
| SCH-06 | Error registry enum includes: ERR_CAPABILITY_MISMATCH, ERR_INSUFFICIENT_JOULES, ERR_PAYLOAD_TOO_LARGE, ERR_TASK_TIMEOUT, ERR_JOULE_VALIDATION_FAILED |

---

## Success Criteria

1. **Message envelope includes all required fields**
   - Pydantic model validates all 13 envelope fields
   - All fields have appropriate types and validators

2. **All FIPA-ACL performatives supported**
   - Enum includes all 11 performatives
   - Each performative maps to appropriate content schema

3. **Version negotiation via NOT_UNDERSTOOD**
   - NOT_UNDERSTOOD payload includes protocol_meta block
   - Contains min_version and max_version in semver format

4. **Binary data support**
   - Content schema includes payload_encoding field (default: identity)
   - Includes media_type field for MIME type indication

5. **Payload size limits enforced**
   - 10 MB limit on Base64 payloads (configurable)
   - Raises validation error with ERR_PAYLOAD_TOO_LARGE code

6. **Error registry available**
   - Enum includes all 5 error codes
   - Error codes used in REFUSE/FAILURE performatives

---

## Implementation Tasks

### Task 2.1: Message Envelope Schema

```
Location: src/agenlang/schema.py
```

1. Create `MessageEnvelope` Pydantic model with fields:
   - `protocol_version: str` - semver format "0.1.0"
   - `message_id: str` - prefixed UUID format "msg_..."
   - `sender_did: str` - did:key format
   - `receiver_did: str` - did:key format
   - `nonce: str` - 32-byte hex (secrets.token_hex(32))
   - `timestamp: datetime` - ISO 8601 with Z suffix, millisecond precision
   - `expires_at: datetime` - ISO 8601 with Z suffix
   - `trace_id: str` - prefixed UUID for distributed tracing
   - `parent_contract_id: str | None` - "ctr_..." prefix
   - `conversation_id: str | None` - "conv_..." prefix
   - `reply_with: str | None` - correlation ID for replies
   - `in_reply_to: str | None` - references original message
   - `signature: str` - base64url-encoded Ed25519 signature

2. Add validators:
   - Timestamp must be UTC with 'Z' suffix
   - expires_at must be > timestamp
   - DID format validation

### Task 2.2: FIPA-ACL Performatives

1. Create `Performative` enum with all 11 values:
   - REQUEST, PROPOSE, ACCEPT-PROPOSAL, REJECT-PROPOSAL
   - INFORM, AGREE, REFUSE, FAILURE, CANCEL
   - CFP, NOT_UNDERSTOOD

2. Create base `MessageContent` Pydantic model with:
   - `performative: Performative`
   - `content: dict` - flexible payload
   - `payload_encoding: str = "identity"` - for binary data
   - `media_type: str | None` - MIME type

3. Create specific content models per performative:
   - `CfpContent` - task description, constraints
   - `ProposeContent` - proposal with pricing, TTL, max_rounds
   - `AcceptProposalContent` - proposal_id reference
   - `RejectProposalContent` - proposal_id + reason
   - `InformContent` - result data
   - `AgreeContent` - agreement confirmation
   - `RefuseContent` - error_code from registry
   - `FailureContent` - error_code + details
   - `CancelContent` - contract_id to cancel
   - `NotUnderstoodContent` - protocol_meta for version negotiation

### Task 2.3: Version Negotiation

1. Create `ProtocolMeta` model:
   - `min_version: str` - semver format
   - `max_version: str` - semver format

2. Integrate into `NotUnderstoodContent`:
   ```python
   class NotUnderstoodContent(MessageContent):
       protocol_meta: ProtocolMeta
       reason: str
   ```

### Task 2.4: Binary Data Support

1. Add fields to `MessageContent`:
   - `payload_encoding: Literal["identity", "base64"] = "identity"`
   - `media_type: str | None = None` - e.g., "application/pdf"

2. Create validator for payload size:
   ```python
   @field_validator('content')
   @classmethod
   def validate_payload_size(cls, v):
       if v.get('payload_encoding') == 'base64':
           payload = v.get('data', '')
           if len(payload) > 10 * 1024 * 1024:  # 10 MB
               raise ValueError('ERR_PAYLOAD_TOO_LARGE')
       return v
   ```

### Task 2.5: Error Registry

1. Create `ErrorCode` enum:
   ```python
   class ErrorCode(str, Enum):
       ERR_CAPABILITY_MISMATCH = "ERR_CAPABILITY_MISMATCH"
       ERR_INSUFFICIENT_JOULES = "ERR_INSUFFICIENT_JOULES"
       ERR_PAYLOAD_TOO_LARGE = "ERR_PAYLOAD_TOO_LARGE"
       ERR_TASK_TIMEOUT = "ERR_TASK_TIMEOUT"
       ERR_JOULE_VALIDATION_FAILED = "ERR_JOULE_VALIDATION_FAILED"
   ```

2. Integrate into `RefuseContent` and `FailureContent`:
   ```python
   class RefuseContent(MessageContent):
       error_code: ErrorCode
       details: dict | None = None
   ```

### Task 2.6: YAML Serialization

1. Create serialization helpers:
   - `serialize_envelope(envelope: MessageEnvelope, content: MessageContent) -> str`
   - `deserialize_envelope(data: str) -> tuple[MessageEnvelope, MessageContent]`

2. Use `yaml.safe_load()` for parsing, custom encoder for serialization
3. Ensure round-trip: YAML → Pydantic → YAML produces identical output

### Task 2.7: Integration Tests

1. Test envelope validation with all fields
2. Test each performative serialization/deserialization
3. Test version negotiation payload
4. Test payload size validation
5. Test error code enum in REFUSE/FAILURE

---

## Dependencies

- `pydantic` v2 - Schema validation
- `pyyaml` - YAML serialization
- `rfc8785` - Already in Identity plan

---

## Files to Create/Modify

- `src/agenlang/schema.py` - Main schema module
- `src/agenlang/__init__.py` - Export schema classes
- `tests/unit/test_schema.py` - Unit tests

---

## Notes

- Schema must be fully validated BEFORE signature verification (security)
- Lazy payload validation: verify signature before decoding large payloads
- All timestamps in UTC with millisecond precision
