"""Tests for settlement backends."""

from unittest.mock import patch

import pytest

from agenlang.settlement import HeliumBackend, HeliumStubBackend, StubSettlementBackend


def test_stub_settlement() -> None:
    """Stub settlement returns receipt."""
    backend = StubSettlementBackend()
    receipt = backend.settle("recipient", 100.0, 2.0)
    assert receipt["status"] == "stub"
    assert receipt["amount_owed"] == 200.0


def test_helium_stub() -> None:
    """Helium stub returns receipt."""
    backend = HeliumStubBackend()
    receipt = backend.settle("recipient", 50.0, 10.0, "helium:addr")
    assert receipt["status"] == "helium_stub"
    assert receipt["amount"] == 500.0


def test_helium_backend_stub_mode() -> None:
    """HeliumBackend with stub api_url returns stub receipt."""
    backend = HeliumBackend(api_url="stub:")
    receipt = backend.settle("recipient", 50.0, 10.0, "helium:addr")
    assert receipt["status"] == "helium_stub"
    assert receipt["amount"] == 500.0
    assert receipt["address"] == "helium:addr"


def test_helium_backend_missing_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """HeliumBackend raises ValueError without HELIUM_API_KEY."""
    monkeypatch.delenv("HELIUM_API_KEY", raising=False)
    with pytest.raises(ValueError, match="HELIUM_API_KEY"):
        HeliumBackend()


def test_helium_backend_error_path(monkeypatch: pytest.MonkeyPatch) -> None:
    """HeliumBackend returns error status when HTTP fails."""
    monkeypatch.setenv("HELIUM_API_KEY", "test-key")
    backend = HeliumBackend()

    with patch("requests.post") as mock_post:
        mock_post.side_effect = Exception("Connection refused")
        receipt = backend.settle("recipient", 50.0, 10.0)

    assert receipt["status"] == "error"
    assert receipt["amount"] == 500.0
    assert "error" in receipt


def test_helium_backend_success_path(monkeypatch: pytest.MonkeyPatch) -> None:
    """HeliumBackend returns submitted with auth header and parsed response."""
    monkeypatch.setenv("HELIUM_API_KEY", "test-key-123")
    backend = HeliumBackend()

    with patch("requests.post") as mock_post:
        mock_post.return_value.raise_for_status = lambda: None
        mock_post.return_value.json.return_value = {
            "hash": "txn_abc123",
            "type": "payment_v2",
            "height": 42,
        }
        receipt = backend.settle("recipient", 50.0, 10.0)

    assert receipt["status"] == "submitted"
    assert receipt["amount"] == 500.0
    assert receipt["tx_id"] == "txn_abc123"
    assert receipt["block_height"] == 42
    assert receipt["type"] == "payment_v2"
    call_kwargs = mock_post.call_args
    assert call_kwargs.kwargs["headers"]["Authorization"] == "Bearer test-key-123"
