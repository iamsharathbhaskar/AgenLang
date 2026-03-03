"""Tests for memory backends."""

import os
import secrets
from pathlib import Path

import pytest

from agenlang.memory import (
    EncryptedMemoryBackend,
    Memory,
    SQLiteMemoryBackend,
    StorageBackend,
)


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


def test_storage_backend_abc() -> None:
    """StorageBackend ABC cannot be instantiated directly."""
    with pytest.raises(TypeError):
        StorageBackend()  # type: ignore[abstract]


def test_all_backends_are_storage_backends() -> None:
    """All memory backends subclass StorageBackend."""
    assert issubclass(Memory, StorageBackend)
    assert issubclass(EncryptedMemoryBackend, StorageBackend)
    assert issubclass(SQLiteMemoryBackend, StorageBackend)


def test_redis_memory_import_error() -> None:
    """RedisMemoryBackend raises ImportError when redis not available."""
    from unittest.mock import patch

    with patch.dict("sys.modules", {"redis": None}):
        with pytest.raises(ImportError, match="redis package required"):
            from agenlang.memory import RedisMemoryBackend

            RedisMemoryBackend("test", redis_url="redis://localhost:6379")


def test_redis_memory_backend_operations() -> None:
    """RedisMemoryBackend handoff, load, purge with mocked Redis client."""
    from unittest.mock import MagicMock, patch

    mock_redis = MagicMock()
    mock_redis_cls = MagicMock()
    mock_redis_cls.Redis.from_url.return_value = mock_redis

    with patch.dict("sys.modules", {"redis": mock_redis_cls}):
        from agenlang.memory import RedisMemoryBackend

        backend = RedisMemoryBackend("test-contract", ttl_seconds=600)

    mock_pipe = MagicMock()
    mock_redis.pipeline.return_value = mock_pipe
    backend.handoff(["key1", "key2"], {"key1": "val1", "key2": 42, "key3": "skip"})
    mock_pipe.set.assert_any_call("agenlang:test-contract:key1", '"val1"', ex=600)
    mock_pipe.set.assert_any_call("agenlang:test-contract:key2", "42", ex=600)
    mock_pipe.execute.assert_called_once()

    mock_redis.scan_iter.return_value = [
        b"agenlang:test-contract:key1",
        b"agenlang:test-contract:key2",
    ]
    mock_redis.get.side_effect = [b'"val1"', b"42"]
    loaded = backend.load()
    assert loaded == {"key1": "val1", "key2": 42}

    mock_redis.scan_iter.return_value = [b"agenlang:test-contract:key1"]
    backend.purge()
    mock_redis.delete.assert_called_once()


def test_redis_memory_load_non_json() -> None:
    """RedisMemoryBackend handles non-JSON values gracefully."""
    from unittest.mock import MagicMock, patch

    mock_redis = MagicMock()
    mock_redis_cls = MagicMock()
    mock_redis_cls.Redis.from_url.return_value = mock_redis

    with patch.dict("sys.modules", {"redis": mock_redis_cls}):
        from agenlang.memory import RedisMemoryBackend

        backend = RedisMemoryBackend("test-decode")

    mock_redis.scan_iter.return_value = [b"agenlang:test-decode:raw"]
    mock_redis.get.return_value = b"not-json-content"
    loaded = backend.load()
    assert loaded["raw"] == "not-json-content"


def test_redis_memory_purge_empty() -> None:
    """RedisMemoryBackend purge with no keys is a no-op."""
    from unittest.mock import MagicMock, patch

    mock_redis = MagicMock()
    mock_redis_cls = MagicMock()
    mock_redis_cls.Redis.from_url.return_value = mock_redis

    with patch.dict("sys.modules", {"redis": mock_redis_cls}):
        from agenlang.memory import RedisMemoryBackend

        backend = RedisMemoryBackend("test-empty")

    mock_redis.scan_iter.return_value = []
    backend.purge()
    mock_redis.delete.assert_not_called()
