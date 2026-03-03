"""KeyManager — persistent/rotatable ECDSA keys for contract signing and SER.

Supports file-based storage (stub). Production deployments should use
age-encrypted storage or HashiCorp Vault.
"""

import secrets
from pathlib import Path
from typing import Optional

import structlog
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

log = structlog.get_logger()


class KeyManager:
    """Manages ECDSA keys for signing and verification.

    Keys are persisted to a file (stub). For production, use age-encrypted
    storage or Vault integration.
    """

    def __init__(self, key_path: Optional[Path] = None) -> None:
        """Initialize KeyManager.

        Args:
            key_path: Path to key file. Defaults to ~/.agenlang/keys.pem.
                Set AGENLANG_KEY_DIR to override base directory.
        """
        import os

        base = Path(os.environ.get("AGENLANG_KEY_DIR", str(Path.home() / ".agenlang")))
        self._key_path = key_path or base / "keys.pem"
        self._ser_key_path = self._key_path.parent / "ser.key"
        self._private_key: Optional[ec.EllipticCurvePrivateKey] = None

    def generate(self) -> ec.EllipticCurvePrivateKey:
        """Generate a new ECDSA key (SECP256R1).

        Returns:
            New private key. Also persists to key_path.
        """
        self._private_key = ec.generate_private_key(ec.SECP256R1(), default_backend())
        self._save()
        log.info("key_generated", path=str(self._key_path))
        return self._private_key

    def load(self) -> Optional[ec.EllipticCurvePrivateKey]:
        """Load private key from disk.

        Returns:
            Private key if file exists, else None.
        """
        if not self._key_path.exists():
            return None
        pem = self._key_path.read_bytes()
        loaded = serialization.load_pem_private_key(
            pem, password=None, backend=default_backend()
        )
        assert isinstance(loaded, ec.EllipticCurvePrivateKey)
        self._private_key = loaded
        return self._private_key

    def get_or_create(self) -> ec.EllipticCurvePrivateKey:
        """Get existing key or generate new one.

        Returns:
            Private key.
        """
        key = self.load()
        if key is None:
            key = self.generate()
        return key

    def get_public_key_pem(self) -> bytes:
        """Get public key as PEM for inclusion in contract issuer.

        Returns:
            PEM-encoded public key.
        """
        key = self.get_or_create()
        return key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )

    def sign(self, data: bytes) -> bytes:
        """Sign data with ECDSA-SHA256.

        Args:
            data: Data to sign.

        Returns:
            DER-encoded signature.
        """
        key = self.get_or_create()
        return key.sign(data, ec.ECDSA(hashes.SHA256()))

    def verify(self, data: bytes, signature: bytes, public_key_pem: bytes) -> bool:
        """Verify ECDSA-SHA256 signature.

        Args:
            data: Original data.
            signature: DER-encoded signature.
            public_key_pem: PEM-encoded public key.

        Returns:
            True if signature valid.
        """
        from cryptography.exceptions import InvalidSignature

        loaded_pub = serialization.load_pem_public_key(
            public_key_pem, backend=default_backend()
        )
        assert isinstance(loaded_pub, ec.EllipticCurvePublicKey)
        try:
            loaded_pub.verify(signature, data, ec.ECDSA(hashes.SHA256()))
            return True
        except InvalidSignature:
            return False

    def _save(self) -> None:
        """Persist private key to disk."""
        if self._private_key is None:
            return
        self._key_path.parent.mkdir(parents=True, exist_ok=True)
        pem = self._private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        self._key_path.write_bytes(pem)
        self._key_path.chmod(0o600)

    def get_ser_key(self) -> bytes:
        """Get or create 32-byte key for SER HMAC. Persistent across runs.

        Returns:
            32-byte key for HMAC.
        """
        if self._ser_key_path.exists():
            return self._ser_key_path.read_bytes()
        key = secrets.token_bytes(32)
        self._ser_key_path.parent.mkdir(parents=True, exist_ok=True)
        self._ser_key_path.write_bytes(key)
        self._ser_key_path.chmod(0o600)
        return key

    @staticmethod
    def verify_replay_hmac(content: bytes, hmac_value: bytes, key: bytes) -> bool:
        """Verify HMAC-SHA256 of replay content.

        Args:
            content: Replay content (without HMAC suffix).
            hmac_value: Expected HMAC (32 bytes).
            key: HMAC key.

        Returns:
            True if HMAC matches.
        """
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives import hmac as hmac_mod

        h = hmac_mod.HMAC(key, hashes.SHA256(), backend=default_backend())
        h.update(content)
        try:
            h.verify(hmac_value)
            return True
        except InvalidSignature:
            return False
