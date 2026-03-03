# Copyright 2024 AgenLang Contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for SolanaBackend settlement."""

from unittest.mock import MagicMock, patch

import pytest

from agenlang.solana import SolanaBackend, SolanaStubBackend


def test_solana_stub_backend() -> None:
    """SolanaStubBackend returns stub receipt."""
    backend = SolanaStubBackend()
    receipt = backend.settle("recipient-1", 100.0, 0.001)
    assert receipt["status"] == "solana_stub"
    assert receipt["recipient"] == "recipient-1"
    assert receipt["amount"] == 0.1
    assert receipt["rpc_endpoint"] == "stub:"


def test_solana_backend_stub_mode() -> None:
    """SolanaBackend with stub: URL returns stub receipt."""
    backend = SolanaBackend(rpc_url="stub:")
    receipt = backend.settle("r", 50.0, 0.01)
    assert receipt["status"] == "solana_stub"
    assert receipt["amount"] == 0.5


def test_solana_backend_success_path(monkeypatch: pytest.MonkeyPatch) -> None:
    """SolanaBackend success path with mocked Solana RPC."""
    monkeypatch.delenv("HELIUS_API_KEY", raising=False)
    monkeypatch.delenv("HELIUM_API_KEY", raising=False)

    blockhash_resp = MagicMock()
    blockhash_resp.status_code = 200
    blockhash_resp.json.return_value = {
        "jsonrpc": "2.0",
        "result": {"value": {"blockhash": "abc123def456", "lastValidBlockHeight": 100}},
    }
    blockhash_resp.raise_for_status = MagicMock()

    slot_resp = MagicMock()
    slot_resp.status_code = 200
    slot_resp.json.return_value = {"jsonrpc": "2.0", "result": 42000}
    slot_resp.raise_for_status = MagicMock()

    with patch(
        "agenlang.solana.requests.post", side_effect=[blockhash_resp, slot_resp]
    ):
        backend = SolanaBackend(rpc_url="https://api.devnet.solana.com")
        receipt = backend.settle("recipient", 200.0, 0.001)
    assert receipt["status"] == "confirmed"
    assert receipt["recipient"] == "recipient"
    assert receipt["amount"] == 0.2
    assert receipt["tx_id"].startswith("sol:")
    assert receipt["block_height"] == 42000


def test_solana_backend_rpc_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """SolanaBackend handles RPC errors gracefully."""
    monkeypatch.delenv("HELIUS_API_KEY", raising=False)
    monkeypatch.delenv("HELIUM_API_KEY", raising=False)

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "jsonrpc": "2.0",
        "error": {"code": -32600, "message": "Invalid request"},
    }
    mock_resp.raise_for_status = MagicMock()

    with patch("agenlang.solana.requests.post", return_value=mock_resp):
        backend = SolanaBackend(rpc_url="https://api.devnet.solana.com")
        receipt = backend.settle("recipient", 100.0, 0.001)
    assert receipt["status"] == "error"
    assert "Solana RPC error" in receipt["error"]


def test_solana_backend_http_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """SolanaBackend handles HTTP failures."""
    monkeypatch.delenv("HELIUS_API_KEY", raising=False)
    monkeypatch.delenv("HELIUM_API_KEY", raising=False)

    with patch(
        "agenlang.solana.requests.post",
        side_effect=ConnectionError("connection refused"),
    ):
        backend = SolanaBackend(rpc_url="https://api.devnet.solana.com")
        receipt = backend.settle("recipient", 100.0, 0.001)
    assert receipt["status"] == "error"
    assert "connection refused" in receipt["error"]


def test_solana_backend_helius_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """SolanaBackend uses Helius RPC when HELIUS_API_KEY is set."""
    monkeypatch.delenv("HELIUM_API_KEY", raising=False)
    monkeypatch.setenv("HELIUS_API_KEY", "helius-key-456")
    backend = SolanaBackend()
    assert "helius" in backend.rpc_url
    assert "helius-key-456" in backend.rpc_url


def test_solana_backend_helium_key_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    """SolanaBackend falls back to HELIUM_API_KEY with deprecation warning."""
    monkeypatch.delenv("HELIUS_API_KEY", raising=False)
    monkeypatch.setenv("HELIUM_API_KEY", "legacy-key-789")
    import warnings

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        backend = SolanaBackend()
    assert "helius" in backend.rpc_url
    assert "legacy-key-789" in backend.rpc_url
    assert len(w) == 1
    assert "deprecated" in str(w[0].message).lower()


def test_solana_backend_helius_priority(monkeypatch: pytest.MonkeyPatch) -> None:
    """HELIUS_API_KEY takes priority over HELIUM_API_KEY."""
    monkeypatch.setenv("HELIUS_API_KEY", "primary-key")
    monkeypatch.setenv("HELIUM_API_KEY", "legacy-key")
    backend = SolanaBackend()
    assert "primary-key" in backend.rpc_url
    assert "legacy-key" not in backend.rpc_url
