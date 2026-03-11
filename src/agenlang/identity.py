"""Identity module - DID:key generation and message signing."""

import secrets
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import base58
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.backends import default_backend

import rfc8785

MULTICODEC_ED25519_PUBKEY = bytes.fromhex("ed01")
MULTIBASE_BASE58BTC = "z"


@dataclass
class Identity:
    """Agent identity with DID and key management."""

    did: str
    public_key_bytes: bytes
    private_key: Optional[ed25519.Ed25519PrivateKey] = None
    _key_path: Optional[Path] = field(default=None, repr=False)

    @classmethod
    def generate(cls, agent_id: str) -> "Identity":
        """Generate a new Ed25519 key pair and DID."""
        private_key = ed25519.Ed25519PrivateKey.generate()
        public_key = private_key.public_key()
        public_key_bytes = public_key.public_bytes(
            encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw
        )

        did = generate_did_key(public_key_bytes)

        identity = cls(
            did=did,
            public_key_bytes=public_key_bytes,
            private_key=private_key,
        )

        key_dir = Path.home() / ".agenlang" / "keys"
        key_dir.mkdir(parents=True, exist_ok=True)
        identity._key_path = key_dir / f"{agent_id}.key"

        identity._save_key(private_key, agent_id)

        return identity

    @classmethod
    def load(cls, agent_id: str) -> "Identity":
        """Load identity from storage or generate new if not exists."""
        key_dir = Path.home() / ".agenlang" / "keys"
        key_path = key_dir / f"{agent_id}.key"

        if not key_path.exists():
            return cls.generate(agent_id)

        private_key = cls._load_key(key_path, agent_id)
        public_key = private_key.public_key()
        public_key_bytes = public_key.public_bytes(
            encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw
        )

        did = generate_did_key(public_key_bytes)

        return cls(
            did=did,
            public_key_bytes=public_key_bytes,
            private_key=private_key,
            _key_path=key_path,
        )

    def _save_key(self, private_key: ed25519.Ed25519PrivateKey, agent_id: str) -> None:
        """Save private key to encrypted file."""
        if self._key_path is None:
            key_dir = Path.home() / ".agenlang" / "keys"
            key_dir.mkdir(parents=True, exist_ok=True)
            self._key_path = key_dir / f"{agent_id}.key"

        passphrase = self._get_passphrase()
        if passphrase:
            encrypted = private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.BestAvailableEncryption(passphrase),
            )
        else:
            encrypted = private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption(),
            )

        self._key_path.write_bytes(encrypted)

    @staticmethod
    def _load_key(key_path: Path, agent_id: str) -> ed25519.Ed25519PrivateKey:
        """Load private key from encrypted file."""
        encrypted = key_path.read_bytes()

        passphrase = Identity._get_passphrase()
        try:
            if passphrase:
                private_key = serialization.load_pem_private_key(
                    encrypted, password=passphrase, backend=default_backend()
                )
            else:
                private_key = serialization.load_pem_private_key(
                    encrypted, password=None, backend=default_backend()
                )
        except Exception:
            raise ValueError(f"Failed to load key for agent {agent_id}. Invalid passphrase?")

        return private_key

    @staticmethod
    def _get_passphrase() -> Optional[bytes]:
        """Get passphrase from environment or keyring."""
        import os

        passphrase = os.environ.get("AGENT_KEY_PASSPHRASE")
        if passphrase:
            return passphrase.encode()

        try:
            import keyring

            pw = keyring.get_password("agenlang", "key-passphrase")
            if pw:
                return pw.encode()
        except Exception:
            pass

        return None

    def save(self) -> None:
        """Save identity to storage."""
        if self.private_key and self._key_path:
            self._save_key(self.private_key, self.did.split(":")[-1])

    def sign(self, envelope: dict, content: dict) -> str:
        """Sign a payload using RFC 8785 canonicalization."""
        if not self.private_key:
            raise ValueError("No private key available for signing")

        canonical_bytes = canonicalize_for_signing(envelope, content)
        digest = hashes.Hash(hashes.SHA256())
        digest.update(canonical_bytes)
        message_hash = digest.finalize()

        signature = self.private_key.sign(message_hash)

        import base64

        return base64.urlsafe_b64encode(signature).rstrip(b"=").decode("ascii")

    def verify(self, envelope: dict, content: dict, signature_b64: str) -> bool:
        """Verify a signature."""
        try:
            from cryptography.hazmat.primitives import hashes
            from cryptography.hazmat.primitives.asymmetric import ed25519

            import base64

            public_key_bytes = self.public_key_bytes
            public_key = ed25519.Ed25519PublicKey.from_public_bytes(public_key_bytes)

            canonical_bytes = canonicalize_for_signing(envelope, content)
            digest = hashes.Hash(hashes.SHA256())
            digest.update(canonical_bytes)
            message_hash = digest.finalize()

            signature = base64.urlsafe_b64decode(signature_b64 + "==")

            public_key.verify(signature, message_hash)
            return True
        except Exception:
            return False


def generate_did_key(public_key_bytes: bytes) -> str:
    """Generate did:key from Ed25519 public key using multicodec + multibase."""
    multicodec_encoded = MULTICODEC_ED25519_PUBKEY + public_key_bytes
    base58_btc = base58.b58encode(multicodec_encoded).decode("ascii")
    return f"did:key:{MULTIBASE_BASE58BTC}{base58_btc}"


def parse_did_key(did: str) -> ed25519.Ed25519PublicKey:
    """Parse did:key to extract public key."""
    if not did.startswith("did:key:"):
        raise ValueError(f"Invalid DID format: {did}")

    multibase_encoded = did[8:]

    if not multibase_encoded.startswith(MULTIBASE_BASE58BTC):
        raise ValueError(f"Unsupported multibase encoding: {multibase_encoded[0]}")

    base58_btc = multibase_encoded[1:]
    multicodec_encoded = base58.b58decode(base58_btc)

    if not multicodec_encoded.startswith(MULTICODEC_ED25519_PUBKEY):
        raise ValueError(f"Invalid multicodec prefix")

    public_key_bytes = multicodec_encoded[len(MULTICODEC_ED25519_PUBKEY) :]

    return ed25519.Ed25519PublicKey.from_public_bytes(public_key_bytes)


def canonicalize_for_signing(envelope: dict, content: dict) -> bytes:
    """Canonicalize envelope + content for signing using RFC 8785."""
    signing_payload = {
        "envelope": {k: v for k, v in envelope.items() if k != "signature"},
        "content": content,
    }

    canonical_bytes = rfc8785.dumps(signing_payload)
    return canonical_bytes


def verify_signature(signature_b64: str, envelope: dict, content: dict, did: str) -> bool:
    """Verify a signature from a DID."""
    try:
        public_key = parse_did_key(did)

        canonical_bytes = canonicalize_for_signing(envelope, content)
        digest = hashes.Hash(hashes.SHA256())
        digest.update(canonical_bytes)
        message_hash = digest.finalize()

        import base64

        signature = base64.urlsafe_b64decode(signature_b64 + "==")

        public_key.verify(signature, message_hash)
        return True
    except Exception:
        return False


def generate_nonce() -> str:
    """Generate a cryptographically secure nonce."""
    return secrets.token_hex(32)
