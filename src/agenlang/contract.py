"""AgenLang Contract - loads and validates the v1.0 schema.

This module provides the Contract model and validation against the
AgenLang v1.0 JSON schema. Supports ECDSA signing and verification.
"""

import base64
import importlib.resources
import json
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, Optional

from jsonschema import ValidationError, validate  # type: ignore[import-untyped]
from pydantic import BaseModel, Field

from .keys import derive_did_from_pubkey
from .models import (
    CapabilityAttestation,
    Constraints,
    IntentAnchor,
    Issuer,
    MemoryContract,
    Receiver,
    SerConfig,
    Settlement,
    Workflow,
)

if TYPE_CHECKING:
    from .keys import KeyManager

_DID_KEY_PATTERN = re.compile(r"^did:key:z[1-9A-HJ-NP-Za-km-z]+$")

_KEY_PATTERNS = [
    re.compile(r"sk-[a-zA-Z0-9]{20,}"),
    re.compile(r"sk-ant-[a-zA-Z0-9]{20,}"),
    re.compile(r"xai-[a-zA-Z0-9]{20,}"),
    re.compile(r"tvly-[a-zA-Z0-9]{20,}"),
    re.compile(r"[A-Za-z0-9]{32,}_secret_[A-Za-z0-9]+"),
]


def _check_for_leaked_keys(data: Dict[str, Any]) -> None:
    """Raise ValueError if the contract data contains API key patterns."""
    text = json.dumps(data)
    for pattern in _KEY_PATTERNS:
        if pattern.search(text):
            raise ValueError(
                "Contract contains embedded API key pattern — "
                "remove before submitting"
            )


def _load_schema() -> dict:
    """Load schema from package resources."""
    schema_ref = importlib.resources.files("agenlang") / "schema" / "v1.0.json"
    with importlib.resources.as_file(schema_ref) as path:
        return json.loads(path.read_text())


class Contract(BaseModel):
    """AgenLang v1.0 Contract - the core object agents exchange.

    Attributes:
        agenlang_version: Schema version (always "1.0").
        contract_id: URN identifier (urn:agenlang:exec:<32 hex chars>).
        issuer: Issuer agent identity and public key.
        goal: Human-readable goal description.
        intent_anchor: Hash anchoring user intent.
        constraints: Joule budget, PII level, etc.
        workflow: Steps and execution type.
        memory_contract: Handoff keys and TTL.
        settlement: Joule recipient and rate.
        capability_attestations: Capability proofs.
        ser_config: SER redaction and replay options.
        ser: Optional execution record (populated after run).
    """

    agenlang_version: str = "1.0"
    contract_id: str
    issuer: Issuer
    receiver: Receiver
    goal: str
    intent_anchor: IntentAnchor
    constraints: Constraints
    workflow: Workflow
    memory_contract: MemoryContract
    settlement: Settlement
    capability_attestations: list[CapabilityAttestation]
    ser_config: SerConfig = Field(default_factory=SerConfig)
    ser: Optional[Dict[str, Any]] = None

    @classmethod
    def model_validate(cls, obj: Any, **kwargs: Any) -> "Contract":  # type: ignore[override]
        """Validate with API key leak check."""
        if isinstance(obj, dict):
            _check_for_leaked_keys(obj)
        return super().model_validate(obj, **kwargs)

    @classmethod
    def from_file(cls, path: str) -> "Contract":
        """Load a contract from JSON file and validate against schema.

        Args:
            path: Path to JSON contract file.

        Returns:
            Validated Contract instance.

        Raises:
            ValueError: If JSON is invalid or schema validation fails.
        """
        data = json.loads(Path(path).read_text())
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Contract":
        """Load from dict and validate against schema.

        Args:
            data: Contract as dict (e.g. from JSON parse).

        Returns:
            Validated Contract instance.

        Raises:
            ValueError: If schema validation fails or embedded keys detected.
        """
        _check_for_leaked_keys(data)
        schema = _load_schema()
        try:
            validate(instance=data, schema=schema)
        except ValidationError as e:
            raise ValueError(f"Invalid AgenLang contract: {e.message}") from e
        issuer = data.get("issuer", {})
        if isinstance(issuer, dict) and issuer.get("proof"):
            agent_id = issuer.get("agent_id", "")
            if not _DID_KEY_PATTERN.match(agent_id):
                raise ValueError(
                    "Signed contract requires issuer.agent_id as did:key format"
                )
        return cls.model_validate(data)

    def to_json(self) -> str:
        """Export contract as JSON string.

        Returns:
            Indented JSON representation.
        """
        return self.model_dump_json(indent=2)

    def _canonical_payload(self) -> bytes:
        """Build canonical JSON payload for signing (excludes issuer.proof)."""
        payload = self.model_dump()
        if "issuer" in payload and isinstance(payload["issuer"], dict):
            payload["issuer"] = {
                k: v for k, v in payload["issuer"].items() if k != "proof"
            }
        return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )

    def sign(self, key_manager: "KeyManager") -> None:
        """Sign contract with KeyManager. Sets issuer.agent_id (DID:key), pubkey, proof.

        Args:
            key_manager: KeyManager instance with private key.
        """
        did = key_manager.derive_did_key()
        pubkey_pem = key_manager.get_public_key_pem().decode("utf-8")
        self.issuer = Issuer(agent_id=did, pubkey=pubkey_pem, proof=None)
        payload = self._canonical_payload()
        signature = key_manager.sign(payload)
        self.issuer = Issuer(
            agent_id=did,
            pubkey=pubkey_pem,
            proof=base64.b64encode(signature).decode("ascii"),
        )

    def verify_signature(self) -> bool:
        """Verify issuer signature and DID:key identity binding.

        Requires issuer.agent_id to be a DID:key that matches issuer.pubkey.
        Returns True only if both signature and identity are valid.
        """
        if not self.issuer.proof:
            return False
        if not _DID_KEY_PATTERN.match(self.issuer.agent_id):
            return False
        try:
            signature = base64.b64decode(self.issuer.proof)
        except Exception:
            return False
        pubkey_str = self.issuer.pubkey
        if "\\n" in pubkey_str:
            pubkey_str = pubkey_str.replace("\\n", "\n")
        pubkey_pem = pubkey_str.encode("utf-8")

        derived_did = derive_did_from_pubkey(pubkey_pem)
        if self.issuer.agent_id != derived_did:
            return False

        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.backends import default_backend
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import ec

        try:
            loaded_pub = serialization.load_pem_public_key(
                pubkey_pem, backend=default_backend()
            )
            assert isinstance(loaded_pub, ec.EllipticCurvePublicKey)
            loaded_pub.verify(
                signature, self._canonical_payload(), ec.ECDSA(hashes.SHA256())
            )
            return True
        except (InvalidSignature, Exception):
            return False

    def verify_receiver_key(self, key_manager: "KeyManager") -> bool:
        """Check receiver.pubkey matches executing KeyManager's public key.

        Returns True if receiver.pubkey is absent (any executor accepted)
        or if it matches the KeyManager's PEM public key.
        """
        if not self.receiver.pubkey:
            return True
        km_pubkey = key_manager.get_public_key_pem().decode("utf-8")
        return self.receiver.pubkey.strip() == km_pubkey.strip()
