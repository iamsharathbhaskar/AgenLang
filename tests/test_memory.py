"""Tests for memory backends."""

import os
import secrets
from pathlib import Path

from agenlang.memory import EncryptedMemoryBackend, Memory, SQLiteMemoryBackend


def test_memory_handoff_load_purge(tmp_path: Path) -> None:
    """Memory handoff, load, purge."""
    orig = os.getcwd()
    try:
        os.chdir(tmp_path)
        mem = Memory("test-contract", "subject")
        mem.handoff(["a", "b"], {"a": 1, "b": 2, "c": 3})
        assert mem.load() == {"a": 1, "b": 2}
        mem.purge()
        assert mem.load() == {}
    finally:
        os.chdir(orig)


def test_sqlite_memory(tmp_path: Path) -> None:
    """SQLite memory backend."""
    orig = os.getcwd()
    try:
        os.chdir(tmp_path)
        mem = SQLiteMemoryBackend("test-sqlite", "subject")
        mem.handoff(["x"], {"x": "value"})
        assert mem.load() == {"x": "value"}
        mem.purge()
        assert mem.load() == {}
    finally:
        os.chdir(orig)


def test_encrypted_memory(tmp_path: Path) -> None:
    """Encrypted memory backend."""
    orig = os.getcwd()
    try:
        os.chdir(tmp_path)
        key = secrets.token_bytes(32)
        mem = EncryptedMemoryBackend("test-enc", "subject", key=key)
        mem.handoff(["secret"], {"secret": "data"})
        assert mem.load() == {"secret": "data"}
        mem.purge()
        assert mem.load() == {}
    finally:
        os.chdir(orig)
