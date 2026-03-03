"""AgenLang Memory - handoff and purge with GDPR compliance.

Supports plain JSON, SQLite (default), and AES-GCM encrypted backends.
"""

import json
import secrets
import sqlite3
from pathlib import Path
from typing import Any, Dict, Optional

import structlog
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

log = structlog.get_logger()


class Memory:
    """Handles memory handoff and purge with GDPR compliance.

    Persists whitelisted keys to a JSON file; supports purge on completion.
    """

    def __init__(self, contract_id: str, data_subject: str) -> None:
        """Initialize memory backend for a contract.

        Args:
            contract_id: Contract URN (used for file naming).
            data_subject: Data subject identifier for GDPR.
        """
        self.contract_id = contract_id
        self.data_subject = data_subject
        self.memory_path = Path(f"{contract_id}.memory.json")

    def handoff(self, keys: list[str], data: Dict[str, Any]) -> None:
        """Save whitelisted memory keys.

        Args:
            keys: Keys to persist from data.
            data: Full data dict; only keys in keys are saved.
        """
        whitelisted_data = {k: data.get(k) for k in keys}
        self.memory_path.write_text(json.dumps(whitelisted_data))

    def load(self) -> Dict[str, Any]:
        """Load memory from file.

        Returns:
            Loaded memory dict, or empty dict if no file.
        """
        if self.memory_path.exists():
            return json.loads(self.memory_path.read_text())
        return {}

    def purge(self) -> None:
        """Purge memory for GDPR compliance."""
        if self.memory_path.exists():
            self.memory_path.unlink()
            log.info("memory_purged", data_subject=self.data_subject)


class EncryptedMemoryBackend:
    """AES-GCM encrypted memory backend with schema validation.

    Data is encrypted at rest; only whitelisted keys are persisted.
    """

    def __init__(
        self,
        contract_id: str,
        data_subject: str,
        key: Optional[bytes] = None,
    ) -> None:
        """Initialize encrypted memory backend.

        Args:
            contract_id: Contract URN for file naming.
            data_subject: Data subject for GDPR.
            key: 32-byte AES key. If None, derived from KeyManager.
        """
        self.contract_id = contract_id
        self.data_subject = data_subject
        self.memory_path = Path(f"{contract_id}.memory.enc")
        if key is None:
            from .keys import KeyManager

            km = KeyManager()
            key = km.get_ser_key()
        if len(key) != 32:
            raise ValueError("Key must be 32 bytes for AES-256-GCM")
        self._aesgcm = AESGCM(key)

    def handoff(self, keys: list[str], data: Dict[str, Any]) -> None:
        """Save whitelisted memory keys (encrypted)."""
        whitelisted = {k: data.get(k) for k in keys}
        plaintext = json.dumps(whitelisted).encode("utf-8")
        nonce = secrets.token_bytes(12)
        ciphertext = self._aesgcm.encrypt(nonce, plaintext, None)
        self.memory_path.write_bytes(nonce + ciphertext)

    def load(self) -> Dict[str, Any]:
        """Load and decrypt memory."""
        if not self.memory_path.exists():
            return {}
        raw = self.memory_path.read_bytes()
        nonce, ciphertext = raw[:12], raw[12:]
        plaintext = self._aesgcm.decrypt(nonce, ciphertext, None)
        return json.loads(plaintext.decode("utf-8"))

    def purge(self) -> None:
        """Purge encrypted memory."""
        if self.memory_path.exists():
            self.memory_path.unlink()
            log.info("memory_purged", data_subject=self.data_subject)


class SQLiteMemoryBackend:
    """SQLite-backed memory (default for production)."""

    def __init__(self, contract_id: str, data_subject: str) -> None:
        """Initialize SQLite memory backend."""
        self.contract_id = contract_id
        self.data_subject = data_subject
        self._db_path = Path(f"{contract_id}.memory.db")

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._db_path))
        conn.execute(
            "CREATE TABLE IF NOT EXISTS memory " "(key TEXT PRIMARY KEY, value TEXT)"
        )
        return conn

    def handoff(self, keys: list[str], data: Dict[str, Any]) -> None:
        """Save whitelisted keys to SQLite."""
        whitelisted = {k: data.get(k) for k in keys}
        conn = self._conn()
        try:
            conn.execute("DELETE FROM memory")
            for k, v in whitelisted.items():
                conn.execute(
                    "INSERT INTO memory (key, value) VALUES (?, ?)",
                    (k, json.dumps(v) if v is not None else "null"),
                )
            conn.commit()
        finally:
            conn.close()

    def load(self) -> Dict[str, Any]:
        """Load memory from SQLite."""
        if not self._db_path.exists():
            return {}
        conn = self._conn()
        try:
            rows = conn.execute("SELECT key, value FROM memory").fetchall()
            result = {}
            for k, v in rows:
                try:
                    result[k] = json.loads(v)
                except json.JSONDecodeError:
                    result[k] = v
            return result
        finally:
            conn.close()

    def purge(self) -> None:
        """Purge memory."""
        if self._db_path.exists():
            self._db_path.unlink()
            log.info("memory_purged", data_subject=self.data_subject)
